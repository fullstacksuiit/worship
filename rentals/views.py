from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, ProtectedError, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.permissions import cap_required, has_cap

from .forms import (
    BookingForm, BookingPaymentForm, PropertyForm, RentPaymentForm, TenancyForm,
)
from .models import Booking, Property, RentPayment, Tenancy, amount_in_words, money

# Where properties with no type of their own are shown.
OTHER = "Other"


# --- Bookings ---------------------------------------------------------------

@login_required
def booking_list(request):
    org = request.organization
    today = timezone.localdate()
    bookings = (
        Booking.objects.filter(organization=org)
        .select_related("property")
        # So a row can say what's still to collect without asking per row.
        .annotate(paid_total=Coalesce(
            Sum("payments__amount"), Decimal("0"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ))
    )
    upcoming = bookings.filter(end_date__gte=today).exclude(status=Booking.CANCELLED).order_by("start_date")
    past = bookings.filter(end_date__lt=today).order_by("-start_date")
    cancelled = bookings.filter(status=Booking.CANCELLED).order_by("-start_date")
    properties = Property.objects.filter(organization=org)
    return render(request, "rentals/list.html", {
        "upcoming": upcoming, "past": past, "cancelled": cancelled,
        "properties": properties,
        "bookable": properties.filter(is_active=True, rental_mode=Property.BOOKING),
        # Shown on the way through to the tenants screen, so rent owed by a
        # monthly tenant isn't invisible from the bookings side.
        "arrears": _total_arrears(org),
    })


def _total_arrears(org):
    """What every current tenant owes, added up."""
    total = Decimal("0")
    for tenancy in Tenancy.objects.filter(organization=org).select_related("property"):
        if tenancy.is_running:
            total += max(tenancy.ledger()["outstanding"], Decimal("0"))
    return total


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk, organization=request.organization)
    return render(request, "rentals/detail.html", {"booking": booking})


@login_required
@cap_required("manage_rentals")
def booking_add(request):
    org = request.organization
    if not Property.objects.filter(
        organization=org, is_active=True, rental_mode=Property.BOOKING
    ).exists():
        messages.info(request, "Add a property you can book first, then you can book it.")
        return redirect("rentals:property_add")
    if request.method == "POST":
        form = BookingForm(request.POST, org=org)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.organization = org
            booking.save()
            messages.success(request, "Booking created.")
            return redirect("rentals:detail", pk=booking.pk)
    else:
        form = BookingForm(org=org)
    return render(request, "rentals/form.html", {"form": form, "mode": "add"})


@login_required
@cap_required("manage_rentals")
def booking_edit(request, pk):
    org = request.organization
    booking = get_object_or_404(Booking, pk=pk, organization=org)
    if request.method == "POST":
        form = BookingForm(request.POST, instance=booking, org=org)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("rentals:detail", pk=booking.pk)
    else:
        form = BookingForm(instance=booking, org=org)
    return render(request, "rentals/form.html", {"form": form, "mode": "edit", "booking": booking})


@login_required
@cap_required("manage_rentals")
def booking_delete(request, pk):
    booking = get_object_or_404(Booking, pk=pk, organization=request.organization)
    if request.method == "POST":
        booking.delete()
        messages.success(request, "Booking removed.")
        return redirect("rentals:list")
    return render(request, "rentals/confirm_delete.html", {"booking": booking})


@login_required
@cap_required("record_rent")
def booking_payment_add(request, pk):
    """Record rent received on a booking — and put it in the books.

    Replaces the old "mark as paid" tick. A tick said the money had come in but
    left no trace of when, from whom or in what form, and the Money ledger never
    heard about it at all.
    """
    booking = get_object_or_404(
        Booking, pk=pk, organization=request.organization
    )
    if request.method == "POST":
        form = BookingPaymentForm(request.POST, booking=booking)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.organization = booking.organization
            payment.booking = booking
            payment.save()
            messages.success(
                request,
                f"{payment.amount_display} received — added to Money as income.",
            )
            return redirect("rentals:detail", pk=booking.pk)
    else:
        form = BookingPaymentForm(booking=booking)
    return render(request, "rentals/payment_form.html", {
        "form": form, "mode": "add", "booking": booking,
        "outstanding": max(booking.balance, Decimal("0")),
    })


