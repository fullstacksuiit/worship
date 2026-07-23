from django.db import models
from django.utils import timezone

from core.models import Organization


class Member(models.Model):
    """A person in the community (Jamaat / Sangat / Congregation).

    Attached to the Organization so the data is ready to isolate per-place when
    multi-place lands later. Kept deliberately small — extra fields get added in
    their own phase, not preemptively.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="members"
    )
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    household = models.CharField(
        max_length=200, blank=True,
        help_text="Family / household name, to group relatives together.",
    )
    join_date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
