from django import forms

from .models import Notice


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ["title", "body", "is_pinned"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
        }
