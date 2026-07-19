import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from billing.access import feature_gate
from core.permissions import Cap, require_cap
from donations.models import CategoryKind, Transaction

from .forms import PurchaseForm, VendorForm
from .models import Purchase, Vendor


def _require_org(request):
    return getattr(request, "organization", None)


def _no_org(request):
    return render(request, "donations/no_org.html")


def _apply_txn_fields(txn, purchase):
    """Copy a purchase's figures onto its mirroring finance expense entry, so a
    transaction created at purchase time and one re-synced after an edit always
    describe the purchase the same way. The caller sets organization/recorded_by
    (which never change) and saves."""
    txn.kind = CategoryKind.EXPENSE
    txn.category = purchase.category
    txn.party = purchase.vendor.name if purchase.vendor else ""
    txn.amount = purchase.amount
    txn.currency = purchase.currency
    txn.method = purchase.method
    txn.reference = purchase.reference
    txn.occurred_at = purchase.purchased_on
    vendor = f" · {purchase.vendor.name}" if purchase.vendor else ""
    txn.note = f"Purchase · {purchase.item}{vendor}"


def _post_purchase_to_finance(org, purchase, user):
    """Create the mirroring finance expense entry for a freshly saved purchase and
    link the two together. Caller runs this inside an atomic block so the books
    can never end up with a purchase but no expense entry (or vice versa)."""
    txn = Transaction(organization=org, recorded_by=user)
    _apply_txn_fields(txn, purchase)
    txn.save()
    purchase.transaction = txn
    purchase.save(update_fields=["transaction"])


