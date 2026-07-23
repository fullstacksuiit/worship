import builtins
import math
from datetime import date, datetime
from decimal import Decimal

from django.db import models, transaction
from django.dispatch import receiver
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

    @property
    def current_tenancy(self):
        """Who is in this unit now — None if it's standing empty (or is a hall)."""
        today = timezone.localdate()
        return (
            self.tenancies.filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=today))
            .order_by("-start_date")
            .first()
        )

    @property
    def is_vacant(self):
        return self.is_tenancy and self.current_tenancy is None

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

    @builtins.property
    def amount_paid(self):
        """Collected so far. Uses a list's annotation when it was given one."""
        if hasattr(self, "paid_total"):
            return self.paid_total or Decimal("0")
        return self.payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0")

    @builtins.property
    def balance(self):
        """Still to collect on this booking."""
        return self.rent_amount - self.amount_paid

    @builtins.property
    def paid_display(self):
        return money(self.organization, self.amount_paid)

    @builtins.property
    def balance_display(self):
        return money(self.organization, self.balance)

    @builtins.property
    def paid_untracked(self):
        """Ticked as paid back when that was all a booking could say.

        Those bookings never wrote a Money row, and inventing one now would put
        income on a day nothing arrived — so the screen says what it knows and
        offers to record the payment properly.
        """
        return self.is_paid and not self.payments.exists()

    def refresh_paid(self):
        """Keep the paid flag true to the payments actually recorded."""
        paid = self.rent_amount > 0 and self.balance <= 0
        if paid != self.is_paid:
            self.is_paid = paid
            self.save(update_fields=["is_paid"])


