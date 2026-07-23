from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.permissions import cap_required

from .forms import BookingForm, PropertyForm
from .models import Booking, Property

# Where properties with no type of their own are shown.
OTHER = "Other"


# --- Bookings ---------------------------------------------------------------

@login_required
def booking_list(request):
    org = request.organization
    today = timezone.localdate()
    bookings = Booking.objects.filter(organization=org).select_related("property")
    upcoming = bookings.filter(end_date__gte=today).exclude(status=Booking.CANCELLED).order_by("start_date")
    past = bookings.filter(end_date__lt=today).order_by("-start_date")
    cancelled = bookings.filter(status=Booking.CANCELLED).order_by("-start_date")
    properties = Property.objects.filter(organization=org)
    return render(request, "rentals/list.html", {
        "upcoming": upcoming, "past": past, "cancelled": cancelled,
        "properties": properties,
        "bookable": properties.filter(is_active=True, rental_mode=Property.BOOKING),
    })


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
@cap_required("manage_rentals")
def booking_mark_paid(request, pk):
    booking = get_object_or_404(Booking, pk=pk, organization=request.organization)
    if request.method == "POST":
        booking.is_paid = True
        booking.save(update_fields=["is_paid"])
        messages.success(request, "Marked as paid.")
    return redirect("rentals:detail", pk=booking.pk)


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
            messages.error(request, "Can't delete — this property has bookings. Mark it inactive instead.")
            return redirect("rentals:property_list")
        return redirect("rentals:property_list")
    return render(request, "rentals/property_confirm_delete.html", {"property": prop})
