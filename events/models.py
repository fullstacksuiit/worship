from django.db import models
from django.utils import timezone

from core.models import Category, Organization
from members.models import Member


class Event(models.Model):
    """A scheduled gathering — Jalsa / Puja / Service / Kirtan / program.

    Single (non-recurring) events for now; recurrence is its own later phase.
    Attendance is optional — mark which members came from the event page.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="events"
    )
    title = models.CharField(max_length=200)
    # A label this place defines for itself — see core.models.Category.
    category = models.ForeignKey(
        Category, on_delete=models.RESTRICT, null=True, blank=True,
        related_name="events",
    )
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    attendees = models.ManyToManyField(
        Member, blank=True, related_name="events_attended"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start"]

    def __str__(self):
        return self.title

    @property
    def is_past(self):
        return self.start < timezone.now()
