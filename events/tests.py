from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import Plan
from billing.services import start_subscription
from core.models import Member, Organization, OrgRole, UserOrgMembership

from .models import Event, EventKind, Recurrence, next_weekday_at, suggestions_for


def make_org(name="Test Org", slug="test-org", faith="islam"):
    return Organization.objects.create(
        name=name, slug=slug, faith_tradition=faith, currency="GBP"
    )


def make_event(org, **kwargs):
    defaults = dict(
        title="Sunday Service",
        kind=EventKind.SERVICE,
        starts_at=timezone.now() + timedelta(days=2),
    )
    defaults.update(kwargs)
    return Event.objects.create(organization=org, **defaults)


class EventModelTests(TestCase):
    def setUp(self):
        self.org = make_org()

    def test_is_past_and_awaiting_attendance(self):
        past = make_event(self.org, starts_at=timezone.now() - timedelta(days=1))
        self.assertTrue(past.is_past)
        self.assertTrue(past.awaiting_attendance)
        past.attendance = 50
        past.save()
        self.assertFalse(past.awaiting_attendance)

    def test_future_event_not_past(self):
        future = make_event(self.org, starts_at=timezone.now() + timedelta(days=1))
        self.assertFalse(future.is_past)
        self.assertFalse(future.awaiting_attendance)

    def test_is_past_uses_end_time_when_present(self):
        # Started in the past but still running -> not yet past.
        e = make_event(
            self.org,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(e.is_past)

    def test_repeats_flag(self):
        self.assertFalse(make_event(self.org).repeats)
        self.assertTrue(make_event(self.org, recurrence=Recurrence.WEEKLY).repeats)

    def test_next_occurrence_weekly(self):
        start = timezone.now().replace(microsecond=0)
        e = make_event(self.org, starts_at=start, recurrence=Recurrence.WEEKLY)
        self.assertEqual(e.next_occurrence_start(), start + timedelta(weeks=1))

    def test_next_occurrence_none_for_oneoff(self):
        self.assertIsNone(make_event(self.org, recurrence=Recurrence.NONE).next_occurrence_start())

    def test_next_weekday_at_lands_on_requested_day(self):
        # Friday = weekday 4.
        dt = next_weekday_at(4, 13)
        self.assertEqual(dt.weekday(), 4)
        self.assertEqual(dt.hour, 13)

    def test_suggestions_are_faith_aware(self):
        islam = suggestions_for("islam")
        self.assertTrue(any("Jummah" in s[0] for s in islam))
        # Falls back to the common set for an unknown faith, never empty.
        self.assertTrue(suggestions_for("unknown-faith"))


class EventViewTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.user = User.objects.create_user("owner", password="pw")
        UserOrgMembership.objects.create(
            user=self.user, organization=self.org,
            role=OrgRole.OWNER, is_default=True,
        )
        self.plan = Plan.objects.create(
            code="events-test", name="Events Test", tier=2,
            features={"events": True},
        )
        start_subscription(self.org, self.plan)
        self.client.force_login(self.user)

    def test_overview_renders_with_suggestions_when_empty(self):
        resp = self.client.get(reverse("events:overview"))
        self.assertEqual(resp.status_code, 200)
        # Empty schedule offers faith-aware quick-starts.
        self.assertTrue(resp.context["suggestions"])
        self.assertContains(resp, "Jummah")

    def test_create_event(self):
        start = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "title": "Eid Prayer",
                "kind": EventKind.FESTIVAL,
                "starts_at": start,
                "ends_at": "",
                "location": "Main hall",
                "lead": "",
                "recurrence": Recurrence.NONE,
                "expected_attendance": "300",
                "description": "",
            },
        )
        event = Event.objects.get(organization=self.org, title="Eid Prayer")
        self.assertRedirects(resp, reverse("events:event_detail", args=[event.pk]))
        self.assertEqual(event.created_by, self.user)
        self.assertEqual(event.expected_attendance, 300)

    def test_create_rejects_end_before_start(self):
        start = timezone.now() + timedelta(days=3)
        resp = self.client.post(
            reverse("events:event_create"),
            {
                "title": "Bad times",
                "kind": EventKind.SERVICE,
                "starts_at": start.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "location": "",
                "lead": "",
                "recurrence": Recurrence.NONE,
                "expected_attendance": "",
                "description": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Event.objects.filter(title="Bad times").exists())

    def test_record_attendance(self):
        e = make_event(self.org, starts_at=timezone.now() - timedelta(days=1))
        resp = self.client.post(
            reverse("events:record_attendance", args=[e.pk]),
            {"attendance": "125"},
        )
        self.assertRedirects(resp, reverse("events:event_detail", args=[e.pk]))
        e.refresh_from_db()
        self.assertEqual(e.attendance, 125)

    def test_duplicate_repeating_event_creates_next(self):
        start = timezone.now().replace(microsecond=0) + timedelta(days=1)
        e = make_event(self.org, starts_at=start, recurrence=Recurrence.WEEKLY,
                       attendance=80)
        resp = self.client.post(reverse("events:event_duplicate", args=[e.pk]))
        self.assertEqual(Event.objects.filter(organization=self.org).count(), 2)
        new = Event.objects.exclude(pk=e.pk).get(organization=self.org)
        self.assertEqual(new.starts_at, start + timedelta(weeks=1))
        # The copy starts fresh — no attendance carried over.
        self.assertIsNone(new.attendance)
        self.assertRedirects(resp, reverse("events:event_detail", args=[new.pk]))

    def test_duplicate_oneoff_does_nothing(self):
        e = make_event(self.org, recurrence=Recurrence.NONE)
        self.client.post(reverse("events:event_duplicate", args=[e.pk]))
        self.assertEqual(Event.objects.filter(organization=self.org).count(), 1)

    def test_schedule_filters_by_when(self):
        make_event(self.org, title="FutureGathering", starts_at=timezone.now() + timedelta(days=2))
        make_event(self.org, title="PastGathering", starts_at=timezone.now() - timedelta(days=2))
        upcoming = self.client.get(reverse("events:schedule"), {"when": "upcoming"})
        self.assertContains(upcoming, "FutureGathering")
        self.assertNotContains(upcoming, "PastGathering")
        past = self.client.get(reverse("events:schedule"), {"when": "past"})
        self.assertContains(past, "PastGathering")
        self.assertNotContains(past, "FutureGathering")

    def test_export_csv(self):
        make_event(self.org, title="Exportable")
        resp = self.client.get(reverse("events:export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Exportable", resp.content.decode())

    def test_tenant_isolation(self):
        other = make_org(name="Other", slug="other")
        their_event = make_event(other, title="Their event")
        resp = self.client.get(reverse("events:event_detail", args=[their_event.pk]))
        self.assertEqual(resp.status_code, 404)


class EventGatingTests(TestCase):
    """The events area is gated behind the 'events' plan feature."""

    def setUp(self):
        self.org = make_org()
        self.user = User.objects.create_user("owner", password="pw")
        UserOrgMembership.objects.create(
            user=self.user, organization=self.org,
            role=OrgRole.OWNER, is_default=True,
        )
        self.client.force_login(self.user)

    def test_overview_redirects_without_feature(self):
        plan = Plan.objects.create(
            code="no-events", name="No Events", tier=0,
            features={"events": False},
        )
        start_subscription(self.org, plan)
        resp = self.client.get(reverse("events:overview"))
        self.assertRedirects(resp, reverse("billing:plans"))


class DashboardIntegrationTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.user = User.objects.create_user("owner", password="pw")
        UserOrgMembership.objects.create(
            user=self.user, organization=self.org,
            role=OrgRole.OWNER, is_default=True,
        )
        self.client.force_login(self.user)

    def test_dashboard_shows_upcoming_when_feature_on(self):
        plan = Plan.objects.create(
            code="with-events", name="With Events", tier=2,
            features={"events": True},
        )
        start_subscription(self.org, plan)
        make_event(self.org, title="Friday Jummah")
        resp = self.client.get(reverse("donations:dashboard"))
        self.assertContains(resp, "Upcoming events")
        self.assertContains(resp, "Friday Jummah")

    def test_dashboard_hides_events_without_feature(self):
        plan = Plan.objects.create(
            code="no-events-dash", name="No Events", tier=0,
            features={"events": False},
        )
        start_subscription(self.org, plan)
        make_event(self.org, title="Friday Jummah")
        resp = self.client.get(reverse("donations:dashboard"))
        self.assertNotContains(resp, "Upcoming events")
