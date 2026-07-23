"""Raise rent charges for every running tenancy, up to the last completed month.

Rent is charged lazily on the way into a screen (`Tenancy.ensure_charges`), which
is what keeps arrears honest on a laptop that isn't always on. This command does
the same sweep without anyone opening a page, so a place that *does* leave a
machine up can have last month's rent appear on the 1st by itself — wire it to
cron or Task Scheduler for the small hours of the 1st:

    0 1 1 * *  cd /path/to/worship && python manage.py generate_rent

It is safe to run any day and as often as you like: a month already charged is
never charged twice.
"""

from django.core.management.base import BaseCommand

from rentals.models import Tenancy


class Command(BaseCommand):
    help = "Raise rent charges up to the last completed month for every running tenancy."

    def handle(self, *args, **options):
        tenancies = raised = 0
        for tenancy in Tenancy.objects.select_related("organization", "property"):
            if not tenancy.is_running:
                continue
            # The unit's carried-in figure, then every month gone since — the
            # same two steps a detail page runs when it's opened.
            tenancy.carry_in_opening_balance()
            added = tenancy.ensure_charges()
            if added:
                tenancies += 1
                raised += added
                self.stdout.write(
                    f"  {tenancy.property.name} · {tenancy.tenant_name}: "
                    f"{added} month{'s' if added != 1 else ''} charged"
                )
        self.stdout.write(self.style.SUCCESS(
            f"Done — {raised} rent charge(s) raised across {tenancies} tenancy(ies)."
        ))
