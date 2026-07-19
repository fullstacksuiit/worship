import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from billing.access import feature_gate

from core.permissions import Cap, require_cap

from .forms import AttendanceForm, EventForm
from .models import Event, EventKind, Recurrence, next_weekday_at, suggestions_for


def _require_org(request):
    """Return the current org or None — the same 'no tenant' guard the other apps
    use so a membership-less user is handled consistently."""
    return getattr(request, "organization", None)


def _no_org(request):
    return render(request, "donations/no_org.html")


def _suggestion_links(org):
    """Build the quick-start suggestions for an empty schedule: each carries a
    pre-filled link to the new-event form (title, kind, recurrence, and the next
    sensible date/time already chosen) so a regular service is one click away."""
    base = reverse("events:event_create")
    links = []
    for title, kind, weekday, hour, recurrence in suggestions_for(org.faith_tradition):
        when = next_weekday_at(weekday, hour)
        query = (
            f"?title={title}&kind={kind}&recurrence={recurrence}"
            f"&starts_at={when:%Y-%m-%dT%H:%M}"
        )
        links.append(
            {
                "title": title,
                "kind_label": EventKind(kind).label,
                "when": when,
                "url": base + query,
            }
        )
    return links


# --- Overview --------------------------------------------------------------


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def overview(request):
    """The events hub: what's coming up, what still needs a headcount, and a few
    at-a-glance figures on how gatherings are attended this year."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    now = timezone.now()
    today = timezone.localdate()
    year = today.year
    week_end = now + timezone.timedelta(days=7)

    events = Event.objects.filter(organization=org).select_related("lead")

    upcoming = list(events.filter(starts_at__gte=now).order_by("starts_at")[:12])
    awaiting = list(
        events.filter(starts_at__lt=now, attendance__isnull=True).order_by(
            "-starts_at"
        )[:12]
    )

    this_year = events.filter(starts_at__year=year)
    attendance_stats = this_year.filter(attendance__isnull=False).aggregate(
        total=Sum("attendance"), avg=Avg("attendance"), counted=Count("id")
    )

    context = {
        "upcoming": upcoming,
        "awaiting": awaiting,
        "year": year,
        "total_events": events.count(),
        "upcoming_count": events.filter(starts_at__gte=now).count(),
        "this_week_count": events.filter(
            starts_at__gte=now, starts_at__lte=week_end
        ).count(),
        "events_this_year": this_year.count(),
        "attendance_total": attendance_stats["total"] or 0,
        "attendance_avg": round(attendance_stats["avg"]) if attendance_stats["avg"] else 0,
        "attendance_counted": attendance_stats["counted"] or 0,
        "suggestions": _suggestion_links(org) if events.count() == 0 else [],
    }
    return render(request, "events/overview.html", context)


# --- Full schedule ---------------------------------------------------------


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def schedule(request):
    """The complete chronological record of gatherings, filterable by kind and by
    time (upcoming / past / all), with a CSV export of whatever is shown."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    now = timezone.now()
    events = Event.objects.filter(organization=org).select_related("lead")

    kind = request.GET.get("kind") or ""
    if kind in EventKind.values:
        events = events.filter(kind=kind)

    when = request.GET.get("when") or "upcoming"
    if when == "past":
        events = events.filter(starts_at__lt=now).order_by("-starts_at")
    elif when == "all":
        events = events.order_by("-starts_at")
    else:
        when = "upcoming"
        events = events.filter(starts_at__gte=now).order_by("starts_at")

    context = {
        "events": events,
        "kinds": EventKind.choices,
        "selected_kind": kind,
        "when": when,
        "when_tabs": [
            ("upcoming", "Upcoming"),
            ("past", "Past"),
            ("all", "All"),
        ],
    }
    return render(request, "events/schedule.html", context)


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def export_csv(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    events = (
        Event.objects.filter(organization=org)
        .select_related("lead")
        .order_by("starts_at")
    )

    response = HttpResponse(content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}-events-{stamp}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        ["Title", "Type", "Starts", "Ends", "Location", "Led by",
         "Repeats", "Expected", "Attendance"]
    )
    for e in events:
        writer.writerow(
            [
                e.title,
                e.get_kind_display(),
                timezone.localtime(e.starts_at).strftime("%Y-%m-%d %H:%M"),
                timezone.localtime(e.ends_at).strftime("%Y-%m-%d %H:%M") if e.ends_at else "",
                e.location,
                e.lead.full_name if e.lead else "",
                e.get_recurrence_display(),
                e.expected_attendance if e.expected_attendance is not None else "",
                e.attendance if e.attendance is not None else "",
            ]
        )
    return response


