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
from donations.models import Category, CategoryKind, PaymentMethod, Transaction

from core.permissions import Cap, require_cap

from .forms import (
    PropertyTypeForm,
    RentAdjustmentForm,
    RentalUnitForm,
    RentPaymentForm,
    RentRevisionForm,
)
from .models import (
    RENTAL_INCOME_CATEGORY_CODE,
    RENTAL_INCOME_CATEGORY_NAME,
    RENTAL_REBATE_CATEGORY_CODE,
    RENTAL_REBATE_CATEGORY_NAME,
    PropertyType,
    RentAdjustment,
    RentalUnit,
    RentPayment,
    RentRevision,
)
from .slips import demand_context, receipt_context, render_pdf


def _require_org(request):
    """Return the current org or None — the same 'no tenant' guard the other apps use."""
    return getattr(request, "organization", None)


def _no_org(request):
    return render(request, "donations/no_org.html")


def _rent_category(org):
    """The org's 'Rental Income' income category, created on first use so rent
    receipts always have a finance bucket to post into. One category covers every
    property type; the per-type breakdown lives on the rentals overview."""
    category, _ = Category.objects.get_or_create(
        organization=org,
        kind=CategoryKind.INCOME,
        code=RENTAL_INCOME_CATEGORY_CODE,
        defaults={"name": RENTAL_INCOME_CATEGORY_NAME, "is_system": True},
    )
    return category


def _apply_txn_fields(txn, unit, payment):
    """Copy a rent receipt's figures onto its mirroring finance income entry, so
    a transaction created at receipt time and one re-synced after an edit always
    describe the payment the same way. The caller sets organization/kind/category
    /recorded_by (which never change) and saves."""
    txn.party = unit.tenant_name or unit.name
    txn.amount = payment.amount
    txn.currency = payment.currency
    txn.method = payment.method
    txn.reference = payment.reference
    txn.occurred_at = payment.paid_on
    txn.note = f"Rent · {unit.name} · {payment.period_label}"


def _post_rent_to_finance(org, unit, payment, user):
    """Create the mirroring finance income entry for a freshly saved rent receipt
    and link the two together. Caller runs this inside an atomic block so the
    books can never end up with a receipt but no income entry (or vice versa)."""
    txn = Transaction(
        organization=org,
        kind=CategoryKind.INCOME,
        category=_rent_category(org),
        recorded_by=user,
    )
    _apply_txn_fields(txn, unit, payment)
    txn.save()
    payment.transaction = txn
    payment.save(update_fields=["transaction"])


def _rebate_category(org):
    """The org's 'Rent Rebates & Concessions' expense category, created on first
    use. Rent is charged gross, so a rebate is booked here as an offsetting expense
    — the concession is visible in the books and net rental income stays right."""
    category, _ = Category.objects.get_or_create(
        organization=org,
        kind=CategoryKind.EXPENSE,
        code=RENTAL_REBATE_CATEGORY_CODE,
        defaults={"name": RENTAL_REBATE_CATEGORY_NAME, "is_system": True},
    )
    return category


def _apply_rebate_txn_fields(txn, unit, adjustment):
    """Copy a rebate's figures onto its mirroring finance expense entry, so an
    entry created at grant time and one re-synced after an edit always describe the
    rebate the same way. The caller sets organization/kind/category/recorded_by."""
    txn.party = unit.tenant_name or unit.name
    txn.amount = adjustment.amount
    txn.currency = adjustment.currency
    txn.method = PaymentMethod.OTHER
    txn.reference = ""
    txn.occurred_at = adjustment.dated_on
    txn.note = (
        f"Rent rebate · {unit.name} · {adjustment.reason} · {adjustment.period_label}"
    )


def _post_rebate_to_finance(org, unit, adjustment, user):
    """Create the mirroring finance expense entry for a freshly saved rebate and
    link the two together. Caller runs this inside an atomic block so the books
    never end up with a rebate but no expense entry (or vice versa)."""
    txn = Transaction(
        organization=org,
        kind=CategoryKind.EXPENSE,
        category=_rebate_category(org),
        recorded_by=user,
    )
    _apply_rebate_txn_fields(txn, unit, adjustment)
    txn.save()
    adjustment.transaction = txn
    adjustment.save(update_fields=["transaction"])


