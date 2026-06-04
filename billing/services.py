"""Subscription lifecycle helpers. Kept out of models so views, signals and
management commands share one code path for starting/changing subscriptions."""

import calendar
from datetime import timedelta

from django.utils import timezone

from .models import BillingInterval, Plan, Subscription, SubscriptionStatus


def add_interval(start, interval):
    """Return `start` advanced by one billing interval, clamping the day of month
    so e.g. Jan 31 + 1 month lands on the last valid day of February."""
    if interval == BillingInterval.YEARLY:
        try:
            return start.replace(year=start.year + 1)
        except ValueError:  # Feb 29 in a non-leap target year
            return start.replace(year=start.year + 1, day=28)
    # Monthly
    month = start.month + 1
    year = start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def default_plan():
    """The plan a brand-new organization is provisioned onto: the cheapest active
    public plan (typically Free). Returns None if no plan catalogue is seeded."""
    return (
        Plan.objects.filter(is_active=True, is_public=True)
        .order_by("tier", "price_amount")
        .first()
    )


def start_subscription(organization, plan, *, provider=""):
    """Create (or replace) the organization's subscription on `plan`, deriving
    trial/period dates. Idempotent per organization thanks to the OneToOne."""
    now = timezone.now()

    if plan.trial_days:
        trial_end = now + timedelta(days=plan.trial_days)
        status = SubscriptionStatus.TRIALING
        period_end = trial_end
    else:
        trial_end = None
        status = SubscriptionStatus.ACTIVE
        # A free plan runs perpetually (no period end); paid plans get a period.
        period_end = add_interval(now, plan.interval) if plan.price_amount else None

    defaults = {
        "plan": plan,
        "status": status,
        "trial_end": trial_end,
        "current_period_start": now,
        "current_period_end": period_end,
        "provider": provider,
        "cancel_at_period_end": False,
        "canceled_at": None,
        "ended_at": None,
    }
    subscription, _ = Subscription.objects.update_or_create(
        organization=organization, defaults=defaults
    )
    return subscription