class Tenancy(models.Model):
    """A tenant in a unit, paying every month — the shop side of rentals.

    A booking is a date range that settles itself and is done. A tenancy runs
    for years and keeps an *account*: rent is charged month by month whether or
    not anyone gets round to collecting it (`RentCharge`), what the tenant hands
    over is recorded against a month (`RentPayment`), and the difference between
    the two columns is the arrears — the figure the whole module exists to
    answer honestly.

    One unit can have had several tenants over the years, so this is a separate
    record rather than fields on `Property`: the shop stays, the tenant changes,
    and last year's account has to keep saying what it always said.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="tenancies"
    )
    property = models.ForeignKey(
        Property, on_delete=models.PROTECT, related_name="tenancies"
    )
    tenant_name = models.CharField(max_length=200)
    tenant_phone = models.CharField(max_length=30, blank=True)
    member = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tenancies",
    )
    start_date = models.DateField(
        default=timezone.localdate,
        help_text="The first month rent is charged for.",
    )
    end_date = models.DateField(
        null=True, blank=True,
        help_text="Leave blank while the tenant is still in.",
    )
    # Copied from the property's rate when the tenancy starts, then free to
    # differ — an old tenant on an old rent is the normal case, not an error.
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name_plural = "tenancies"

    def __str__(self):
        return f"{self.tenant_name} · {self.property}"

    @builtins.property
    def is_running(self):
        return self.end_date is None or self.end_date >= timezone.localdate()

    @builtins.property
    def period_display(self):
        """"Since Apr 2025", or "Apr 2025 – Mar 2026" once it has ended."""
        started = self.start_date.strftime("%b %Y")
        if self.is_running:
            return f"Since {started}"
        return f"{started} – {self.end_date.strftime('%b %Y')}"

    @builtins.property
    def rent_display(self):
        if self.monthly_rent <= 0:
            return "Rent not set"
        return f"{money(self.organization, self.monthly_rent)} per month"

    @builtins.property
    def deposit_display(self):
        return money(self.organization, self.deposit_paid)

    @transaction.atomic
    def ensure_charges(self, upto=None):
        """Bring the account up to date — one rent row per month reached so far.

        Charges are raised here, on the way into a screen, rather than by a
        nightly job. The server this runs on is somebody's laptop as often as
        it's a machine that stays up, and a month's rent that exists only if a
        cron fired is a month's rent that quietly goes missing.

        Each row keeps the rent as it stood that month, so putting the rent up
        next year doesn't rewrite what was owed last year. Returns how many rows
        were added, so a screen can say so the first time.
        """
        if self.monthly_rent <= 0:
            return 0
        # In arrears: the newest month we ever raise is the one just gone, so on
        # the 1st of any month last month's rent appears and the running month
        # is left uncharged until it, too, is over.
        last = _prev_month(_month_start(upto or timezone.localdate()))
        if self.end_date:
            last = min(last, _month_start(self.end_date))
        period = _month_start(self.start_date)
        already = set(
            self.charges.filter(kind=RentCharge.RENT).values_list("period", flat=True)
        )
        pending = []
        while period <= last:
            if period not in already:
                pending.append(RentCharge(
                    organization_id=self.organization_id, tenancy=self,
                    period=period, amount=self.monthly_rent,
                ))
            period = _next_month(period)
        if pending:
            # Two people opening the same shop at once would otherwise raise the
            # same month twice; the unique constraint decides, and both see one.
            RentCharge.objects.bulk_create(pending, ignore_conflicts=True)
        return len(pending)

    @transaction.atomic
    def carry_in_opening_balance(self):
        """Bring the unit's carried-in figure onto this tenant's account.

        A shop doesn't begin its life in this app — the tenant has usually been
        there for years and is already behind, or has paid a few months ahead.
        `Property.opening_balance` is where that figure was typed; this puts it
        in the account as an ordinary row so it can be paid off (or spent) like
        any other, instead of being a number in a corner that never moves.

        Only the unit's first tenancy carries it: the figure describes the day
        record-keeping started, not every tenant who ever holds the keys.
        """
        prop = self.property
        if not prop.has_opening_balance:
            return
        first = prop.tenancies.order_by("start_date", "pk").first()
        if first is None or first.pk != self.pk:
            return
        when = prop.opening_balance_date or self.start_date
        if prop.opening_is_arrears:
            RentCharge.objects.get_or_create(
                tenancy=self, kind=RentCharge.OPENING,
                defaults={
                    "organization_id": self.organization_id,
                    "period": when,
                    "amount": prop.opening_balance,
                },
            )
        else:
            # Paid ahead: a credit on the account. It isn't money arriving now,
            # so it stays out of the books — see `RentPayment.posts_to_books`.
            RentPayment.objects.get_or_create(
                tenancy=self, is_opening=True,
                defaults={
                    "organization_id": self.organization_id,
                    "date": when,
                    "amount": abs(prop.opening_balance),
                    "note": "Paid in advance before records started here",
                },
            )

    def ledger(self, refresh=True):
        """The account, month by month, and what it comes to.

        `refresh` raises any months that have come round since anyone last
        looked, which is what makes the lazy charging above work.
        """
        if refresh:
            self.carry_in_opening_balance()
            self.ensure_charges()
        charges = list(
            self.charges.annotate(paid_sum=models.Sum("payments__amount"))
            .order_by("period", "kind")
        )
        for charge in charges:
            # Cache the aggregate onto the row so `charge.paid` costs no query.
            charge.paid_amount = charge.paid_sum or Decimal("0")
        credits = list(self.payments.filter(charge__isnull=True).order_by("date"))
        charged = sum((c.amount for c in charges), Decimal("0"))
        paid = sum((c.paid_amount for c in charges), Decimal("0")) + sum(
            (p.amount for p in credits), Decimal("0")
        )
        return {
            "charges": charges,
            "credits": credits,
            "unpaid": [c for c in charges if c.due > 0],
            "charged": charged,
            "paid": paid,
            "outstanding": charged - paid,
        }

    @builtins.property
    def outstanding(self):
        """What this tenant owes right now, in figures."""
        return self.ledger()["outstanding"]


class RentCharge(models.Model):
    """One month's rent owed on a tenancy — or the balance carried in at the start."""

    RENT = "rent"
    OPENING = "opening"
    KIND_CHOICES = [(RENT, "Monthly rent"), (OPENING, "Brought forward")]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="rent_charges"
    )
    tenancy = models.ForeignKey(
        Tenancy, on_delete=models.CASCADE, related_name="charges"
    )
    # Always the first of the month the charge covers, so months sort and match
    # by simple comparison rather than by pulling the date apart.
    period = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=RENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["period", "kind"]
        constraints = [
            models.UniqueConstraint(
                "tenancy", "period", "kind", name="unique_rent_charge_period"
            )
        ]

    def __str__(self):
        return f"{self.tenancy.property} · {self.label}"

    @property
    def label(self):
        """How the row is read out — "Aug 2026", or "Brought forward"."""
        if self.kind == self.OPENING:
            return "Brought forward"
        return self.period.strftime("%b %Y")

    @property
    def paid(self):
        """Paid against this month. Uses the ledger's aggregate when it has one."""
        if hasattr(self, "paid_amount"):
            return self.paid_amount
        return self.payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0")

    @property
    def due(self):
        return self.amount - self.paid

    @property
    def is_settled(self):
        return self.due <= 0

    @property
    def amount_display(self):
        return money(self.organization, self.amount)

    @property
    def paid_display(self):
        return money(self.organization, self.paid)

    @property
    def due_display(self):
        return money(self.organization, self.due)


