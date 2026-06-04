from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import BillingInterval, Plan

# Global, faith-agnostic plan catalogue. Each entry becomes (or updates) a Plan
# row keyed by `code`. Monthly/yearly variants of the same product share a tier.
# `max_members` / `max_users` of None means unlimited.
PLANS = [
    {
        "code": "free",
        "name": "Free",
        "tier": 0,
        "price_amount": Decimal("0"),
        "interval": BillingInterval.MONTHLY,
        "trial_days": 0,
        "max_members": 100,
        "max_users": 2,
        "features": {"finance": False, "events": False},
        "description": "Get started: donations tracking for a small congregation.",
    },
    {
        "code": "standard-monthly",
        "name": "Standard",
        "tier": 1,
        "price_amount": Decimal("19.00"),
        "interval": BillingInterval.MONTHLY,
        "trial_days": 14,
        "max_members": 1000,
        "max_users": 5,
        "features": {"finance": True, "events": False},
        "description": "Donations plus full finance (categories, budgets, pledges).",
    },
    {
        "code": "standard-yearly",
        "name": "Standard",
        "tier": 1,
        "price_amount": Decimal("190.00"),
        "interval": BillingInterval.YEARLY,
        "trial_days": 14,
        "max_members": 1000,
        "max_users": 5,
        "features": {"finance": True, "events": False},
        "description": "Donations plus full finance (categories, budgets, pledges).",
    },
    {
        "code": "pro-monthly",
        "name": "Pro",
        "tier": 2,
        "price_amount": Decimal("49.00"),
        "interval": BillingInterval.MONTHLY,
        "trial_days": 14,
        "max_members": None,
        "max_users": None,
        "features": {"finance": True, "events": True},
        "description": "Everything, unlimited members and staff logins.",
    },
    {
        "code": "pro-yearly",
        "name": "Pro",
        "tier": 2,
        "price_amount": Decimal("490.00"),
        "interval": BillingInterval.YEARLY,
        "trial_days": 14,
        "max_members": None,
        "max_users": None,
        "features": {"finance": True, "events": True},
        "description": "Everything, unlimited members and staff logins.",
    },
]


class Command(BaseCommand):
    help = "Create or update the global platform Plan catalogue (idempotent)."

    def handle(self, *args, **options):
        created, updated = 0, 0
        for spec in PLANS:
            code = spec.pop("code")
            _, was_created = Plan.objects.update_or_create(code=code, defaults=spec)
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Plans seeded: {created} created, {updated} updated."
            )
        )
