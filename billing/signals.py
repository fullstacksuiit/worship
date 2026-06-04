from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Organization

from .services import default_plan, start_subscription


@receiver(post_save, sender=Organization, dispatch_uid="billing_provision_subscription")
def provision_subscription(sender, instance, created, **kwargs):
    """Give every newly created organization a subscription on the default
    (free) plan. No-op if no plan catalogue is seeded yet, or if the org somehow
    already has one."""
    if not created:
        return
    if hasattr(instance, "subscription"):
        return
    plan = default_plan()
    if plan is None:
        return
    start_subscription(instance, plan)
