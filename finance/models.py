from django.db import models
from django.utils import timezone

from core.models import Category, Organization
from members.models import Member


class Transaction(models.Model):
    """One entry in the place's money ledger — income or expense.

    A single model keeps the whole cash picture in one place: donations
    (Chanda / Daan / Offering / Chadhava) and other income are `INCOME`,
    everything the place spends is `EXPENSE`. Kept intentionally small; funds,
    budgets and receipts are their own later phase.
    """

    INCOME = "income"
    EXPENSE = "expense"
    KIND_CHOICES = [(INCOME, "Income"), (EXPENSE, "Expense")]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="transactions"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    # A label this place defines for itself — see core.models.Category.
    category = models.ForeignKey(
        Category, on_delete=models.RESTRICT, null=True, blank=True,
        related_name="transactions",
    )
    # For a donation: link to a member, or just record a free-text donor name.
    member = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transactions",
    )
    donor_name = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} ({self.date})"

    @property
    def signed_amount(self):
        """Positive for income, negative for expense — handy for running totals."""
        return self.amount if self.kind == self.INCOME else -self.amount

    @property
    def party(self):
        """Who the money came from / went to, for display."""
        if self.member_id:
            return self.member.name
        return self.donor_name or "—"
