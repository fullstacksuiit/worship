from django import forms
from django.utils import timezone

from core.categories import CategoryField
from core.models import Category
from members.models import Member

from .models import Booking, Property


class PropertyForm(forms.ModelForm):
    """Add a shop, hall or ground — and settle its price once, here.

    The two mode choices carry different pricing: a tenancy is always monthly,
    a booking is priced by the day, the hour or the function. `clean()` keeps
    the pair honest so a shop can never end up priced "per hour".
    """

    class Meta:
        model = Property
        fields = ["name", "category", "rental_mode", "rate", "rate_basis",
                  "deposit_amount", "opening_balance", "opening_balance_date",
                  "description", "is_active"]
        widgets = {
            "rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "deposit_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            # No `min` here — a minus is how a tenant who paid ahead is entered.
            "opening_balance": forms.NumberInput(attrs={"step": "0.01"}),
            "opening_balance_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": "Property name",
            "rental_mode": "How is it rented out?",
            "rate": "Rate",
            "rate_basis": "Charged",
            "deposit_amount": "Deposit",
            "opening_balance": "Opening balance",
            "opening_balance_date": "As of",
            "is_active": "Available to rent",
        }
        help_texts = {
            "name": "What you call it — “Main Hall”, “Shop No. 3”, “Back Ground”.",
            "rental_mode": "A shop goes to one tenant every month; a hall is booked date by date.",
        }

    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.org = org
        self.fields["category"] = CategoryField(
            organization=org, scope=Category.PROPERTY, label="Type",
        )
        self.fields["category"].help_text = "Shop, Hall, Ground — type your own if it's not listed."
        # Rendered as tappable cards by the template: the radio itself goes
        # visually away but stays focusable, and drives the card's checked look.
        self.fields["rental_mode"].widget = forms.RadioSelect(
            choices=Property.MODE_CHOICES,
            attrs={"data-mode-input": "", "class": "peer sr-only"},
        )
        self.fields["rate"].widget.attrs["data-rate-input"] = ""
        self.fields["rate_basis"].widget.attrs["data-basis-input"] = ""
        self.fields["opening_balance"].widget.attrs["data-opening-input"] = ""
        # All three are money you may simply not have, so an empty box means
        # zero rather than an error telling you to type a zero.
        for name in ("rate", "deposit_amount", "opening_balance"):
            self.fields[name].required = False
            self.fields[name].widget.attrs["placeholder"] = "0"
            # The model's default would otherwise put a literal 0 in the box,
            # which has to be selected and deleted before a figure can be typed.
            if not self.instance.pk:
                self.fields[name].initial = None
        self.fields["opening_balance"].help_text = (
            "Rent the tenant already owed on the day you started keeping "
            "records here. Leave blank if they were square; put a minus in "
            "front if they had paid ahead."
        )
        self.fields["opening_balance_date"].help_text = (
            "Defaults to today — change it if that figure was true on some other day."
        )

    def clean_rate(self):
        return self.cleaned_data.get("rate") or 0

    def clean_deposit_amount(self):
        return self.cleaned_data.get("deposit_amount") or 0

    def clean_opening_balance(self):
        return self.cleaned_data.get("opening_balance") or 0

    def clean(self):
        data = super().clean()
        mode, basis = data.get("rental_mode"), data.get("rate_basis")
        if mode == Property.TENANCY and basis != Property.PER_MONTH:
            # Silently correct rather than scold: monthly is the only thing a
            # tenancy can mean, and the mode is what the user actually chose.
            data["rate_basis"] = Property.PER_MONTH
        elif mode == Property.BOOKING and basis == Property.PER_MONTH:
            self.add_error(
                "rate_basis",
                "A date-wise booking is charged per day, per hour or per booking. "
                "Switch the mode to a monthly tenant if you meant per month.",
            )

        # An opening balance is a running tenant's account carried in, so it
        # only means anything on a tenancy. A hall booked date by date settles
        # each booking on its own and has no standing account to carry.
        if mode != Property.TENANCY:
            data["opening_balance"] = 0
            data["opening_balance_date"] = None
        elif data.get("opening_balance"):
            # A figure with no date is a figure nobody can check later, and the
            # day you're typing it is nearly always the day it was true.
            if not data.get("opening_balance_date"):
                data["opening_balance_date"] = timezone.localdate()
        else:
            data["opening_balance_date"] = None
        return data