@login_required
@cap_required("manage_rentals")
def booking_cancel(request, pk):
    booking = get_object_or_404(Booking, pk=pk, organization=request.organization)
    if request.method == "POST":
        booking.status = Booking.CANCELLED
        booking.save(update_fields=["status"])
        messages.success(request, "Booking cancelled.")
    return redirect("rentals:detail", pk=booking.pk)


# --- Properties -------------------------------------------------------------

@login_required
def property_list(request):
    """Everything this place rents out, grouped under the place's own labels.

    Grouping by category is what makes a long list readable — eight shops and
    two halls read as two short lists, not one wall of ten.
    """
    properties = (
        Property.objects.filter(organization=request.organization)
        .select_related("category")
    )
    groups = {}
    for prop in properties:
        groups.setdefault(prop.category.name if prop.category_id else OTHER, []).append(prop)
    return render(request, "rentals/properties.html", {
        "properties": properties,
        # The place's own labels in its own order, with the catch-all last —
        # "Other" is where things land, not a group anyone named.
        "groups": sorted(groups.items(), key=lambda g: (g[0] == OTHER, g[0].lower())),
        "needs_rate": [p for p in properties if not p.has_rate],
    })


@login_required
@cap_required("manage_rentals")
def property_add(request):
    org = request.organization
    if request.method == "POST":
        form = PropertyForm(request.POST, org=org)
        if form.is_valid():
            prop = form.save(commit=False)
            prop.organization = org
            prop.save()
            messages.success(request, f"“{prop.name}” added — {prop.rate_display}.")
            return redirect("rentals:property_list")
    else:
        form = PropertyForm(org=org)
    return render(request, "rentals/property_form.html", {"form": form, "mode": "add"})


@login_required
@cap_required("manage_rentals")
def property_edit(request, pk):
    org = request.organization
    prop = get_object_or_404(Property, pk=pk, organization=org)
    if request.method == "POST":
        form = PropertyForm(request.POST, instance=prop, org=org)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("rentals:property_list")
    else:
        form = PropertyForm(instance=prop, org=org)
    return render(request, "rentals/property_form.html", {"form": form, "mode": "edit", "property": prop})


@login_required
@cap_required("manage_rentals")
def property_delete(request, pk):
    prop = get_object_or_404(Property, pk=pk, organization=request.organization)
    if request.method == "POST":
        try:
            prop.delete()
            messages.success(request, "Property removed.")
        except ProtectedError:
            messages.error(
                request,
                "Can't delete — this property has bookings or tenants on record. "
                "Mark it inactive instead.",
            )
            return redirect("rentals:property_list")
        return redirect("rentals:property_list")
    return render(request, "rentals/property_confirm_delete.html", {"property": prop})


# --- Tenants: units let by the month ----------------------------------------

@login_required
def tenancy_list(request):
    """Every unit let by the month — who's in it, and what they owe.

    The arrears total at the top is the whole point of the screen: it's the one
    number a committee asks for, and until now it lived in somebody's notebook.
    """
    org = request.organization
    units = (
        Property.objects.filter(organization=org, rental_mode=Property.TENANCY)
        .select_related("category")
    )
    rows, vacant, arrears, monthly = [], [], Decimal("0"), Decimal("0")
    for unit in units:
        tenancy = unit.current_tenancy
        if tenancy is None:
            vacant.append(unit)
            continue
        # Reading the page is what brings each account up to date — see
        # `Tenancy.ensure_charges`.
        ledger = tenancy.ledger()
        rows.append({"unit": unit, "tenancy": tenancy, "ledger": ledger})
        arrears += max(ledger["outstanding"], Decimal("0"))
        monthly += tenancy.monthly_rent
    return render(request, "rentals/tenancies.html", {
        # Whoever owes most, first — the list is read to decide who to chase.
        "rows": sorted(rows, key=lambda r: -r["ledger"]["outstanding"]),
        "vacant": vacant,
        "arrears": arrears,
        "monthly": monthly,
        "owing": [r for r in rows if r["ledger"]["outstanding"] > 0],
        "has_units": units.exists(),
    })


