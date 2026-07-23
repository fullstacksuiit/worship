from django import forms

from core.categories import CategoryField
from core.models import Category
from members.models import Member

from .models import Transaction


class TransactionForm(forms.ModelForm):
    """Shared form for both income and expense. `kind` is set by the view, not
    the user, so income and expense entry can show tailored labels."""

    class Meta:
        model = Transaction
        fields = ["amount", "date", "category", "member", "donor_name", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 2}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, org=None, kind=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        # Only this org's members are selectable as donors.
        if org is not None:
            self.fields["member"].queryset = Member.objects.filter(organization=org)
        # Income and expense keep separate category vocabularies, so neither
        # box suggests words from the other side of the ledger.
        self.fields["category"] = CategoryField(
            organization=org,
            scope=Category.EXPENSE if kind == Transaction.EXPENSE else Category.INCOME,
            label="Category",
        )
        if kind == Transaction.EXPENSE:
            # Donor fields make no sense for an expense.
            self.fields.pop("member")
            self.fields.pop("donor_name")
        else:
            self.fields["member"].required = False
            self.fields["member"].label = "Member (optional)"
            self.fields["donor_name"].label = "Or donor name (optional)"
