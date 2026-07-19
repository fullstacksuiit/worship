from django import forms

from donations.models import Category, CategoryKind

from .models import Purchase, Vendor

# Same input styling used across the app's forms.
_INPUT = (
    # Look lives in the global .field-control stylesheet (templates/base.html):
    # brand-tinted focus ring, custom <select> caret, styled date pickers.
    "field-control mt-1 block w-full border px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm"
)


class VendorForm(forms.ModelForm):
    """Create or edit a supplier the org buys from. The view supplies the org."""

    class Meta:
        model = Vendor
        fields = ["name", "phone", "note"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. City Hardware"}
            ),
            "phone": forms.TextInput(attrs={"class": _INPUT}),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Vendor.objects.filter(
            organization=self.organization, name__iexact=name
        ).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have a vendor with that name.")
        return name

    def save(self, commit=True):
        vendor = super().save(commit=False)
        vendor.organization = self.organization
        if commit:
            vendor.save()
        return vendor


class PurchaseForm(forms.ModelForm):
    """Record a purchase. Vendor and expense category are limited to the org's
    own lists. Saving posts a matching expense entry into the finance ledger."""

    class Meta:
        model = Purchase
        fields = [
            "purchased_on",
            "vendor",
            "category",
            "item",
            "quantity",
            "amount",
            "method",
            "reference",
            "description",
        ]
        widgets = {
            "purchased_on": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "vendor": forms.Select(attrs={"class": _INPUT}),
            "category": forms.Select(attrs={"class": _INPUT}),
            "item": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. 50 chairs"}
            ),
            "quantity": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01", "min": "0"}
            ),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}
            ),
            "method": forms.Select(attrs={"class": _INPUT}),
            "reference": forms.TextInput(attrs={"class": _INPUT}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["category"].queryset = Category.objects.filter(
            organization=organization, kind=CategoryKind.EXPENSE, is_active=True
        ).order_by("name")
        self.fields["category"].empty_label = "Select an expense category…"
        self.fields["vendor"].queryset = Vendor.objects.filter(
            organization=organization
        ).order_by("name")
        self.fields["vendor"].empty_label = "No vendor / not recorded"
        self.fields["vendor"].required = False

    def save(self, commit=True):
        purchase = super().save(commit=False)
        purchase.organization = self.organization
        if commit:
            purchase.save()
        return purchase
