from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import Organization


class BillingInterval(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"


class Plan(models.Model):
    """A purchasable platform tier. Unlike almost everything else in the system,
    a Plan is NOT tenant-scoped — it is a global catalogue entry shared by every
    organization. One row per price point (e.g. "Standard Monthly" and "Standard
    Yearly" are two rows sharing the same `tier`), which maps cleanly onto a Stripe
    Price when a payment gateway is added later."""

    code = models.SlugField(
        max_length=40,
        unique=True,
        help_text='Stable identifier, e.g. "free", "standard-monthly".',
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    # Groups the monthly/yearly variants of the same product and orders the
    # pricing table (higher tier = more capable).
    tier = models.PositiveSmallIntegerField(default=0)

    price_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0")
    )
    currency = models.CharField(max_length=3, default="USD")
    interval = models.CharField(
        max_length=10,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTHLY,
    )
    trial_days = models.PositiveIntegerField(default=0)

    # Limits enforced in app code against live counts. NULL means unlimited.
    max_members = models.PositiveIntegerField(null=True, blank=True)
    max_users = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum staff logins (UserOrgMembership) for the org.",
    )

    # Module / feature entitlements kept as flags so adding a new gate doesn't
    # require a migration, e.g. {"finance": true, "events": false}.
    features = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(
        default=True, help_text="Available to start new subscriptions on."
    )
    is_public = models.BooleanField(
        default=True, help_text="Shown on the public pricing page."
    )

    # Set when a payment gateway is wired in (e.g. Stripe Price id).
    external_price_id = models.CharField(max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tier", "interval", "price_amount"]

    def allows(self, feature):
        """Whether this plan grants access to a named module/feature flag."""
        return bool(self.features.get(feature, False))

    def __str__(self):
        return f"{self.name} ({self.get_interval_display()})"


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELED = "canceled", "Canceled"  # still running until current_period_end
    EXPIRED = "expired", "Expired"  # period elapsed, access revoked


class Subscription(models.Model):
    """An organization's relationship to a Plan. Exactly one per organization
    (OneToOne); upgrades/downgrades mutate `plan` in place rather than creating
    new rows — billing-period history lives in Invoice instead."""

    # Statuses that should still grant access to the product.
    LIVE_STATUSES = (
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    )

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=12,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIALING,
    )

    started_at = models.DateTimeField(auto_now_add=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # When true, the subscription will not renew and lapses at period end.
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Provider-agnostic hooks, blank until a gateway is wired in.
    provider = models.CharField(
        max_length=20, blank=True, help_text='e.g. "stripe", "manual".'
    )
    external_customer_id = models.CharField(max_length=80, blank=True)
    external_subscription_id = models.CharField(max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_current(self):
        """Whether the subscription currently entitles the org to the product."""
        if self.status not in self.LIVE_STATUSES:
            return False
        if self.current_period_end and self.current_period_end < timezone.now():
            return False
        return True

    def __str__(self):
        return f"{self.organization} → {self.plan.name} ({self.get_status_display()})"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


class Invoice(models.Model):
    """A billing-period charge against a subscription. Provider-agnostic: stands
    on its own for manual/offline tracking now, and is the natural target for a
    payment gateway's webhooks (paid/void) later."""

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="invoices"
    )
    status = models.CharField(
        max_length=10,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    external_invoice_id = models.CharField(max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.amount} {self.currency} — {self.get_status_display()}"
