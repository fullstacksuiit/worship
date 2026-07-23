from django.conf import settings
from django.db import models

from core.models import Organization


class Notice(models.Model):
    """An announcement on the community board.

    Kept simple: a title, a body, and a pin flag so important notices stay on
    top. Delivery channels (SMS / WhatsApp) are a later phase; for now this is
    the in-app board every signed-in member can read.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="notices"
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title