@login_required
def tenancy_detail(request, pk):
    """One tenant's account: every month charged, everything paid, what's left."""
    org = request.organization
    tenancy = get_object_or_404(
        Tenancy.objects.select_related("property", "member"), pk=pk, organization=org
    )
    ledger = tenancy.ledger()
    form = None
    if has_cap(request.user, "record_rent") and ledger["charges"]:
        form = RentPaymentForm(tenancy=tenancy)
        # Arriving from a month's "Record payment" button: start on that month.
        month = request.GET.get("month")
        if month and form.fields["charge"].queryset.filter(pk=month).exists():
            form.fields["charge"].initial = int(month)
    return render(request, "rentals/tenancy_detail.html", {
        "tenancy": tenancy,
        "ledger": ledger,
        "payments": tenancy.payments.select_related("charge").all(),
        "form": form,
    })


@login_required
@cap_required("manage_rentals")
def tenancy_add(request):
    org = request.organization
    if not Property.objects.filter(
        organization=org, is_active=True, rental_mode=Property.TENANCY
    ).exists():
        messages.info(
            request,
            "Add the unit first — a shop or room let to one tenant monthly — "
            "then you can put a tenant in it.",
        )
        return redirect("rentals:property_add")
    if request.method == "POST":
        form = TenancyForm(request.POST, org=org)
        if form.is_valid():
            tenancy = form.save(commit=False)
            tenancy.organization = org
            tenancy.save()
            # Raise the months this tenancy has already run for, so the account
            # is true the moment it's created rather than on the next visit.
            tenancy.carry_in_opening_balance()
            raised = tenancy.ensure_charges()
            messages.success(
                request,
                f"{tenancy.tenant_name} added — {tenancy.rent_display}."
                + (f" {raised} month{'s' if raised != 1 else ''} charged so far." if raised else ""),
            )
            return redirect("rentals:tenancy_detail", pk=tenancy.pk)
    else:
        form = TenancyForm(org=org)
    return render(request, "rentals/tenancy_form.html", {"form": form, "mode": "add"})


@login_required
@cap_required("manage_rentals")
def tenancy_edit(request, pk):
    org = request.organization
    tenancy = get_object_or_404(Tenancy, pk=pk, organization=org)
    if request.method == "POST":
        form = TenancyForm(request.POST, instance=tenancy, org=org)
        if form.is_valid():
            form.save()
            # Months already charged keep the rent they were charged at; only
            # months not yet raised pick up a new figure.
            tenancy.ensure_charges()
            messages.success(request, "Changes saved.")
            return redirect("rentals:tenancy_detail", pk=tenancy.pk)
    else:
        form = TenancyForm(instance=tenancy, org=org)
    return render(request, "rentals/tenancy_form.html", {
        "form": form, "mode": "edit", "tenancy": tenancy,
    })


@login_required
@cap_required("manage_rentals")
def tenancy_end(request, pk):
    """Move a tenant out. The account stays, arrears and all."""
    tenancy = get_object_or_404(Tenancy, pk=pk, organization=request.organization)
    if request.method == "POST":
        tenancy.ensure_charges()
        tenancy.end_date = timezone.localdate()
        tenancy.save(update_fields=["end_date"])
        messages.success(
            request,
            f"{tenancy.tenant_name} moved out. The account stays here — "
            "no more months will be charged.",
        )
    return redirect("rentals:tenancy_detail", pk=tenancy.pk)


@login_required
@cap_required("manage_rentals")
def tenancy_delete(request, pk):
    tenancy = get_object_or_404(Tenancy, pk=pk, organization=request.organization)
    if request.method == "POST":
        tenancy.delete()
        messages.success(
            request, "Tenant removed, along with their rent account and its Money rows."
        )
        return redirect("rentals:tenancy_list")
    return render(request, "rentals/tenancy_confirm_delete.html", {
        "tenancy": tenancy, "ledger": tenancy.ledger(refresh=False),
    })


# --- Rent received ----------------------------------------------------------

@login_required
@cap_required("record_rent")
def payment_add(request, pk):
    """Record rent handed over against a month — and post it to the books."""
    org = request.organization
    tenancy = get_object_or_404(Tenancy, pk=pk, organization=org)
    if request.method == "POST":
        form = RentPaymentForm(request.POST, tenancy=tenancy)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.organization = org
            payment.tenancy = tenancy
            payment.save()
            messages.success(
                request,
                f"{payment.amount_display} received for {payment.charge.label} — "
                "added to Money as income.",
            )
            return redirect("rentals:tenancy_detail", pk=tenancy.pk)
        # Fall through so the ledger page can show the form with its errors.
        return render(request, "rentals/tenancy_detail.html", {
            "tenancy": tenancy,
            "ledger": tenancy.ledger(),
            "payments": tenancy.payments.select_related("charge").all(),
            "form": form,
        })
    return redirect("rentals:tenancy_detail", pk=tenancy.pk)


