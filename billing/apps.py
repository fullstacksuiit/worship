from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"

    def ready(self):
        # Connect the organization -> subscription provisioning signal.
        from . import signals  # noqa: F401
