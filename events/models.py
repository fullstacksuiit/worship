from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import FaithTradition, Member, TenantScopedModel


class EventKind(models.TextChoices):
    """What sort of gathering this is. Faith-neutral buckets that fit every
    tradition — the title carries the specific name (Jummah, Mass, Aarti, …)."""

    SERVICE = "service", "Service / Worship"
    FESTIVAL = "festival", "Festival / Special"
    CLASS = "class", "Class / Study"
    MEETING = "meeting", "Meeting"
    LIFECYCLE = "lifecycle", "Lifecycle (wedding, funeral…)"
    COMMUNITY = "community", "Community / Outreach"
    OTHER = "other", "Other"


class Recurrence(models.TextChoices):
    """How often a gathering repeats. Stored as a label on the event — the system
    doesn't auto-generate a series, it powers the one-click 'add next' shortcut
    and an 'every week / month' badge, which keeps the model simple to reason
    about while still being quick to keep a regular schedule going."""

    NONE = "none", "One-off"
    DAILY = "daily", "Every day"
    WEEKLY = "weekly", "Every week"
    FORTNIGHTLY = "fortnightly", "Every two weeks"
    MONTHLY = "monthly", "Every month"


# Suggested regular services to offer as one-click quick-starts on an empty
# schedule, per faith. Each entry is (title, kind, weekday, hour, recurrence)
# where weekday is Mon=0 … Sun=6. These only pre-fill the new-event form — the
# organiser confirms the details — so the system never imposes a fixed calendar.
EVENT_SUGGESTIONS = {
    FaithTradition.ISLAM: [
        ("Jummah (Friday Prayer)", EventKind.SERVICE, 4, 13, Recurrence.WEEKLY),
        ("Quran Class", EventKind.CLASS, 5, 10, Recurrence.WEEKLY),
    ],
    FaithTradition.HINDUISM: [
        ("Sandhya Aarti", EventKind.SERVICE, 6, 18, Recurrence.WEEKLY),
        ("Bhajan & Satsang", EventKind.SERVICE, 6, 10, Recurrence.WEEKLY),
    ],
    FaithTradition.CHRISTIANITY: [
        ("Sunday Service", EventKind.SERVICE, 6, 10, Recurrence.WEEKLY),
        ("Bible Study", EventKind.CLASS, 2, 19, Recurrence.WEEKLY),
    ],
    FaithTradition.SIKHISM: [
        ("Weekly Diwan & Kirtan", EventKind.SERVICE, 6, 10, Recurrence.WEEKLY),
        ("Langar Seva", EventKind.COMMUNITY, 6, 12, Recurrence.WEEKLY),
    ],
    FaithTradition.BUDDHISM: [
        ("Meditation Session", EventKind.SERVICE, 6, 9, Recurrence.WEEKLY),
        ("Dharma Talk", EventKind.CLASS, 6, 11, Recurrence.WEEKLY),
    ],
    FaithTradition.JUDAISM: [
        ("Shabbat Service", EventKind.SERVICE, 5, 9, Recurrence.WEEKLY),
        ("Torah Study", EventKind.CLASS, 5, 8, Recurrence.WEEKLY),
    ],
    FaithTradition.JAINISM: [
        ("Daily Puja", EventKind.SERVICE, 6, 8, Recurrence.WEEKLY),
        ("Pratikraman", EventKind.SERVICE, 5, 18, Recurrence.WEEKLY),
    ],
    FaithTradition.BAHAI: [
        ("Devotional Gathering", EventKind.SERVICE, 6, 10, Recurrence.WEEKLY),
        ("Study Circle", EventKind.CLASS, 2, 19, Recurrence.WEEKLY),
    ],
}

# A couple of universal extras every tradition can use, appended to the above.
COMMON_SUGGESTIONS = [
    ("Committee Meeting", EventKind.MEETING, 0, 19, Recurrence.MONTHLY),
]


def suggestions_for(faith_tradition):
    """The quick-start service suggestions to show an organisation with an empty
    schedule, tailored to its faith and falling back to the common set."""
    return list(EVENT_SUGGESTIONS.get(faith_tradition, [])) + list(COMMON_SUGGESTIONS)


def next_weekday_at(weekday, hour, *, today=None):
    """The next date on or after today that falls on `weekday` (Mon=0…Sun=6),
    combined with `hour`:00 local time. Used to pre-fill a suggested event so the
    organiser lands on a sensible upcoming slot rather than an empty field."""
    today = today or timezone.localdate()
    ahead = (weekday - today.weekday()) % 7
    target = today + timedelta(days=ahead)
    return datetime.combine(target, time(hour=hour))


class Event(TenantScopedModel):
    """A scheduled gathering on an organisation's calendar — a regular service,
    a festival, a class, a committee meeting, a wedding or funeral. Attendance is
    recorded afterwards so an organisation can see how its gatherings are growing."""

    title = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=12, choices=EventKind.choices, default=EventKind.SERVICE
    )

    starts_at = models.DateTimeField()
    # Optional finish time; left blank for open-ended gatherings.
    ends_at = models.DateTimeField(null=True, blank=True)

    location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Where it's held, e.g. “Main hall”, “Prayer hall”.",
    )

    # Who is leading — a recorded member, kept if that member is later removed.
    lead = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_events",
    )

    description = models.TextField(blank=True)

    recurrence = models.CharField(
        max_length=12, choices=Recurrence.choices, default=Recurrence.NONE
    )

    expected_attendance = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="A planning estimate — how many you expect.",
    )
    # The headcount actually recorded after the gathering. NULL = not yet taken.
    attendance = models.PositiveIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_events",
    )

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["organization", "starts_at"]),
            models.Index(fields=["organization", "kind"]),
        ]

    def __str__(self):
        return f"{self.title} · {self.starts_at:%d %b %Y}"

    # --- Time helpers ------------------------------------------------------

    @property
    def is_past(self):
        """True once the gathering's finish (or its start, if open-ended) has
        passed — i.e. attendance can sensibly be recorded for it."""
        moment = self.ends_at or self.starts_at
        return moment < timezone.now()

    @property
    def is_today(self):
        return self.starts_at.date() == timezone.localdate()

    @property
    def awaiting_attendance(self):
        """A past gathering whose headcount hasn't been entered yet — surfaced as
        a gentle to-do so attendance figures don't quietly go missing."""
        return self.is_past and self.attendance is None

    @property
    def repeats(self):
        return self.recurrence != Recurrence.NONE

    def next_occurrence_start(self):
        """When the next gathering in this series would start, given its
        recurrence. Used by the one-click 'schedule the next one' shortcut.
        Returns None for one-offs."""
        start = self.starts_at
        if self.recurrence == Recurrence.DAILY:
            return start + timedelta(days=1)
        if self.recurrence == Recurrence.WEEKLY:
            return start + timedelta(weeks=1)
        if self.recurrence == Recurrence.FORTNIGHTLY:
            return start + timedelta(weeks=2)
        if self.recurrence == Recurrence.MONTHLY:
            # Advance one month, clamping the day to the target month's length.
            import calendar

            month = start.month + 1
            year = start.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(start.day, calendar.monthrange(year, month)[1])
            return start.replace(year=year, month=month, day=day)
        return None