class PropertySelect(forms.Select):
    """Property dropdown that carries each property's price in the markup.

    The booking form works the sum out as you type, and it can only do that if
    the rate travels with the option. Without JavaScript nothing is lost — the
    same sum is worked out again on save.
    """

    def create_option(self, name, value, label, *args, **kwargs):
        option = super().create_option(name, value, label, *args, **kwargs)
        prop = getattr(value, "instance", None)
        if prop is not None:
            option["attrs"].update({
                "data-rate": f"{prop.rate}",
                "data-basis": prop.rate_basis,
                "data-noun": prop.basis_noun,
            })
        return option


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["property", "renter_name", "renter_phone", "member",
                  "start_date", "end_date", "start_time", "end_time",
                  "purpose", "rent_amount", "notes"]
        widgets = {
            "property": PropertySelect,
            "start_date": forms.DateInput(attrs={"type": "date", "data-start-date": ""}),
            "end_date": forms.DateInput(attrs={"type": "date", "data-end-date": ""}),
            "start_time": forms.TimeInput(attrs={"type": "time", "data-start-time": ""}),
            "end_time": forms.TimeInput(attrs={"type": "time", "data-end-time": ""}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "rent_amount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "data-amount-input": ""}),
        }
        labels = {"rent_amount": "Rent"}

    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.org = org
        if org is not None:
            # Only bookable properties — a shop on a monthly tenancy is let
            # through its tenant, not through this form.
            self.fields["property"].queryset = Property.objects.filter(
                organization=org, is_active=True, rental_mode=Property.BOOKING)
            self.fields["member"].queryset = Member.objects.filter(organization=org)
        self.fields["property"].empty_label = "Choose a property…"
        self.fields["member"].required = False
        self.fields["member"].label = "Member (optional)"
        # Blank means "use the property's rate" — filled in by `clean()`.
        self.fields["rent_amount"].required = False
        self.fields["rent_amount"].widget.attrs["placeholder"] = "Fills in from the rate"
        if not self.instance.pk:
            self.fields["rent_amount"].initial = None
        self.fields["rent_amount"].help_text = (
            "Fills itself in from the property's rate. Change it for a discount "
            "or a special price."
        )
        for name in ("start_time", "end_time"):
            self.fields[name].required = False
        self.fields["start_time"].help_text = "Only for properties charged by the hour."

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        prop = data.get("property")
        if start and end:
            if end < start:
                self.add_error("end_date", "End date can't be before the start date.")
            elif prop is not None:
                # Prevent double-booking: any active booking on the same property
                # whose range overlaps [start, end].
                clash = Booking.objects.filter(
                    property=prop, start_date__lte=end, end_date__gte=start,
                ).exclude(status=Booking.CANCELLED)
                if self.instance.pk:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    b = clash.first()
                    self.add_error(
                        "start_date",
                        f"{prop} is already booked {b.start_date}–{b.end_date} "
                        f"by {b.renter_name}.",
                    )

        if prop is not None:
            if prop.rate_basis == Property.PER_HOUR:
                if not data.get("start_time") or not data.get("end_time"):
                    self.add_error(
                        "start_time",
                        f"{prop} is charged by the hour — add a start and end time.",
                    )
            else:
                # Times only mean something for an hourly property; drop them so
                # a property switched off hourly pricing doesn't keep stale ones.
                data["start_time"] = data["end_time"] = None

            quote = prop.quote(start, end, data.get("start_time"), data.get("end_time"))
            data["quoted_amount"] = quote["amount"] if quote else None
            if data.get("rent_amount") in (None, ""):
                if quote:
                    data["rent_amount"] = quote["amount"]
                elif not prop.has_rate:
                    self.add_error(
                        "rent_amount",
                        f"{prop} has no rate set, so type what this booking costs.",
                    )
        return data

    def save(self, commit=True):
        booking = super().save(commit=False)
        booking.quoted_amount = self.cleaned_data.get("quoted_amount")
        if commit:
            booking.save()
        return booking
