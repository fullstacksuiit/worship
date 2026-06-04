from django.core.management.base import BaseCommand

from core.models import Organization

from billing.services import default_plan, start_subscription


class Command(BaseCommand):
    help = (
        "Provision a default-plan subscription for any organization that lacks "
        "one (e.g. orgs created before billing existed). Idempotent."
    )

    def handle(self, *args, **options):
        plan = default_plan()
        if plan is None:
            self.stderr.write(
                self.style.ERROR("No active plan found — run `seed_plans` first.")
            )
            return

        provisioned = 0
        for org in Organization.objects.filter(subscription__isnull=True):
            start_subscription(org, plan)
            provisioned += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfilled {provisioned} organization(s) onto '{plan.name}'."
            )
        )
