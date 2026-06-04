from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import FaithTradition, Member, TenantScopedModel


# Suggested funds to seed for each faith tradition. Each entry is (code, name).
# These are starting points an organization can rename, extend, or disable —
# the model itself imposes no faith-specific rules.
DEFAULT_FUNDS = {
    FaithTradition.ISLAM: [
        ("zakat", "Zakat"),
        ("sadaqah", "Sadaqah"),
        ("general", "General Fund"),
        ("building", "Building Fund"),
    ],
    FaithTradition.HINDUISM: [
        ("dakshina", "Dakshina"),
        ("seva", "Seva / Donation"),
        ("annadanam", "Annadanam (Food Offering)"),
        ("general", "General Fund"),
    ],
    FaithTradition.CHRISTIANITY: [
        ("tithe", "Tithe"),
        ("offering", "Offering"),
        ("missions", "Missions"),
        ("building", "Building Fund"),
    ],
    FaithTradition.SIKHISM: [
        ("dasvandh", "Dasvandh"),
        ("langar", "Langar"),
        ("golak", "Golak Offering"),
        ("general", "General Fund"),
    ],
}


class Fund(TenantScopedModel):
    """A category that a donation is directed to (e.g. Zakat, Tithe, Seva,
    Building Fund). Each organization manages its own set of funds."""

    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_fund_code_per_org",
            ),
        ]

    def __str__(self):
        return self.name


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank", "Bank Transfer"
    CHEQUE = "cheque", "Cheque"
    ONLINE = "online", "Online / Gateway"
    OTHER = "other", "Other"


class Donation(TenantScopedModel):
    """A single contribution. May be tied to a Member, or recorded against a
    free-text donor name for walk-in/anonymous gifts."""

    fund = models.ForeignKey(
        Fund, on_delete=models.PROTECT, related_name="donations"
    )

    # Donor: either a linked Member, or just a name, or fully anonymous.
    donor = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    donor_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Used when the donor is not a recorded Member.",
    )
    is_anonymous = models.BooleanField(default=False)

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    # Currency captured at time of gift (copied from the org on save) for
    # historical accuracy even if the org later changes its default currency.
    currency = models.CharField(max_length=3, blank=True)

    method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference = models.CharField(
        max_length=120,
        blank=True,
        help_text="Cheque number, transaction id, or other external reference.",
    )
    received_at = models.DateField()
    note = models.TextField(blank=True)

    # Auto-incrementing, per-organization receipt number (assigned on save).
    receipt_number = models.PositiveIntegerField(null=True, blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_donations",
    )

    class Meta:
        ordering = ["-received_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="donation_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["organization", "receipt_number"],
                name="unique_receipt_number_per_org",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "received_at"]),
        ]

    def save(self, *args, **kwargs):
        # Default the currency from the owning organization on first save.
        if not self.currency and self.organization_id:
            self.currency = self.organization.currency
        # Assign the next per-organization receipt number once.
        if self.receipt_number is None and self.organization_id:
            last = (
                Donation.objects.filter(organization_id=self.organization_id)
                .exclude(receipt_number=None)
                .order_by("-receipt_number")
                .values_list("receipt_number", flat=True)
                .first()
            )
            self.receipt_number = (last or 0) + 1
        super().save(*args, **kwargs)

    @property
    def display_donor(self):
        if self.is_anonymous:
            return "Anonymous"
        if self.donor_id:
            return self.donor.full_name
        return self.donor_name or "Anonymous"

    def __str__(self):
        return f"{self.display_donor} — {self.amount} {self.currency}"
