from django import forms

from core.categories import CategoryField
from core.models import Category

from .models import Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "category", "start", "end", "location", "description"]
        widgets = {
            "start": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"] = CategoryField(
            organization=org, scope=Category.EVENT, label="Category",
        )
        # HTML datetime-local needs this input format accepted on submit too.
        for f in ("start", "end"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end"].required = False