class RentPayment(models.Model):
    """Rent actually received — against a month of a tenancy, or against a booking.

    Every payment writes a matching income row in the Money ledger, so rent
    stops being a separate world with its own idea of what came in. The two
    stay together for the whole life of the payment: editing one edits both,
    deleting the payment takes its ledger row with it.
    """

    CASH = "cash"
    BANK = "bank"
    UPI = "upi"
    CHEQUE = "cheque"
    OTHER = "other"
    METHOD_CHOICES = [
        (CASH, "Cash"), (BANK, "Bank transfer"), (UPI, "UPI"),
        (CHEQUE, "Cheque"), (OTHER, "Other"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="rent_payments"
    )
    # Exactly one of these two says what was being paid for. A tenancy payment
    # also names the month via `charge`; a booking is one thing and needs no month.
    tenancy = models.ForeignKey(
        Tenancy, on_delete=models.CASCADE, null=True, blank=True,
        related_name="payments",
    )
    charge = models.ForeignKey(
        RentCharge, on_delete=models.CASCADE, null=True, blank=True,
        related_name="payments",
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, null=True, blank=True,
        related_name="payments",
    )
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=CASH)
    reference = models.CharField(
        max_length=60, blank=True, help_text="Cheque number, UPI reference — if there is one."
    )
    note = models.TextField(blank=True)
    # A credit the tenant already held when record-keeping started. Real money,
    # but it arrived before this app existed, so posting it now would invent
    # income on a day nothing came in.
    is_opening = models.BooleanField(default=False)
    # The Money row this payment wrote. Kept so an edit can find and correct it
    # rather than leaving a second, stale copy behind.
    transaction = models.OneToOneField(
        "finance.Transaction", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rent_payment",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.amount_display} · {self.date}"

    @property
    def amount_display(self):
        return money(self.organization, self.amount)

    @property
    def posts_to_books(self):
        """Should this payment appear in Money? Everything but a carried-in credit."""
        return not self.is_opening

    @property
    def payer_name(self):
        """Who handed the money over — the name a receipt is made out to."""
        return self._payer_name()

    @property
    def paid_for(self):
        """What was being paid for, said in one line."""
        if self.charge_id:
            return f"{self.charge.tenancy.property} · {self.charge.label}"
        if self.tenancy_id:
            return f"{self.tenancy.property} · advance"
        if self.booking_id:
            return f"{self.booking.property} · {self.booking.start_date:%d %b %Y}"
        return "Rent"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self._sync_books():
                super().save(update_fields=["transaction"])
            self._refresh_booking()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            booking = self.booking
            result = super().delete(*args, **kwargs)
            # The Money row goes with it — see `_remove_books_entry` below,
            # which handles this deletion and cascaded ones alike.
            if booking is not None:
                booking.refresh_paid()
            return result

    def _sync_books(self):
        """Write, correct or withdraw this payment's row in the Money ledger.

        Returns True when `self.transaction` changed and needs saving — the
        caller does that, so this never recurses back into `save()`.
        """
        # Imported here rather than at module load: it keeps the app registry
        # free to load rentals before finance, whatever order they're listed in.
        from finance.models import Transaction

        if not self.posts_to_books:
            if self.transaction_id:
                self.transaction.delete()
                self.transaction = None
                return True
            return False

        entry = self.transaction or Transaction(organization_id=self.organization_id)
        entry.kind = Transaction.INCOME
        entry.amount = self.amount
        entry.date = self.date
        entry.category = Category.resolve(self.organization, Category.INCOME, "Rent")
        entry.member = self._payer_member()
        entry.donor_name = "" if entry.member else self._payer_name()
        entry.note = self._books_note()
        entry.save()
        if self.transaction_id == entry.pk:
            return False
        self.transaction = entry
        return True

    def _payer_member(self):
        source = self.charge.tenancy if self.charge_id else (self.tenancy or self.booking)
        return getattr(source, "member", None) if source else None

    def _payer_name(self):
        if self.charge_id:
            return self.charge.tenancy.tenant_name
        if self.tenancy_id:
            return self.tenancy.tenant_name
        if self.booking_id:
            return self.booking.renter_name
        return ""

    def _books_note(self):
        """What the Money ledger says this row was — readable without coming back here."""
        parts = [f"Rent · {self.paid_for}"]
        if self.reference:
            parts.append(self.reference)
        if self.note:
            parts.append(self.note)
        return " · ".join(parts)

    def _refresh_booking(self):
        if self.booking_id:
            self.booking.refresh_paid()


@receiver(models.signals.post_delete, sender=RentPayment)
def _remove_books_entry(sender, instance, **kwargs):
    """Take a payment's Money row with it, however the payment came to go.

    A signal rather than a line in `delete()` because most payments don't die
    by their own delete: they're swept away with the tenancy or the booking they
    belong to, and Django's cascade never calls the method. Missing that leaves
    rent income in the books for a tenant whose record no longer exists.
    """
    if instance.transaction_id:
        from finance.models import Transaction

        Transaction.objects.filter(pk=instance.transaction_id).delete()


def _month_start(value):
    return value.replace(day=1)


def _next_month(value):
    """The first of the month after `value` — the only date arithmetic here."""
    return date(value.year + (value.month == 12), (value.month % 12) + 1, 1)


def _prev_month(value):
    """The first of the month before `value` — the mirror of `_next_month`."""
    return date(value.year - (value.month == 1), 12 if value.month == 1 else value.month - 1, 1)


def money(organization, amount):
    """An amount the way this place writes it — no stray ".00" on round sums."""
    text = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"{organization.currency_symbol}{text}"


# --- Amount in words, for slips ---------------------------------------------
# A receipt has to say the figure twice — once in numbers, once in words — so
# nobody can quietly turn a 500 into a 5000 after it's signed. The grouping is
# the Indian one (thousand, lakh, crore), which is what the currencies this app
# ships with are read in.

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
         "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
         "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
         "Eighty", "Ninety"]
