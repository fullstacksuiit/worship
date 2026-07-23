from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.permissions import cap_required
from members.models import Member

from .forms import EventForm
from .models import Event


@login_required
def event_list(request):
    org = request.organization
    now = timezone.now()
    events = Event.objects.filter(organization=org).select_related("category")
    upcoming = events.filter(start__gte=now).order_by("start")
    past = events.filter(start__lt=now).order_by("-start")
    return render(request, "events/list.html", {"upcoming": upcoming, "past": past})


@login_required
@cap_required("manage_events")
def event_add(request):
    if request.method == "POST":
        form = EventForm(request.POST, org=request.organization)
        if form.is_valid():
            event = form.save(commit=False)
            event.organization = request.organization
            event.save()
            messages.success(request, f"“{event.title}” scheduled.")
            return redirect("events:detail", pk=event.pk)
    else:
        form = EventForm(org=request.organization)
    return render(request, "events/form.html", {"form": form, "mode": "add"})


@login_required
def event_detail(request, pk):
    org = request.organization
    event = get_object_or_404(Event, pk=pk, organization=org)
    members = Member.objects.filter(organization=org, is_active=True)
    attending_ids = set(event.attendees.values_list("id", flat=True))
    return render(request, "events/detail.html", {
        "event": event, "members": members, "attending_ids": attending_ids,
    })


@login_required
@cap_required("manage_events")
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk, organization=request.organization)
    if request.method == "POST":
        form = EventForm(request.POST, instance=event, org=request.organization)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("events:detail", pk=event.pk)
    else:
        form = EventForm(instance=event, org=request.organization)
    return render(request, "events/form.html", {"form": form, "mode": "edit", "event": event})


@login_required
@cap_required("manage_events")
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk, organization=request.organization)
    if request.method == "POST":
        title = event.title
        event.delete()
        messages.success(request, f"“{title}” removed.")
        return redirect("events:list")
    return render(request, "events/confirm_delete.html", {"event": event})


@login_required
@cap_required("manage_events")
def event_attendance(request, pk):
    """Save which members attended (checkbox list on the detail page)."""
    org = request.organization
    event = get_object_or_404(Event, pk=pk, organization=org)
    if request.method == "POST":
        ids = request.POST.getlist("attendees")
        members = Member.objects.filter(organization=org, id__in=ids)
        event.attendees.set(members)
        messages.success(request, f"Attendance saved — {len(members)} present.")
    return redirect("events:detail", pk=event.pk)
