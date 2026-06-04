from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import Member, TenantScopedModel
from donations.models import Fund, PaymentMethod


class CategoryKind(models.TextChoices):
    """Whether a category groups money coming in or money going out."""

    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"


# Generic categories seeded for every new organization, regardless of faith.
# Donations are tracked separately (by Fund); these cover the rest of the books:
# non-donation income on one side, running costs and outlays on the other.
DEFAULT_CATEGORIES = {
    CategoryKind.INCOME: [
        ("hall_rental", "Hall / Venue Rental"),
        ("sales", "Sales (books, food, items)"),
        ("grants", "Grants & Aid"),
        ("events", "Event Income"),
        ("other_income", "Other Income"),
    ],
    CategoryKind.EXPENSE: [
        ("utilities", "Utilities"),
        ("salaries", "Salaries & Stipends"),
        ("maintenance", "Maintenance & Repairs"),
        ("rent", "Rent / Mortgage"),
        ("charity", "Charity & Welfare Payouts"),
        ("events_expense", "Events & Programs"),
        ("supplies", "Supplies"),
        ("other_expense", "Other Expense"),
    ],
}


class Category(TenantScopedModel):
    """A bucket a non-donation transaction is filed under. Each organization keeps
    its own income and expense categories; donations keep using Fund instead."""

    kind = models.CharField(max_length=10, choices=CategoryKind.choices)
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind", "code"],
                name="unique_category_code_per_org_kind",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class Transaction(TenantScopedModel):
    """A single non-donation money movement — income (hall rental, sales, grants)
    or expense (utilities, salaries, charity payouts). Donations live in their own
    model; the finance overview sums both into one financial picture."""

    kind = models.CharField(max_length=10, choices=CategoryKind.choices)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="transactions"
    )

    # Free-text counterparty: who was paid (expense) or who paid (income).
    party = models.CharField(
        max_length=200,
        blank=True,
        help_text="Paid to (expense) or received from (income).",
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Currency captured at time of entry (copied from the org) for historical
    # accuracy even if the org later changes its default currency.
    currency = models.CharField(max_length=3, blank=True)

    method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference = models.CharField(
        max_length=120,
        blank=True,
        help_text="Invoice number, transaction id, or other external reference.",
    )
    occurred_at = models.DateField()
    note = models.TextField(blank=True)

    # Auto-incrementing, per-organization voucher number (assigned on save),
    # shared across income and expense entries — one running register.
    voucher_number = models.PositiveIntegerField(null=True, blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_transactions",
    )

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="transaction_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["organization", "voucher_number"],
                name="unique_voucher_number_per_org",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "occurred_at"]),
            models.Index(fields=["organization", "kind"]),
        ]

    def save(self, *args, **kwargs):
        # Default the currency from the owning organization on first save.
        if not self.currency and self.organization_id:
            self.currency = self.organization.currency
        # Keep the kind in step with the chosen category so the two never drift.
        if self.category_id and not self.kind:
            self.kind = self.category.kind
        # Assign the next per-organization voucher number once.
        if self.voucher_number is None and self.organization_id:
            last = (
                Transaction.objects.filter(organization_id=self.organization_id)
                .exclude(voucher_number=None)
                .order_by("-voucher_number")
                .values_list("voucher_number", flat=True)
                .first()
            )
            self.voucher_number = (last or 0) + 1
        super().save(*args, **kwargs)

    @property
    def signed_amount(self):
        """Amount as it affects the balance: positive for income, negative out."""
        if self.kind == CategoryKind.EXPENSE:
            return -self.amount
        return self.amount

    def __str__(self):
        sign = "-" if self.kind == CategoryKind.EXPENSE else "+"
        return f"{sign}{self.amount} {self.currency} · {self.category.name}"


class Budget(TenantScopedModel):
    """A planned amount for one category in one calendar year. Actuals are compared
    against this on the budgets page so an organization can track over/under-spend."""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="budgets"
    )
    year = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-year", "category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "category", "year"],
                name="unique_budget_per_category_year",
            ),
            models.CheckConstraint(
                check=models.Q(amount__gte=Decimal("0")),
                name="budget_amount_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.category.name} {self.year}: {self.amount}"


class Pledge(TenantScopedModel):
    """A member's commitment to give a set amount to a fund within a year. Progress
    is measured against the member's actual donations to that fund in that year."""

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="pledges"
    )
    fund = models.ForeignKey(
        Fund, on_delete=models.PROTECT, related_name="pledges"
    )
    year = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-year", "member__last_name", "member__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "member", "fund", "year"],
                name="unique_pledge_per_member_fund_year",
            ),
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="pledge_amount_positive",
            ),
        ]

    def fulfilled_amount(self):
        """Total this member has actually given to this fund during the year."""
        from django.db.models import Sum

        agg = self.member.donations.filter(
            fund=self.fund, received_at__year=self.year
        ).aggregate(total=Sum("amount"))
        return agg["total"] or Decimal("0")

    def __str__(self):
        return f"{self.member.full_name} → {self.fund.name} {self.year}: {self.amount}"
