from django import forms

from core.models import Member

from .models import Event

# Shared input styling — matches the finance/donations/rentals/members forms so
# every field in the app looks identical.
_INPUT = (
    # Look lives in the global .field-control stylesheet (templates/base.html):
    # brand-tinted focus ring, custom <select> caret, styled date pickers.
    "field-control mt-1 block w-full border px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm"
)


class EventForm(forms.ModelForm):
    """Create or edit a gathering. The owning organisation is supplied by the
    view; the 'led by' picker is limited to that organisation's members."""

    class Meta:
        model = Event
        fields = [
            "title",
            "kind",
            "starts_at",
            "ends_at",
            "location",
            "lead",
            "recurrence",
            "expected_attendance",
            "description",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Sunday Service"}
            ),
            "kind": forms.Select(attrs={"class": _INPUT}),
            "starts_at": forms.DateTimeInput(
                attrs={"class": _INPUT, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"class": _INPUT, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "location": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "e.g. Main hall"}
            ),
            "lead": forms.Select(attrs={"class": _INPUT}),
            "recurrence": forms.Select(attrs={"class": _INPUT}),
            "expected_attendance": forms.NumberInput(
                attrs={"class": _INPUT, "min": "0", "placeholder": "Optional"}
            ),
            "description": forms.Textarea(
                attrs={"class": _INPUT, "rows": 3,
                       "placeholder": "Anything attendees or organisers should know."}
            ),
        }

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        # The browser's datetime-local control needs this exact format to show an
        # existing value when editing.
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["ends_at"].required = False
        self.fields["lead"].required = False
        self.fields["lead"].queryset = Member.objects.filter(
            organization=organization, is_active=True
        )
        self.fields["lead"].empty_label = "— Not assigned —"

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends < starts:
            self.add_error("ends_at", "The finish time can't be before the start.")
        return cleaned

    def save(self, commit=True):
        event = super().save(commit=False)
        event.organization = self.organization
        if commit:
            event.save()
        return event


class AttendanceForm(forms.ModelForm):
    """Record (or correct) the headcount for a gathering — the only field needed
    after the event has happened."""

    class Meta:
        model = Event
        fields = ["attendance"]
        widgets = {
            "attendance": forms.NumberInput(
                attrs={
                    "class": _INPUT,
                    "min": "0",
                    "placeholder": "e.g. 120",
                    "autofocus": "autofocus",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attendance"].required = True
        self.fields["attendance"].label = "People who attended"
