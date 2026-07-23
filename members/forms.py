from django import forms

from .models import Member


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["name", "phone", "email", "household", "join_date", "is_active", "notes"]
        widgets = {
            "join_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