# --- Overview / rent roll --------------------------------------------------


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def overview(request):
    """The rent roll: every unit on the premises, the agreed rent, what's been
    collected this year, and who is in arrears — with a per-property-type
    breakdown of the monthly rent roll."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    today = timezone.localdate()
    year = today.year

    units = list(
        RentalUnit.objects.filter(organization=org)
        .select_related("property_type")
        .prefetch_related("revisions", "adjustments")
        .annotate(paid_all=Sum("rent_payments__amount"))
    )

    rent_roll = Decimal("0")  # monthly rent across active units
    arrears_total = Decimal("0")
    occupied = 0
    rows = []
    # Monthly rent roll grouped by property type, for the breakdown strip.
    by_type = {}
    for unit in units:
        paid = unit.paid_all or Decimal("0")
        balance = unit.balance(as_of=today, paid_total=paid)
        # The rent roll uses the rent in force now, not the tenancy's opening rate.
        current_rent = unit.current_rent(today)
        if unit.is_active:
            rent_roll += current_rent
            occupied += 1
            label = unit.property_type.name if unit.property_type else "Other"
            bucket = by_type.setdefault(
                label,
                {
                    "label": label,
                    "icon": unit.property_type.icon if unit.property_type else "",
                    "count": 0,
                    "rent": Decimal("0"),
                },
            )
            bucket["count"] += 1
            bucket["rent"] += current_rent
            if balance > 0:
                arrears_total += balance
        rows.append(
            {
                "unit": unit,
                "paid": paid,
                "balance": balance,
                "in_arrears": unit.is_active and balance > 0,
                "current_rent": current_rent,
            }
        )

    # Rent collected within the current calendar year (by date received).
    collected_year = (
        RentPayment.objects.filter(
            organization=org, paid_on__year=year
        ).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )

    context = {
        "rows": rows,
        "year": year,
        "rent_roll": rent_roll,
        "collected_year": collected_year,
        "arrears_total": arrears_total,
        "unit_count": len(units),
        "occupied": occupied,
        "type_breakdown": sorted(by_type.values(), key=lambda b: b["label"]),
    }
    return render(request, "rentals/overview.html", context)


# --- Property types --------------------------------------------------------


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def property_type_list(request):
    """Manage the org's rentable property types (Shop, Hall, ...). The page shows
    every type with its unit count and carries an inline 'add type' form."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if request.method == "POST":
        form = PropertyTypeForm(request.POST, organization=org)
        if form.is_valid():
            ptype = form.save()
            messages.success(request, f"Added property type “{ptype.name}”.")
            return redirect("rentals:property_type_list")
    else:
        form = PropertyTypeForm(organization=org)

    types = (
        PropertyType.objects.filter(organization=org)
        .annotate(unit_count=Count("units"))
        .order_by("name")
    )
    return render(
        request,
        "rentals/property_type_list.html",
        {"types": types, "form": form},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def property_type_edit(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    ptype = get_object_or_404(PropertyType, pk=pk, organization=org)
    if request.method == "POST":
        form = PropertyTypeForm(request.POST, instance=ptype, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated “{ptype.name}”.")
            return redirect("rentals:property_type_list")
    else:
        form = PropertyTypeForm(instance=ptype, organization=org)

    return render(
        request,
        "rentals/property_type_form.html",
        {"form": form, "ptype": ptype},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def property_type_delete(request, pk):
    """Remove a property type. Blocked while units still reference it — the app
    steers you to reassign or deactivate rather than erroring out."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    ptype = get_object_or_404(PropertyType, pk=pk, organization=org)
    in_use = ptype.units.count()

    if request.method == "POST":
        if in_use:
            messages.error(
                request,
                f"“{ptype.name}” is still used by {in_use} unit"
                f"{'' if in_use == 1 else 's'}. Reassign or remove those first, "
                "or just deactivate the type.",
            )
            return redirect("rentals:property_type_list")
        name = ptype.name
        ptype.delete()
        messages.success(request, f"Deleted property type “{name}”.")
        return redirect("rentals:property_type_list")

    consequences = ["This cannot be undone."]
    if in_use:
        consequences.insert(
            0,
            f"{in_use} unit{'' if in_use == 1 else 's'} still use this type — "
            "you'll need to reassign them first. Deactivating the type instead "
            "keeps existing units intact.",
        )
    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": f"Delete “{ptype.name}”?",
            "message": f"You're about to remove the “{ptype.name}” property type.",
            "consequences": consequences,
            "confirm_label": "Delete type",
            "cancel_url": reverse("rentals:property_type_list"),
        },
    )


# --- Units -----------------------------------------------------------------


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def unit_create(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if not PropertyType.objects.filter(organization=org, is_active=True).exists():
        messages.info(
            request,
            "Add at least one property type (Shop, Hall, ...) before adding a unit.",
        )
        return redirect("rentals:property_type_list")

    if request.method == "POST":
        form = RentalUnitForm(request.POST, organization=org)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f"Added {unit.name}.")
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentalUnitForm(
            organization=org, initial={"start_date": timezone.localdate()}
        )

    return render(
        request, "rentals/unit_form.html", {"form": form, "is_edit": False}
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def unit_edit(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(RentalUnit, pk=pk, organization=org)
    if request.method == "POST":
        form = RentalUnitForm(request.POST, instance=unit, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated {unit.name}.")
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentalUnitForm(instance=unit, organization=org)

    return render(
        request,
        "rentals/unit_form.html",
        {"form": form, "is_edit": True, "unit": unit},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def unit_delete(request, pk):
    """Permanently remove a unit and its whole rent history. Deleting the unit
    cascades to its receipts, so we first reverse each receipt's mirroring finance
    income entry — otherwise the books would keep rent income for receipts that no
    longer exist. For a unit that has simply been vacated, editing it to inactive
    is the gentler option; this is the hard delete."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(RentalUnit, pk=pk, organization=org)
    payment_count = unit.rent_payments.count()

    if request.method == "POST":
        name = unit.name
        with db_transaction.atomic():
            # Capture the linked finance entries before the cascade detaches them.
            txn_ids = list(
                unit.rent_payments.exclude(transaction=None).values_list(
                    "transaction_id", flat=True
                )
            )
            unit.delete()
            if txn_ids:
                Transaction.objects.filter(
                    organization=org, id__in=txn_ids
                ).delete()
        messages.success(
            request,
            f"Deleted {name}"
            + (
                f" and reversed its {payment_count} rent receipt"
                f"{'' if payment_count == 1 else 's'}."
                if payment_count
                else "."
            ),
        )
        return redirect("rentals:overview")

    consequences = ["This cannot be undone."]
    if payment_count:
        consequences.insert(
            0,
            f"{payment_count} rent receipt{'' if payment_count == 1 else 's'} "
            "and the matching finance income entries will be reversed.",
        )
    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": f"Delete {unit.name}?",
            "message": (
                f"You're about to permanently remove {unit.name} "
                f"({unit.tenant_name}) and its entire rent history."
            ),
            "consequences": consequences,
            "confirm_label": "Delete unit",
            "cancel_url": reverse("rentals:unit_detail", args=[unit.pk]),
        },
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def unit_detail(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(
        RentalUnit.objects.select_related("property_type").prefetch_related(
            "revisions", "adjustments"
        ),
        pk=pk,
        organization=org,
    )
    payments = unit.rent_payments.all()
    today = timezone.localdate()

    paid = payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    balance = unit.balance(as_of=today, paid_total=paid)

    return render(
        request,
        "rentals/unit_detail.html",
        {
            "unit": unit,
            "payments": payments,
            "paid_total": paid,
            "expected": unit.expected_to_date(today),
            "months_due": unit.months_due(today),
            "balance": balance,
            "in_arrears": unit.is_active and balance > 0,
            "current_rent": unit.current_rent(today),
            "revisions": list(unit.revisions.all()),
            "adjustments": list(unit.adjustments.all()),
            "rebate_total": unit.adjustments_total(today),
        },
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def unit_ledger(request, pk):
    """A running account statement for one unit: opening balance, monthly rent
    charges, and payments, each with the balance owed after it."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(RentalUnit, pk=pk, organization=org)
    today = timezone.localdate()
    entries = unit.ledger(as_of=today)

    total_charged = sum((e["charge"] for e in entries), Decimal("0"))
    total_credited = sum((e["credit"] for e in entries), Decimal("0"))
    balance = entries[-1]["running"] if entries else Decimal("0")

    return render(
        request,
        "rentals/unit_ledger.html",
        {
            "unit": unit,
            "entries": entries,
            "total_charged": total_charged,
            "total_credited": total_credited,
            "balance": balance,
            "in_arrears": unit.is_active and balance > 0,
        },
    )


# --- Rent payments ---------------------------------------------------------


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def payment_new(request):
    """Record a rent receipt without first opening a unit — the form carries a
    'from whom' dropdown so you choose the unit/tenant here. Same flow as
    `payment_create`, just with the unit picked on the form instead of the URL."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    today = timezone.localdate()

    if request.method == "POST":
        form = RentPaymentForm(request.POST, organization=org)
        if form.is_valid():
            unit = form.cleaned_data["unit"]
            # Save the receipt and its mirroring finance income entry together,
            # so the books can never end up with one but not the other.
            with db_transaction.atomic():
                payment = form.save(commit=False)
                payment.recorded_by = request.user
                payment.save()
                _post_rent_to_finance(org, unit, payment, request.user)

            messages.success(
                request,
                f"Receipt #{payment.receipt_number} recorded — "
                f"{payment.amount} {payment.currency} from "
                f"{unit.tenant_name or unit.name} for {payment.period_label}.",
            )
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentPaymentForm(
            organization=org,
            initial={
                "period_month": today.month,
                "period_year": today.year,
                "paid_on": today,
            },
        )

    return render(
        request,
        "rentals/payment_form.html",
        {"form": form, "pick_unit": True},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def payment_create(request, unit_pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(RentalUnit, pk=unit_pk, organization=org)
    today = timezone.localdate()

    if request.method == "POST":
        form = RentPaymentForm(request.POST, organization=org, unit=unit)
        if form.is_valid():
            # Save the receipt and its mirroring finance income entry together,
            # so the books can never end up with one but not the other.
            with db_transaction.atomic():
                payment = form.save(commit=False)
                payment.recorded_by = request.user
                payment.save()
                _post_rent_to_finance(org, unit, payment, request.user)

            messages.success(
                request,
                f"Receipt #{payment.receipt_number} recorded — "
                f"{payment.amount} {payment.currency} for {payment.period_label}.",
            )
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        # Default the period to the oldest month still unpaid, not today — a
        # tenant in arrears is settling the month that fell due first.
        due_year, due_month = unit.next_due_period(today)
        form = RentPaymentForm(
            organization=org,
            unit=unit,
            initial={
                "period_month": due_month,
                "period_year": due_year,
                "paid_on": today,
                # The rent in force for the month being settled — which may differ
                # from today's rent when clearing older arrears.
                "amount": unit.rent_for_period(due_year, due_month),
            },
        )

    balance = unit.balance(as_of=today)
    return render(
        request,
        "rentals/payment_form.html",
        {
            "form": form,
            "unit": unit,
            "months_due": unit.months_due(today),
            "balance": balance,
            "in_arrears": unit.is_active and balance > 0,
        },
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def payment_edit(request, pk):
    """Correct a recorded rent receipt — a wrong amount, period, or date — and
    re-sync its mirroring finance income entry so the books match the receipt."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    payment = get_object_or_404(
        RentPayment.objects.select_related("unit", "transaction"),
        pk=pk,
        organization=org,
    )
    unit = payment.unit

    if request.method == "POST":
        form = RentPaymentForm(
            request.POST, instance=payment, organization=org, unit=unit
        )
        if form.is_valid():
            with db_transaction.atomic():
                payment = form.save()
                # Keep the finance entry in lock-step. Defensive get_or_create:
                # a receipt should always have one, but never leave it unlinked.
                txn = payment.transaction or Transaction(
                    organization=org,
                    kind=CategoryKind.INCOME,
                    category=_rent_category(org),
                    recorded_by=request.user,
                )
                _apply_txn_fields(txn, unit, payment)
                txn.save()
                if payment.transaction_id != txn.id:
                    payment.transaction = txn
                    payment.save(update_fields=["transaction"])

            messages.success(
                request, f"Updated receipt #{payment.receipt_number}."
            )
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentPaymentForm(instance=payment, organization=org, unit=unit)

    return render(
        request,
        "rentals/payment_form.html",
        {"form": form, "unit": unit, "payment": payment, "is_edit": True},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def payment_delete(request, pk):
    """Void a rent receipt and reverse its finance income entry together, so the
    receipt and the books are never left disagreeing."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    payment = get_object_or_404(
        RentPayment.objects.select_related("unit", "transaction"),
        pk=pk,
        organization=org,
    )
    unit = payment.unit

    if request.method == "POST":
        receipt = payment.receipt_number
        with db_transaction.atomic():
            txn = payment.transaction
            payment.delete()
            if txn is not None:
                txn.delete()
        messages.success(
            request,
            f"Voided receipt #{receipt} and reversed its finance entry.",
        )
        return redirect("rentals:unit_detail", pk=unit.pk)

    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": f"Void receipt #{payment.receipt_number}?",
            "message": (
                f"This removes the {payment.amount} {payment.currency} receipt "
                f"for {payment.period_label} on {unit.name}."
            ),
            "consequences": [
                "The matching finance income entry will be reversed.",
                "This cannot be undone.",
            ],
            "confirm_label": "Void receipt",
            "cancel_url": reverse("rentals:unit_detail", args=[unit.pk]),
        },
    )


# --- Rent revisions (increase / decrease) ----------------------------------


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def revision_add(request, unit_pk):
    """Record a rent increase or decrease for a unit, effective from a chosen
    month. Past months keep the rate they were charged at; every month from the
    effective one onward uses the new rent."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(RentalUnit, pk=unit_pk, organization=org)
    today = timezone.localdate()

    if request.method == "POST":
        form = RentRevisionForm(request.POST, organization=org, unit=unit)
        if form.is_valid():
            revision = form.save(commit=False)
            revision.recorded_by = request.user
            revision.save()
            messages.success(
                request,
                f"Rent for {unit.name} set to {revision.monthly_rent} "
                f"{unit.currency} from {revision.effective_label}.",
            )
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentRevisionForm(
            organization=org,
            unit=unit,
            initial={
                "effective_month": today.month,
                "effective_year": today.year,
                "monthly_rent": unit.current_rent(today),
            },
        )

    return render(
        request,
        "rentals/revision_form.html",
        {"form": form, "unit": unit},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def revision_edit(request, pk):
    """Correct a recorded rent change — the effective month or the new amount."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    revision = get_object_or_404(
        RentRevision.objects.select_related("unit"), pk=pk, organization=org
    )
    unit = revision.unit

    if request.method == "POST":
        form = RentRevisionForm(
            request.POST, instance=revision, organization=org, unit=unit
        )
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated the rent change for {unit.name}.")
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentRevisionForm(instance=revision, organization=org, unit=unit)

    return render(
        request,
        "rentals/revision_form.html",
        {"form": form, "unit": unit, "revision": revision, "is_edit": True},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def revision_delete(request, pk):
    """Remove a rent change. The rent then reverts to whatever was in force before
    it — arrears recompute accordingly."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    revision = get_object_or_404(
        RentRevision.objects.select_related("unit"), pk=pk, organization=org
    )
    unit = revision.unit

    if request.method == "POST":
        label = revision.effective_label
        revision.delete()
        messages.success(
            request, f"Removed the rent change from {label} on {unit.name}."
        )
        return redirect("rentals:unit_detail", pk=unit.pk)

    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": f"Remove rent change from {revision.effective_label}?",
            "message": (
                f"This drops the {revision.monthly_rent} {unit.currency} rent that "
                f"took effect from {revision.effective_label} on {unit.name}."
            ),
            "consequences": [
                "The rent reverts to whatever was in force before this change, and "
                "arrears recompute.",
                "This cannot be undone.",
            ],
            "confirm_label": "Remove change",
            "cancel_url": reverse("rentals:unit_detail", args=[unit.pk]),
        },
    )


# --- Rent rebates / concessions --------------------------------------------


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def adjustment_add(request, unit_pk):
    """Grant a rebate against one month's rent (poor condition, goodwill, ...). It
    credits the tenant's statement and posts a matching expense to Finance so the
    concession is visible in the books."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(RentalUnit, pk=unit_pk, organization=org)
    today = timezone.localdate()

    if request.method == "POST":
        form = RentAdjustmentForm(request.POST, organization=org, unit=unit)
        if form.is_valid():
            # Save the rebate and its mirroring finance expense together, so the
            # books can never end up with one but not the other.
            with db_transaction.atomic():
                adjustment = form.save(commit=False)
                adjustment.recorded_by = request.user
                adjustment.save()
                _post_rebate_to_finance(org, unit, adjustment, request.user)

            messages.success(
                request,
                f"Rebate of {adjustment.amount} {adjustment.currency} recorded for "
                f"{unit.name} ({adjustment.period_label}) and posted to Finance.",
            )
            return redirect("rentals:unit_detail", pk=unit.pk)
    else:
        form = RentAdjustmentForm(
            organization=org,
            unit=unit,
            initial={
                "period_month": today.month,
                "period_year": today.year,
                "dated_on": today,
            },
        )

    return render(
        request,
        "rentals/adjustment_form.html",
        {"form": form, "unit": unit},
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def adjustment_delete(request, pk):
    """Void a rebate and reverse its finance expense entry together, so the
    statement and the books are never left disagreeing."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    adjustment = get_object_or_404(
        RentAdjustment.objects.select_related("unit", "transaction"),
        pk=pk,
        organization=org,
    )
    unit = adjustment.unit

    if request.method == "POST":
        with db_transaction.atomic():
            txn = adjustment.transaction
            adjustment.delete()
            if txn is not None:
                txn.delete()
        messages.success(
            request, "Voided the rebate and reversed its finance entry."
        )
        return redirect("rentals:unit_detail", pk=unit.pk)

    return render(
        request,
        "rentals/confirm_delete.html",
        {
            "title": "Void this rebate?",
            "message": (
                f"This removes the {adjustment.amount} {adjustment.currency} rebate "
                f"({adjustment.reason}) for {adjustment.period_label} on {unit.name}."
            ),
            "consequences": [
                "The matching finance expense entry will be reversed.",
                "What the tenant owes goes back up by the rebate amount.",
                "This cannot be undone.",
            ],
            "confirm_label": "Void rebate",
            "cancel_url": reverse("rentals:unit_detail", args=[unit.pk]),
        },
    )


# --- Printable slips (demand + receipt) ------------------------------------


def _serve_slip(request, template, context, filename, back_url):
    """Serve a slip either as a printable HTML page or, on ``?format=pdf``, as a
    downloaded PDF. When WeasyPrint isn't available on the host the PDF request
    falls back to the printable page with a hint, so the link never 500s."""
    context = {**context, "back_url": back_url}
    if request.GET.get("format") == "pdf":
        pdf = render_pdf(request, template, context, filename)
        if pdf is not None:
            return pdf
        messages.info(
            request,
            "Direct PDF export isn’t enabled on this server — use the Print "
            "button and choose “Save as PDF”.",
        )
    return render(request, template, context)


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def payment_slip(request, pk):
    """The rent receipt for one payment — proof the tenant paid. Viewable,
    printable, and downloadable as PDF (`?format=pdf`)."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    payment = get_object_or_404(
        RentPayment.objects.select_related(
            "unit", "unit__property_type", "recorded_by"
        ),
        pk=pk,
        organization=org,
    )
    return _serve_slip(
        request,
        "rentals/receipt_slip.html",
        receipt_context(payment),
        f"rent-receipt-{payment.receipt_number}.pdf",
        reverse("rentals:unit_detail", args=[payment.unit_id]),
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def unit_demand(request, pk):
    """The rent demand for one unit — a bill of what's owed, drawn from the unit's
    running statement. Viewable, printable, and downloadable as PDF."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    unit = get_object_or_404(
        RentalUnit.objects.select_related("property_type"), pk=pk, organization=org
    )
    return _serve_slip(
        request,
        "rentals/demand_slip.html",
        demand_context(unit),
        f"rent-demand-{unit.pk}.pdf",
        reverse("rentals:unit_detail", args=[unit.pk]),
    )


@login_required
@feature_gate("rentals", "Rentals")
@require_cap(Cap.RENTALS_ACCESS)
def payments_export(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    payments = (
        RentPayment.objects.filter(organization=org)
        .select_related("unit", "unit__property_type")
        .order_by("paid_on", "receipt_number")
    )

    response = HttpResponse(content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}-rent-{stamp}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        ["Receipt", "Paid on", "Unit", "Type", "Tenant", "Period",
         "Method", "Amount", "Currency", "Reference"]
    )
    for p in payments:
        writer.writerow(
            [
                p.receipt_number,
                p.paid_on.isoformat(),
                p.unit.name,
                p.unit.property_type.name if p.unit.property_type else "",
                p.unit.tenant_name,
                p.period_label,
                p.get_method_display(),
                p.amount,
                p.currency,
                p.reference,
            ]
        )
    return response
