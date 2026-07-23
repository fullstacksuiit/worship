import builtins
import math
from datetime import datetime
from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import Category, Organization
from members.models import Member


class Property(models.Model):
    """A rentable asset — a hall, a shop, a community room, an open ground.

    Two quite different things get let out and the rest of the module keys off
    which one this is. A shop goes to a single tenant who pays every month for
    years; a hall is taken date by date by whoever needs it that week. That is
    `rental_mode`, and it decides which screens a property appears on.

    The rate lives here rather than on each booking so the price is settled once
    and every booking after that fills itself in. What a rate *means* differs by
    property — per day for a hall, per hour for an air-conditioned room, a flat
    sum per function for a ground, per month for a shop — so `rate_basis` says
    which, and `quote()` turns it into an amount.
    """

    TENANCY = "tenancy"
    BOOKING = "booking"
    MODE_CHOICES = [
        (BOOKING, "Booked date by date"),
        (TENANCY, "Let to one tenant, monthly"),
    ]

    PER_DAY = "day"
    PER_HOUR = "hour"
    PER_USE = "use"
    PER_MONTH = "month"
    BASIS_CHOICES = [
        (PER_DAY, "per day"),
        (PER_HOUR, "per hour"),
        (PER_USE, "per booking"),
        (PER_MONTH, "per month"),
    ]
    # A monthly tenancy is always priced per month; a booking never is.
    BOOKING_BASES = [PER_DAY, PER_HOUR, PER_USE]
    BASIS_NOUNS = {PER_DAY: "day", PER_HOUR: "hour", PER_USE: "booking", PER_MONTH: "month"}

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="properties"
    )
    name = models.CharField(max_length=200)
    # A label this place defines for itself — see core.models.Category.
    category = models.ForeignKey(
        Category, on_delete=models.RESTRICT, null=True, blank=True,
        related_name="properties",
    )
    description = models.CharField(max_length=300, blank=True)
    rental_mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=BOOKING)
    rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Leave at 0 if the price changes every time.",
    )
    rate_basis = models.CharField(max_length=10, choices=BASIS_CHOICES, default=PER_DAY)
    deposit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Refundable security deposit, if you take one.",
    )
    # Shops don't start their life in this app — a tenant has usually been in
    # the unit for years and is already behind, or has paid a few months ahead.
    # That standing figure is carried in here so the account starts off true
    # instead of pretending everyone was square on the day you signed up.
    # Positive = the tenant owes; negative = they hold a credit.
    opening_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="What the tenant already owed when you started keeping "
                  "records here. Put a minus in front if they had paid ahead.",
    )
    opening_balance_date = models.DateField(
        null=True, blank=True,
        help_text="The day that figure was true — usually the day you started.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "properties"

    def __str__(self):
        return self.name

    @property
    def is_tenancy(self):
        return self.rental_mode == self.TENANCY

    @property
    def icon(self):
        return "🏪" if self.is_tenancy else "🏛️"

    @property
    def has_rate(self):
        return self.rate > 0

    @property
    def basis_noun(self):
        return self.BASIS_NOUNS.get(self.rate_basis, "booking")

    @property
    def rate_display(self):
        """The price as a person would say it — "₹8,000 per day"."""
        if not self.has_rate:
            return "Rate not set"
        return f"{money(self.organization, self.rate)} {self.get_rate_basis_display()}"

    @property
    def deposit_display(self):
        return money(self.organization, self.deposit_amount)

    @property
    def has_opening_balance(self):
        """Only a tenancy carries one — a hall settles each booking on its own."""
        return self.is_tenancy and self.opening_balance != 0

    @property
    def opening_is_arrears(self):
        return self.opening_balance > 0

    @property
    def opening_balance_display(self):
        """The carried-in figure in words — "₹12,000 in arrears", never "-₹2,000".

        A minus sign in front of money is read wrong at a counter about as often
        as it's read right, so the direction is said rather than signed.
        """
        if not self.has_opening_balance:
            return ""
        amount = money(self.organization, abs(self.opening_balance))
        return f"{amount} {'in arrears' if self.opening_is_arrears else 'paid in advance'}"

    def units_for(self, start_date, end_date, start_time=None, end_time=None):
        """How many rate-units a stay covers — the multiplier for `rate`.

        None means the sum can't be worked out yet (an hourly property with no
        times filled in, say), which the caller shows as "type the amount".
        """
        if not (start_date and end_date):
            return None
        if self.rate_basis == self.PER_USE:
            return 1
        if self.rate_basis == self.PER_DAY:
            days = (end_date - start_date).days + 1
            return days if days > 0 else None
        if self.rate_basis == self.PER_HOUR:
            if not (start_time and end_time):
                return None
            minutes = (
                datetime.combine(end_date, end_time)
                - datetime.combine(start_date, start_time)
            ).total_seconds() / 60
            # Part hours count as a full hour — the simplest rule to explain at
            # the counter, and the amount stays editable if you'd rather not.
            return math.ceil(minutes / 60) if minutes > 0 else None
        # PER_MONTH belongs to a tenancy, which isn't priced by date range.
        return None

    def quote(self, start_date, end_date, start_time=None, end_time=None):
        """What this property costs for the given span.

        Returns the amount together with the sum it came from, so nobody has to
        trust a number they can't check. None when there's nothing to compute.
        """
        units = self.units_for(start_date, end_date, start_time, end_time)
        if units is None or not self.has_rate:
            return None
        amount = (self.rate * units).quantize(Decimal("0.01"))
        noun = self.basis_noun + ("s" if units != 1 else "")
        return {
            "units": units,
            "noun": noun,
            "amount": amount,
            "sum": f"{money(self.organization, self.rate)} × {units} {noun} "
                   f"= {money(self.organization, amount)}",
        }


class Booking(models.Model):
    """A reservation of a property for a date range."""

    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [(BOOKED, "Booked"), (COMPLETED, "Completed"), (CANCELLED, "Cancelled")]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="bookings"
    )
    property = models.ForeignKey(
        Property, on_delete=models.PROTECT, related_name="bookings"
    )
    renter_name = models.CharField(max_length=200)
    renter_phone = models.CharField(max_length=30, blank=True)
    member = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bookings",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    # Only asked for when the property is priced by the hour.
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    purpose = models.CharField(max_length=200, blank=True, help_text="e.g. Wedding, Meeting, Function.")
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # What the property's rate worked out to when this was saved. Kept so the
    # detail screen can say "adjusted from ₹16,000" — and so raising a rate
    # later doesn't quietly rewrite what an old booking was charged.
    quoted_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=BOOKED)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.property} · {self.renter_name} ({self.start_date})"

    # NB: the `property` field above shadows the built-in in this class body,
    # so reference it explicitly for these computed helpers.
    @builtins.property
    def is_past(self):
        return self.end_date < timezone.localdate()

    @builtins.property
    def is_cancelled(self):
        return self.status == self.CANCELLED

    @builtins.property
    def is_adjusted(self):
        """Was the rent changed away from what the rate worked out to?"""
        return self.quoted_amount is not None and self.quoted_amount != self.rent_amount

    @builtins.property
    def rent_display(self):
        return money(self.organization, self.rent_amount)

    @builtins.property
    def quoted_display(self):
        return money(self.organization, self.quoted_amount or 0)


def money(organization, amount):
    """An amount the way this place writes it — no stray ".00" on round sums."""
    text = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"{organization.currency_symbol}{text}"
