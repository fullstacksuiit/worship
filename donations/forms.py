from django import forms

from core.models import Member

from .models import Donation, Fund

_INPUT = (
    "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition placeholder:text-slate-400 "
    "focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900/10"
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
            "amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
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
