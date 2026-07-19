from django import forms

from core.models import Member

from .models import (
    Budget,
    Category,
    Donation,
    Fund,
    Pledge,
    Transaction,
)

_INPUT = (
    # Look lives in the global .field-control stylesheet (templates/base.html):
    # brand-tinted focus ring, custom <select> caret, styled date pickers.
    "field-control mt-1 block w-full border px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm"
)


class DonationForm(forms.ModelForm):
    """Record-a-donation form, scoped to a single organization so the fund and
    donor dropdowns only ever show that org's records."""

    class Meta:
        model = Donation
        fields = [
            "fund",
            "donor",
            "donor_name",
            "is_anonymous",
            "amount",
            "method",
            "received_at",
            "reference",
            "note",
        ]
        widgets = {
            "fund": forms.Select(attrs={"class": _INPUT}),
            "donor": forms.Select(attrs={"class": _INPUT}),
            "donor_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Name (if not a member)"}),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT + " !mt-0 pl-14", "step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "method": forms.Select(attrs={"class": _INPUT}),
            "received_at": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "reference": forms.TextInput(attrs={"class": _INPUT}),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["fund"].queryset = Fund.objects.filter(
            organization=organization, is_active=True
        )
        self.fields["donor"].queryset = Member.objects.filter(
            organization=organization, is_active=True
        )
        self.fields["donor"].required = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("is_anonymous") and not cleaned.get("donor") and not cleaned.get("donor_name"):
            raise forms.ValidationError(
                "Choose a member, enter a donor name, or mark the gift anonymous."
            )
        return cleaned

    def save(self, commit=True):
        donation = super().save(commit=False)
        donation.organization = self.organization
        if commit:
            donation.save()
        return donation


class TransactionForm(forms.ModelForm):
    """Record an income or expense entry. The view fixes the `kind` (so the same
    form serves both the 'Record expense' and 'Record income' pages) and the
    category dropdown is limited to that org's active categories of that kind."""

    class Meta:
        model = Transaction
        fields = [
            "category",
            "party",
            "amount",
            "method",
            "occurred_at",
            "reference",
            "note",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": _INPUT}),
            "party": forms.TextInput(attrs={"class": _INPUT}),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT + " !mt-0 pl-14", "step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "method": forms.Select(attrs={"class": _INPUT}),
            "occurred_at": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "reference": forms.TextInput(attrs={"class": _INPUT}),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.kind = kind
        # Exclude system categories (e.g. rent, fed from the Rentals module) so
        # the same income can't be recorded twice by hand.
        self.fields["category"].queryset = Category.objects.filter(
            organization=organization, kind=kind, is_active=True, is_system=False
        )

    def save(self, commit=True):
        txn = super().save(commit=False)
        txn.organization = self.organization
        txn.kind = self.kind
        if commit:
            txn.save()
        return txn


class CategoryForm(forms.ModelForm):
    """Add a finance category. The view supplies the org and the kind."""

    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Insurance"}
            ),
            "description": forms.TextInput(attrs={"class": _INPUT}),
        }

    def __init__(self, *args, organization, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.kind = kind

    def clean_name(self):
        from django.utils.text import slugify

        name = self.cleaned_data["name"].strip()
        code = slugify(name)[:40] or "category"
        if Category.objects.filter(
            organization=self.organization, kind=self.kind, code=code
        ).exists():
            raise forms.ValidationError(
                "A category like that already exists for this organization."
            )
        self._code = code
        return name

    def save(self, commit=True):
        category = super().save(commit=False)
        category.organization = self.organization
        category.kind = self.kind
        category.code = self._code
        if commit:
            category.save()
        return category


class BudgetForm(forms.ModelForm):
    """Set a yearly budget for one category, scoped to the org's own categories."""

    class Meta:
        model = Budget
        fields = ["category", "year", "amount", "note"]
        widgets = {
            "category": forms.Select(attrs={"class": _INPUT}),
            "year": forms.NumberInput(attrs={"class": _INPUT, "min": "2000", "max": "2100"}),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01", "min": "0"}
            ),
            "note": forms.TextInput(attrs={"class": _INPUT}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["category"].queryset = Category.objects.filter(
            organization=organization, is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        year = cleaned.get("year")
        if category and year:
            dupes = Budget.objects.filter(
                organization=self.organization, category=category, year=year
            )
            if dupes.exists():
                raise forms.ValidationError(
                    f"A budget for {category.name} in {year} already exists."
                )
        return cleaned

    def save(self, commit=True):
        budget = super().save(commit=False)
        budget.organization = self.organization
        if commit:
            budget.save()
        return budget


class PledgeForm(forms.ModelForm):
    """Record a member's giving commitment, scoped to the org's members and funds."""

    class Meta:
        model = Pledge
        fields = ["member", "fund", "year", "amount", "note"]
        widgets = {
            "member": forms.Select(attrs={"class": _INPUT}),
            "fund": forms.Select(attrs={"class": _INPUT}),
            "year": forms.NumberInput(attrs={"class": _INPUT, "min": "2000", "max": "2100"}),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}
            ),
            "note": forms.TextInput(attrs={"class": _INPUT}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["member"].queryset = Member.objects.filter(
            organization=organization, is_active=True
        )
        self.fields["fund"].queryset = Fund.objects.filter(
            organization=organization, is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        member = cleaned.get("member")
        fund = cleaned.get("fund")
        year = cleaned.get("year")
        if member and fund and year:
            dupes = Pledge.objects.filter(
                organization=self.organization,
                member=member,
                fund=fund,
                year=year,
            )
            if dupes.exists():
                raise forms.ValidationError(
                    "That member already has a pledge to this fund for that year."
                )
        return cleaned

    def save(self, commit=True):
        pledge = super().save(commit=False)
        pledge.organization = self.organization
        if commit:
            pledge.save()
        return pledge