@login_required
@cap_required("record_rent")
def payment_edit(request, pk):
    """Correct a payment. The Money row it wrote is corrected with it."""
    payment = get_object_or_404(
        RentPayment.objects.select_related("tenancy", "booking"),
        pk=pk, organization=request.organization, is_opening=False,
    )
    if payment.tenancy_id:
        form_class, kwargs = RentPaymentForm, {"tenancy": payment.tenancy}
    else:
        form_class, kwargs = BookingPaymentForm, {"booking": payment.booking}
    if request.method == "POST":
        form = form_class(request.POST, instance=payment, **kwargs)
        if form.is_valid():
            form.save()
            messages.success(request, "Payment corrected, in Money too.")
            return redirect(_payment_home(payment))
    else:
        form = form_class(instance=payment, **kwargs)
    return render(request, "rentals/payment_form.html", {
        "form": form, "mode": "edit", "payment": payment,
        "booking": payment.booking, "tenancy": payment.tenancy,
    })


@login_required
@cap_required("record_rent")
def payment_delete(request, pk):
    payment = get_object_or_404(
        RentPayment.objects.select_related("tenancy", "booking"),
        pk=pk, organization=request.organization, is_opening=False,
    )
    home = _payment_home(payment)
    if request.method == "POST":
        payment.delete()
        messages.success(
            request, "Payment removed — its income row in Money has gone too."
        )
        return redirect(home)
    return render(request, "rentals/payment_confirm_delete.html", {"payment": payment})


def _payment_home(payment):
    """Back to whatever the payment was for."""
    if payment.tenancy_id:
        return reverse("rentals:tenancy_detail", args=[payment.tenancy_id])
    return reverse("rentals:detail", args=[payment.booking_id])


# --- Slips: rent demand and payment receipt ---------------------------------
# Both render a standalone, print-clean page — no app chrome — that a browser
# turns into a PDF with "Save as PDF". No library, nothing to install, and it
# works on the laptop-with-no-network this often runs on.

@login_required
def rent_demand(request, pk):
    """A printable rent demand — what this tenant owes, month by month, to hand over."""
    org = request.organization
    tenancy = get_object_or_404(
        Tenancy.objects.select_related("property", "property__category", "member"),
        pk=pk, organization=org,
    )
    # Reading the slip brings the account up to date, same as the detail page.
    ledger = tenancy.ledger()
    total_due = max(ledger["outstanding"], Decimal("0"))
    return render(request, "rentals/slips/rent_demand.html", {
        "tenancy": tenancy,
        "ledger": ledger,
        "unpaid": ledger["unpaid"],
        "total_due": total_due,
        "total_due_display": money(org, total_due),
        "amount_words": amount_in_words(org, total_due),
        "today": timezone.localdate(),
        "back_url": reverse("rentals:tenancy_detail", args=[tenancy.pk]),
    })


@login_required
def payment_receipt(request, pk):
    """A printable receipt for one rent payment — of a monthly tenant or a booking."""
    org = request.organization
    payment = get_object_or_404(
        RentPayment.objects.select_related(
            "tenancy__property", "charge__tenancy__property", "booking__property",
        ),
        pk=pk, organization=org,
    )
    # What's still owed after this payment, for the account it belongs to — so
    # the receipt can say "and this clears you" or "₹2,000 still to come".
    if payment.charge_id or payment.tenancy_id:
        tenancy = payment.charge.tenancy if payment.charge_id else payment.tenancy
        balance = max(tenancy.ledger()["outstanding"], Decimal("0"))
    elif payment.booking_id:
        balance = max(payment.booking.balance, Decimal("0"))
    else:
        balance = None
    return render(request, "rentals/slips/payment_receipt.html", {
        "payment": payment,
        "balance": balance,
        "balance_display": money(org, balance) if balance is not None else None,
        "amount_words": amount_in_words(org, payment.amount),
        "today": timezone.localdate(),
        "back_url": _payment_home(payment),
    })