# --- Overview --------------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def overview(request):
    """Every purchase the org has recorded, with headline spend figures."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    today = timezone.localdate()
    year = today.year

    purchases = (
        Purchase.objects.filter(organization=org)
        .select_related("vendor", "category")
    )

    total_all = purchases.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    spent_year = (
        purchases.filter(purchased_on__year=year).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    vendor_count = Vendor.objects.filter(organization=org).count()

    context = {
        "purchases": purchases,
        "year": year,
        "total_all": total_all,
        "spent_year": spent_year,
        "purchase_count": purchases.count(),
        "vendor_count": vendor_count,
    }
    return render(request, "purchases/overview.html", context)


# --- Purchases -------------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def purchase_create(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    from donations.models import Category

    if not Category.objects.filter(
        organization=org, kind=CategoryKind.EXPENSE, is_active=True
    ).exists():
        messages.info(
            request,
            "Add an expense category in Finance before recording a purchase.",
        )
        return redirect("purchases:overview")

    if request.method == "POST":
        form = PurchaseForm(request.POST, organization=org)
        if form.is_valid():
            with db_transaction.atomic():
                purchase = form.save(commit=False)
                purchase.recorded_by = request.user
                purchase.save()
                _post_purchase_to_finance(org, purchase, request.user)
            messages.success(
                request,
                f"Purchase #{purchase.voucher_number} recorded — "
                f"{purchase.amount} {purchase.currency} for {purchase.item}.",
            )
            return redirect("purchases:overview")
    else:
        form = PurchaseForm(
            organization=org, initial={"purchased_on": timezone.localdate()}
        )

    return render(
        request, "purchases/purchase_form.html", {"form": form, "is_edit": False}
    )


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def purchase_edit(request, pk):
    """Correct a recorded purchase and re-sync its mirroring finance expense entry
    so the books match the purchase."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    purchase = get_object_or_404(
        Purchase.objects.select_related("vendor", "category", "transaction"),
        pk=pk,
        organization=org,
    )

    if request.method == "POST":
        form = PurchaseForm(request.POST, instance=purchase, organization=org)
        if form.is_valid():
            with db_transaction.atomic():
                purchase = form.save()
                # Keep the finance entry in lock-step. Defensive: a purchase
                # should always have one, but never leave it unlinked.
                txn = purchase.transaction or Transaction(
                    organization=org, recorded_by=request.user
                )
                _apply_txn_fields(txn, purchase)
                txn.save()
                if purchase.transaction_id != txn.id:
                    purchase.transaction = txn
                    purchase.save(update_fields=["transaction"])
            messages.success(
                request, f"Updated purchase #{purchase.voucher_number}."
            )
            return redirect("purchases:overview")
    else:
        form = PurchaseForm(instance=purchase, organization=org)

    return render(
        request,
        "purchases/purchase_form.html",
        {"form": form, "is_edit": True, "purchase": purchase},
    )


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def purchase_delete(request, pk):
    """Void a purchase and reverse its finance expense entry together, so the
    purchase and the books are never left disagreeing."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    purchase = get_object_or_404(
        Purchase.objects.select_related("transaction"), pk=pk, organization=org
    )

    if request.method == "POST":
        voucher = purchase.voucher_number
        with db_transaction.atomic():
            txn = purchase.transaction
            purchase.delete()
            if txn is not None:
                txn.delete()
        messages.success(
            request,
            f"Voided purchase #{voucher} and reversed its finance entry.",
        )
        return redirect("purchases:overview")

    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": f"Void purchase #{purchase.voucher_number}?",
            "message": (
                f"This removes the {purchase.amount} {purchase.currency} purchase "
                f"of {purchase.item}."
            ),
            "consequences": [
                "The matching finance expense entry will be reversed.",
                "This cannot be undone.",
            ],
            "confirm_label": "Void purchase",
            "cancel_url": reverse("purchases:overview"),
        },
    )


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def purchases_export(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    purchases = (
        Purchase.objects.filter(organization=org)
        .select_related("vendor", "category")
        .order_by("purchased_on", "voucher_number")
    )

    response = HttpResponse(content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}-purchases-{stamp}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        ["Voucher", "Date", "Item", "Vendor", "Category", "Quantity",
         "Method", "Amount", "Currency", "Reference"]
    )
    for p in purchases:
        writer.writerow(
            [
                p.voucher_number,
                p.purchased_on.isoformat(),
                p.item,
                p.vendor.name if p.vendor else "",
                p.category.name,
                p.quantity,
                p.get_method_display(),
                p.amount,
                p.currency,
                p.reference,
            ]
        )
    return response


# --- Vendors ---------------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def vendor_list(request):
    """Manage the org's suppliers, with an inline 'add vendor' form."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if request.method == "POST":
        form = VendorForm(request.POST, organization=org)
        if form.is_valid():
            vendor = form.save()
            messages.success(request, f"Added vendor “{vendor.name}”.")
            return redirect("purchases:vendor_list")
    else:
        form = VendorForm(organization=org)

    vendors = (
        Vendor.objects.filter(organization=org)
        .annotate(purchase_count=Count("purchases"))
        .order_by("name")
    )
    return render(
        request, "purchases/vendor_list.html", {"vendors": vendors, "form": form}
    )


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def vendor_edit(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    vendor = get_object_or_404(Vendor, pk=pk, organization=org)
    if request.method == "POST":
        form = VendorForm(request.POST, instance=vendor, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated “{vendor.name}”.")
            return redirect("purchases:vendor_list")
    else:
        form = VendorForm(instance=vendor, organization=org)

    return render(
        request, "purchases/vendor_form.html", {"form": form, "vendor": vendor}
    )


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def vendor_delete(request, pk):
    """Remove a vendor. Blocked while purchases still reference it."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    vendor = get_object_or_404(Vendor, pk=pk, organization=org)
    in_use = vendor.purchases.count()

    if request.method == "POST":
        if in_use:
            messages.error(
                request,
                f"“{vendor.name}” is on {in_use} purchase"
                f"{'' if in_use == 1 else 's'}. Reassign or remove those first.",
            )
            return redirect("purchases:vendor_list")
        name = vendor.name
        vendor.delete()
        messages.success(request, f"Deleted vendor “{name}”.")
        return redirect("purchases:vendor_list")

    consequences = ["This cannot be undone."]
    if in_use:
        consequences.insert(
            0,
            f"{in_use} purchase{'' if in_use == 1 else 's'} still name this vendor "
            "— you'll need to reassign them first.",
        )
    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": f"Delete “{vendor.name}”?",
            "message": f"You're about to remove the vendor “{vendor.name}”.",
            "consequences": consequences,
            "confirm_label": "Delete vendor",
            "cancel_url": reverse("purchases:vendor_list"),
        },
    )
