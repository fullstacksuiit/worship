import calendar

from django import forms

from .models import (
    PropertyType,
    RentAdjustment,
    RentalUnit,
    RentPayment,
    RentRevision,
)

# Matches the input styling used across the finance/donations/members forms so
# every field in the app looks the same.
_INPUT = (
    # Look lives in the global .field-control stylesheet (templates/base.html):
    # brand-tinted focus ring, custom <select> caret, styled date pickers.
    "field-control mt-1 block w-full border px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm"
)

_MONTH_CHOICES = [(m, calendar.month_name[m]) for m in range(1, 13)]


class PropertyTypeForm(forms.ModelForm):
    """Create or edit one of an organization's rentable property types (Shop,
    Hall, Room, ...). The view supplies the owning organization."""

    class Meta:
        model = PropertyType
        fields = ["name", "icon", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Hall"}
            ),
            "icon": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "Optional emoji, e.g. 🏛️"}
            ),
            "description": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "What this kind of unit is"}
            ),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["is_active"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900/20"}
        )

    def clean_name(self):
        """Derive a stable per-org code from the name, guarding uniqueness. The
        code is what finance/reporting keys on; the name is the editable label."""
        from django.utils.text import slugify

        name = self.cleaned_data["name"].strip()
        code = slugify(name)[:40] or "type"
        clash = PropertyType.objects.filter(
            organization=self.organization, code=code
        ).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(
                "You already have a property type with a similar name."
            )
        self._derived_code = code
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.organization = self.organization
        if getattr(self, "_derived_code", None):
            obj.code = self._derived_code
        if commit:
            obj.save()
        return obj


class RentalUnitForm(forms.ModelForm):
    """Create or edit a rentable unit and its tenant. The view supplies the
    owning organization."""

    class Meta:
        model = RentalUnit
        fields = [
            "property_type",
            "name",
            "description",
            "tenant_name",
            "tenant_phone",
            "monthly_rent",
            "deposit",
            "opening_balance",
            "currency",
            "start_date",
            "is_active",
            "note",
        ]
        widgets = {
            "property_type": forms.Select(attrs={"class": _INPUT}),
            "name": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Shop 1"}
            ),
            "description": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Ground floor, left of gate"}
            ),
            "tenant_name": forms.TextInput(attrs={"class": _INPUT}),
            "tenant_phone": forms.TextInput(attrs={"class": _INPUT}),
            "monthly_rent": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01", "min": "0"}
            ),
            "deposit": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01", "min": "0"}
            ),
            "opening_balance": forms.NumberInput(
                attrs={"class": _INPUT, "step": "0.01"}
            ),
            "currency": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "Leave blank to use org default"}
            ),
            "start_date": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        # Only offer this org's active property types.
        self.fields["property_type"].queryset = PropertyType.objects.filter(
            organization=organization, is_active=True
        ).order_by("name")
        self.fields["property_type"].empty_label = "Select a type…"
        # Currency defaults from the org, so most users never touch this field.
        self.fields["currency"].required = False
        self.fields["is_active"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900/20"}
        )

    def save(self, commit=True):
        unit = super().save(commit=False)
        unit.organization = self.organization
        if commit:
            unit.save()
        return unit


class RentPaymentForm(forms.ModelForm):
    """Record a rent receipt against a unit. The month/year default to the current
    period and the amount to the unit's agreed monthly rent.

    The unit can be fixed by the view (when recording from a unit's own page) or
    chosen by the user from a dropdown — pass ``unit=None`` and the form grows a
    "From (unit / tenant)" selector so rent can be recorded without first
    navigating into a unit."""

    period_month = forms.TypedChoiceField(
        choices=_MONTH_CHOICES, coerce=int, widget=forms.Select(attrs={"class": _INPUT})
    )

    class Meta:
        model = RentPayment
        fields = [
            "period_month",
            "period_year",
            "amount",
            "method",
            "paid_on",
            "reference",
            "note",
        ]
        widgets = {
            "period_year": forms.NumberInput(
                attrs={"class": _INPUT, "min": "2000", "max": "2100"}
            ),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT + " !mt-0 pl-14", "step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "method": forms.Select(attrs={"class": _INPUT}),
            "paid_on": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "reference": forms.TextInput(attrs={"class": _INPUT}),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, unit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.unit = unit
        # When the view hasn't fixed a unit, let the user pick who the rent is
        # from. Active units only — vacated units stop accruing rent, and their
        # own page is still there for the rare late receipt.
        if unit is None:
            self.fields["unit"] = forms.ModelChoiceField(
                queryset=RentalUnit.objects.filter(
                    organization=organization, is_active=True
                ).order_by("name"),
                empty_label="Select a unit…",
                widget=forms.Select(attrs={"class": _INPUT}),
                label="From (unit / tenant)",
            )
            # Show the selector first — you choose who before recording what.
            self.order_fields(["unit", *(f for f in self.fields if f != "unit")])

    def save(self, commit=True):
        payment = super().save(commit=False)
        payment.organization = self.organization
        payment.unit = self.unit or self.cleaned_data["unit"]
        if commit:
            payment.save()
        return payment


class RentRevisionForm(forms.ModelForm):
    """Record a rent increase or decrease taking effect from a chosen month. The
    view supplies the organization and the unit."""

    effective_month = forms.TypedChoiceField(
        choices=_MONTH_CHOICES, coerce=int, widget=forms.Select(attrs={"class": _INPUT})
    )

    class Meta:
        model = RentRevision
        fields = ["effective_month", "effective_year", "monthly_rent", "reason", "note"]
        widgets = {
            "effective_year": forms.NumberInput(
                attrs={"class": _INPUT, "min": "2000", "max": "2100"}
            ),
            "monthly_rent": forms.NumberInput(
                attrs={"class": _INPUT + " !mt-0 pl-14", "step": "0.01", "min": "0", "placeholder": "0.00"}
            ),
            "reason": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Annual revision"}
            ),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, unit, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.unit = unit

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("effective_year")
        month = cleaned.get("effective_month")
        # One rate change per month per unit — guard the unique constraint with a
        # friendly message instead of a 500.
        if year and month:
            clash = RentRevision.objects.filter(
                unit=self.unit, effective_year=year, effective_month=month
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    "This unit already has a rent change for that month — edit or "
                    "remove it instead."
                )
        return cleaned

    def save(self, commit=True):
        revision = super().save(commit=False)
        revision.organization = self.organization
        revision.unit = self.unit
        if commit:
            revision.save()
        return revision


class RentAdjustmentForm(forms.ModelForm):
    """Grant a rebate/concession against one month's rent. The view supplies the
    organization and unit and posts the matching finance expense."""

    period_month = forms.TypedChoiceField(
        choices=_MONTH_CHOICES, coerce=int, widget=forms.Select(attrs={"class": _INPUT})
    )

    class Meta:
        model = RentAdjustment
        fields = ["period_month", "period_year", "amount", "reason", "dated_on", "note"]
        widgets = {
            "period_year": forms.NumberInput(
                attrs={"class": _INPUT, "min": "2000", "max": "2100"}
            ),
            "amount": forms.NumberInput(
                attrs={"class": _INPUT + " !mt-0 pl-14", "step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "reason": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Poor condition"}
            ),
            "dated_on": forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "note": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization, unit, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.unit = unit
        self.fields["reason"].required = True

    def save(self, commit=True):
        adjustment = super().save(commit=False)
        adjustment.organization = self.organization
        adjustment.unit = self.unit
        if commit:
            adjustment.save()
        return adjustment