# --- Create / edit / detail / delete --------------------------------------


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def event_create(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if request.method == "POST":
        form = EventForm(request.POST, organization=org)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            messages.success(request, f"“{event.title}” added to the schedule.")
            return redirect("events:event_detail", pk=event.pk)
    else:
        # Pre-fill from a quick-start suggestion or sensible blank defaults.
        initial = {}
        for field in ("title", "starts_at"):
            if request.GET.get(field):
                initial[field] = request.GET[field]
        kind = request.GET.get("kind")
        if kind in EventKind.values:
            initial["kind"] = kind
        recurrence = request.GET.get("recurrence")
        if recurrence in Recurrence.values:
            initial["recurrence"] = recurrence
        form = EventForm(organization=org, initial=initial)

    return render(request, "events/event_form.html", {"form": form, "is_edit": False})


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def event_edit(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    event = get_object_or_404(Event, pk=pk, organization=org)
    if request.method == "POST":
        form = EventForm(request.POST, instance=event, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated “{event.title}”.")
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm(instance=event, organization=org)

    return render(
        request,
        "events/event_form.html",
        {"form": form, "is_edit": True, "event": event},
    )


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def event_detail(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    event = get_object_or_404(
        Event.objects.select_related("lead"), pk=pk, organization=org
    )
    return render(
        request,
        "events/event_detail.html",
        {"event": event, "attendance_form": AttendanceForm(instance=event)},
    )


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def event_delete(request, pk):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    event = get_object_or_404(Event, pk=pk, organization=org)
    if request.method == "POST":
        title = event.title
        event.delete()
        messages.success(request, f"Removed “{title}” from the schedule.")
        return redirect("events:overview")

    return render(
        request,
        "events/confirm_delete.html",
        {
            "title": f"Remove “{event.title}”?",
            "message": (
                f"This deletes the {event.get_kind_display().lower()} scheduled for "
                f"{timezone.localtime(event.starts_at):%A %d %B %Y, %H:%M}"
                + (f" and its recorded attendance of {event.attendance}."
                   if event.attendance is not None else ".")
            ),
            "consequences": ["This cannot be undone."],
            "confirm_label": "Remove event",
            "cancel_url": reverse("events:event_detail", args=[event.pk]),
        },
    )


# --- Attendance & recurrence shortcuts -------------------------------------


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def record_attendance(request, pk):
    """Save the headcount for a gathering. POST-only; the form lives inline on the
    detail and overview pages so recording attendance is a single step."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    event = get_object_or_404(Event, pk=pk, organization=org)
    if request.method == "POST":
        form = AttendanceForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Recorded {event.attendance} at “{event.title}”.",
            )
        else:
            messages.error(request, "Enter a valid number of attendees.")
    # Return where the user came from when we can, else the event page.
    nxt = request.POST.get("next")
    if nxt == "overview":
        return redirect("events:overview")
    return redirect("events:event_detail", pk=event.pk)


@login_required
@feature_gate("events", "Events & Services")
@require_cap(Cap.EVENTS_ACCESS)
def event_duplicate(request, pk):
    """Schedule the next occurrence of a repeating gathering — copies its details
    forward by one interval, leaving attendance blank for the new date. POST-only."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    event = get_object_or_404(Event, pk=pk, organization=org)
    if request.method != "POST":
        return redirect("events:event_detail", pk=event.pk)

    next_start = event.next_occurrence_start()
    if next_start is None:
        messages.info(request, "This is a one-off event, so there's nothing to repeat.")
        return redirect("events:event_detail", pk=event.pk)

    duration = (event.ends_at - event.starts_at) if event.ends_at else None
    new_event = Event.objects.create(
        organization=org,
        title=event.title,
        kind=event.kind,
        starts_at=next_start,
        ends_at=(next_start + duration) if duration else None,
        location=event.location,
        lead=event.lead,
        description=event.description,
        recurrence=event.recurrence,
        expected_attendance=event.expected_attendance,
        created_by=request.user,
    )
    messages.success(
        request,
        f"Scheduled the next “{new_event.title}” for "
        f"{timezone.localtime(new_event.starts_at):%A %d %B, %H:%M}.",
    )
    return redirect("events:event_detail", pk=new_event.pk)