# The word for a whole unit and its hundredth, per currency this app knows.
_CURRENCY_WORDS = {
    "INR": ("Rupees", "Paise"),
    "USD": ("Dollars", "Cents"),
    "EUR": ("Euros", "Cents"),
    "GBP": ("Pounds", "Pence"),
}


def _two_words(n):
    """0–99 in words."""
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_words(n):
    """0–999 in words."""
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(_ONES[hundreds] + " Hundred")
    if rest:
        parts.append(_two_words(rest))
    return " ".join(parts)


def words_for_number(value):
    """A whole number in words — 125000 → "One Lakh Twenty Five Thousand"."""
    n = int(value)
    if n == 0:
        return "Zero"
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    parts = []
    if crore:
        # Recurse so "One Hundred Crore" and beyond read correctly.
        parts.append(words_for_number(crore) + " Crore")
    if lakh:
        parts.append(_two_words(lakh) + " Lakh")
    if thousand:
        parts.append(_two_words(thousand) + " Thousand")
    if n:
        parts.append(_three_words(n))
    return " ".join(parts)


def amount_in_words(organization, amount):
    """The figure spelled out for a slip — "One Thousand Five Hundred Rupees Only"."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    whole = int(amount)
    fraction = int((amount - whole) * 100)
    major, minor = _CURRENCY_WORDS.get(organization.currency, ("", ""))
    text = words_for_number(whole)
    if major:
        text = f"{text} {major}"
    if fraction:
        piece = f"{_two_words(fraction)} {minor}" if minor else f"{_two_words(fraction)}/100"
        text = f"{text} and {piece}"
    return f"{text} Only"
