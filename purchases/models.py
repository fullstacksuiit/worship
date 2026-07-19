from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import TenantScopedModel
from donations.models import PaymentMethod

# Purchases are the org buying things — the symmetric counterpart of Rentals.
# Where a rent receipt posts an income entry into Finance, a purchase posts an
# *expense* entry, so the org's outgoings live in the same unified ledger. The
# purchase files under a normal, user-chosen expense Category (not a system one),
# so one purchase is exactly one expense transaction — no double-counting.


class Vendor(TenantScopedModel):
    """A supplier the organization buys from. Each org keeps its own list; a
    purchase can name a vendor or be left vendor-less (e.g. a cash sundry)."""

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_vendor_name_per_org",
            ),
        ]

    def __str__(self):
        return self.name


class Purchase(TenantScopedModel):
    """Something the organization bought — supplies, equipment, services. Each
    purchase posts a matching expense entry into Finance (see `transaction`) so
    outgoings flow into the organization's books automatically."""

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name="purchases",
        null=True,
        blank=True,
    )
    # The expense bucket this purchase is filed under (Supplies, Maintenance, ...).
    category = models.ForeignKey(
        "donations.Category",
        on_delete=models.PROTECT,
        related_name="purchases",
    )

    item = models.CharField(max_length=200, help_text="What was bought.")
    description = models.TextField(blank=True)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("1")
    )

    amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Total spent on this purchase."
    )
    # Currency captured at time of entry (copied from the org) for historical
    # accuracy even if the org later changes its default currency.
    currency = models.CharField(max_length=3, blank=True)

    method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    purchased_on = models.DateField()
    reference = models.CharField(
        max_length=120,
        blank=True,
        help_text="Invoice or bill number, or other external reference.",
    )
    note = models.TextField(blank=True)

    # Auto-incrementing, per-organization voucher number for the purchase record
    # (assigned on save). The mirroring finance Transaction keeps its own voucher.
    voucher_number = models.PositiveIntegerField(null=True, blank=True)

    # The finance expense entry created for this purchase. SET_NULL so deleting
    # the ledger entry doesn't erase the purchase record (and vice versa).
    transaction = models.ForeignKey(
        "donations.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase",
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_purchases",
    )

    class Meta:
        ordering = ["-purchased_on", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="purchase_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["organization", "voucher_number"],
                name="unique_purchase_voucher_per_org",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "purchased_on"],
                name="purchase_org_date_idx",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.currency and self.organization_id:
            self.currency = self.organization.currency
        if self.voucher_number is None and self.organization_id:
            last = (
                Purchase.objects.filter(organization_id=self.organization_id)
                .exclude(voucher_number=None)
                .order_by("-voucher_number")
                .values_list("voucher_number", flat=True)
                .first()
            )
            self.voucher_number = (last or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Purchase #{self.voucher_number} · {self.item}"
