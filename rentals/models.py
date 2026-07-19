from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from core.models import TenantScopedModel
from donations.models import PaymentMethod

# The finance income category rent receipts are filed under, so rental income
# shows up in the unified finance picture alongside everything else. One category
# covers every property type — the per-type breakdown lives on the rentals
# overview, not in the chart of accounts. The code is stable; the display name is
# only used when the category is first created.
RENTAL_INCOME_CATEGORY_CODE = "rental_income"
RENTAL_INCOME_CATEGORY_NAME = "Rental Income"

# The finance expense category rent rebates/concessions are filed under. Rent is
# charged gross (the full agreed rent), so a rebate for poor condition or a
# goodwill discount is booked as an offsetting expense — the concession stays
# visible in the books and net rental income comes out right. See RentAdjustment.
RENTAL_REBATE_CATEGORY_CODE = "rent_rebate"
RENTAL_REBATE_CATEGORY_NAME = "Rent Rebates & Concessions"

# Starting-point property types seeded for every new organization. Faith-agnostic
# — orgs rename, extend, or disable these to match whatever they actually let out
# (shops, halls, rooms, stalls, farmland, ...).
DEFAULT_PROPERTY_TYPES = [
    ("shop", "Shop"),
    ("hall", "Hall"),
    ("room", "Room"),
    ("stall", "Stall"),
    ("land", "Land"),
]


class PropertyType(TenantScopedModel):
    """A kind of rentable property an organization lets out — Shop, Hall, Room,
    Stall, Land, or anything the org defines. Each org keeps its own list; the
    defaults are only a starting point and impose no rules."""

    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=200, blank=True)
    # Optional emoji/icon shown beside the type in the UI (e.g. "🏪", "🏛️").
    icon = models.CharField(max_length=8, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_property_type_code_per_org",
            ),
        ]

    def __str__(self):
        return self.name


class RentalUnit(TenantScopedModel):
    """A rentable unit on a worship place's premises — a shop, hall, room, stall,
    plot of land, or any type the org has defined. It is let to a tenant for a
    monthly rent. The tenant is recorded here by name and phone (a lessee, not a
    congregation member), and the agreed rent plus the tenancy start date are the
    basis for the arrears calculation."""

    # What kind of property this is. Nullable so an "untyped" unit is legal (and
    # so the rename migration can backfill existing rows). PROTECT stops a type
    # from being deleted while units still reference it.
    property_type = models.ForeignKey(
        PropertyType,
        on_delete=models.PROTECT,
        related_name="units",
        null=True,
        blank=True,
    )

    name = models.CharField(
        max_length=120, help_text="e.g. “Shop 1”, “Main Hall”, “Corner Stall”."
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Location or what the unit is used for.",
    )

    # The tenant as a standalone party (not linked to the Member directory).
    tenant_name = models.CharField(max_length=200)
    tenant_phone = models.CharField(max_length=40, blank=True)

    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2)
    deposit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    # Balance carried in when the unit was first entered into the system — rent
    # already owed from before tracking began. Positive = the tenant is in
    # arrears at the outset; negative = they had paid ahead / hold a credit.
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Rent already owed (or, if negative, paid ahead) before tracking "
        "started here. Becomes the first line of the ledger.",
    )
    # Currency captured from the org at creation for historical accuracy.
    currency = models.CharField(max_length=3, blank=True)

    # When the tenancy began — rent is considered due from this month onward.
    start_date = models.DateField()

    # False once the unit is vacated; arrears stop accruing for inactive units.
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["organization", "is_active"])]

    def save(self, *args, **kwargs):
        if not self.currency and self.organization_id:
            self.currency = self.organization.currency
        super().save(*args, **kwargs)

    def months_due(self, as_of=None):
        """How many monthly rents should have fallen due by `as_of` (inclusive of
        both the start month and the current month). Zero before the tenancy began
        or once the unit is marked inactive."""
        if not self.is_active:
            return 0
        as_of = as_of or timezone.localdate()
        if as_of < self.start_date:
            return 0
        return (
            (as_of.year - self.start_date.year) * 12
            + (as_of.month - self.start_date.month)
            + 1
        )

    def rate_schedule(self):
        """The unit's rent over time as sorted ``((year, month), rate)`` break
        points. The tenancy's opening rate is `monthly_rent` from the start month;
        each `RentRevision` layers a new rate from its effective month onward. Used
        to charge every month at the rate that was actually in force then, so a
        rent increase or decrease never rewrites the arrears of past months.

        Relies on `self.revisions.all()` — prefetch it in list views to avoid a
        query per unit."""
        points = [
            ((self.start_date.year, self.start_date.month), self.monthly_rent or Decimal("0"))
        ]
        for rev in self.revisions.all():
            points.append(
                ((rev.effective_year, rev.effective_month), rev.monthly_rent)
            )
        points.sort(key=lambda p: p[0])
        return points

    def rent_for_period(self, year, month, schedule=None):
        """The monthly rent in force for a given ``(year, month)`` — the latest
        revision effective on or before it, or the opening rate. Pass a `schedule`
        from `rate_schedule()` to reuse it across a month-by-month walk."""
        schedule = self.rate_schedule() if schedule is None else schedule
        rate = schedule[0][1] if schedule else Decimal("0")
        for period, r in schedule:
            if period <= (year, month):
                rate = r
            else:
                break
        return rate

    def current_rent(self, as_of=None):
        """The rent in force right now (or at `as_of`) — the headline figure and
        the amount a fresh receipt defaults to."""
        as_of = as_of or timezone.localdate()
        return self.rent_for_period(as_of.year, as_of.month)

    def expected_to_date(self, as_of=None):
        """Total rent that should have been charged by `as_of`, gross — every
        month it has been let, each at the rate then in force. Rebates don't reduce
        this (rent is charged gross); they land separately as credits."""
        n = self.months_due(as_of)
        if not n:
            return Decimal("0")
        schedule = self.rate_schedule()
        total = Decimal("0")
        y, m = self.start_date.year, self.start_date.month
        for _ in range(n):
            total += self.rent_for_period(y, m, schedule)
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return total

    def adjustments_total(self, as_of=None):
        """Total rebates/concessions whose month has come due by `as_of` — credits
        that reduce what the tenant owes. Future-dated rebates don't count yet, the
        same way a future month's rent isn't charged yet.

        Relies on `self.adjustments.all()` — prefetch it in list views."""
        as_of = as_of or timezone.localdate()
        cutoff = (as_of.year, as_of.month)
        return sum(
            (a.amount for a in self.adjustments.all()
             if (a.period_year, a.period_month) <= cutoff),
            Decimal("0"),
        )

    def next_due_period(self, as_of=None):
        """The earliest month — walking from the tenancy start up to `as_of` — that
        has no rent receipt yet. This is the period a fresh payment most likely
        settles, so the record-rent form can default to it instead of today's
        month (a tenant three months behind is paying off March, not July).

        Returns a ``(year, month)`` tuple. Falls back to the current month once
        every past month is receipted, and to the start month before the tenancy
        has begun."""
        as_of = as_of or timezone.localdate()
        start = (self.start_date.year, self.start_date.month)
        current = (as_of.year, as_of.month)
        if current < start:
            return start
        paid = set(self.rent_payments.values_list("period_year", "period_month"))
        y, m = start
        while (y, m) <= current:
            if (y, m) not in paid:
                return (y, m)
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return current

    def paid_total(self):
        """Everything actually received against this unit, all periods."""
        return self.rent_payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    def balance(self, as_of=None, paid_total=None):
        """Outstanding rent: positive means the tenant owes (in arrears),
        negative means they've paid ahead. Includes any opening balance carried
        in. Pass `paid_total` to reuse an already computed/annotated sum and
        avoid a per-unit query in list views."""
        paid = self.paid_total() if paid_total is None else paid_total
        opening = self.opening_balance or Decimal("0")
        return (
            opening
            + self.expected_to_date(as_of)
            - self.adjustments_total(as_of)
            - paid
        )

    def ledger(self, as_of=None):
        """A running account statement for this unit: the opening balance, one
        rent charge for every month it has been let (at the rate then in force),
        any rebates as credits, and every payment received — each line carrying the
        running balance owed after it. Ordered by date, and within a day: opening,
        then charge, then rebate, then payment. The final running balance equals
        `balance()`."""
        as_of = as_of or timezone.localdate()
        opening = self.opening_balance or Decimal("0")
        schedule = self.rate_schedule()

        entries = []
        # Opening balance, only when there is one to carry in.
        if opening:
            entries.append(
                {
                    "date": self.start_date,
                    "sort": 0,
                    "kind": "opening",
                    "label": "Opening balance",
                    "charge": opening if opening > 0 else Decimal("0"),
                    "credit": -opening if opening < 0 else Decimal("0"),
                }
            )

        # One rent charge per month the unit has been let, dated the 1st, at the
        # rent in force that month.
        y, m = self.start_date.year, self.start_date.month
        for _ in range(self.months_due(as_of)):
            import calendar

            entries.append(
                {
                    "date": date(y, m, 1),
                    "sort": 1,
                    "kind": "charge",
                    "label": f"Rent due · {calendar.month_name[m]} {y}",
                    "charge": self.rent_for_period(y, m, schedule),
                    "credit": Decimal("0"),
                }
            )
            m += 1
            if m > 12:
                m, y = 1, y + 1

        # Rebates/concessions whose month has come due, as credits.
        cutoff = (as_of.year, as_of.month)
        for a in self.adjustments.all():
            if (a.period_year, a.period_month) > cutoff:
                continue
            entries.append(
                {
                    "date": a.dated_on,
                    "sort": 2,
                    "kind": "rebate",
                    "label": f"Rebate · {a.reason} ({a.period_label})",
                    "charge": Decimal("0"),
                    "credit": a.amount,
                    "adjustment": a,
                }
            )

        # Every payment received, as a credit.
        for p in self.rent_payments.all():
            entries.append(
                {
                    "date": p.paid_on,
                    "sort": 3,
                    "kind": "payment",
                    "label": f"Payment · receipt #{p.receipt_number} ({p.period_label})",
                    "charge": Decimal("0"),
                    "credit": p.amount,
                    "payment": p,
                }
            )

        entries.sort(key=lambda e: (e["date"], e["sort"]))

        running = Decimal("0")
        for e in entries:
            running += e["charge"] - e["credit"]
            e["running"] = running
        return entries

    def __str__(self):
        return f"{self.name} — {self.tenant_name}"


class RentPayment(TenantScopedModel):
    """A single rent receipt from a tenant for a given month. Each payment also
    posts a matching income entry into Finance (see `transaction`) so rental income
    flows into the organization's books automatically."""

    unit = models.ForeignKey(
        RentalUnit, on_delete=models.CASCADE, related_name="rent_payments"
    )

    # The month this payment settles, kept separate from the date it was received
    # so a late or advance payment is still attributed to the right period.
    period_year = models.PositiveIntegerField()
    period_month = models.PositiveSmallIntegerField()  # 1–12

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True)
    method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    paid_on = models.DateField()
    reference = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)

    # Auto-incrementing, per-organization rent receipt number (assigned on save).
    receipt_number = models.PositiveIntegerField(null=True, blank=True)

    # The finance income entry created for this receipt. SET_NULL so deleting the
    # ledger entry doesn't erase the rent record (and vice versa).
    transaction = models.ForeignKey(
        "donations.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rent_payment",
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_rent_payments",
    )

    class Meta:
        ordering = ["-period_year", "-period_month", "-paid_on"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="rent_payment_amount_positive",
            ),
            models.CheckConstraint(
                check=models.Q(period_month__gte=1) & models.Q(period_month__lte=12),
                name="rent_payment_month_valid",
            ),
            models.UniqueConstraint(
                fields=["organization", "receipt_number"],
                name="unique_rent_receipt_number_per_org",
            ),
        ]
        indexes = [models.Index(fields=["organization", "unit"])]

    def save(self, *args, **kwargs):
        if not self.currency and self.organization_id:
            self.currency = self.organization.currency
        if self.receipt_number is None and self.organization_id:
            last = (
                RentPayment.objects.filter(organization_id=self.organization_id)
                .exclude(receipt_number=None)
                .order_by("-receipt_number")
                .values_list("receipt_number", flat=True)
                .first()
            )
            self.receipt_number = (last or 0) + 1
        super().save(*args, **kwargs)

    @property
    def period_label(self):
        """Human-friendly period, e.g. “March 2026”."""
        import calendar

        name = calendar.month_name[self.period_month] if 1 <= self.period_month <= 12 else "?"
        return f"{name} {self.period_year}"

    def __str__(self):
        return f"Rent #{self.receipt_number} · {self.unit.name} · {self.period_label}"


class RentRevision(TenantScopedModel):
    """A dated change to a unit's monthly rent — an increase or a decrease that
    takes effect from a given month and applies to every month from then on.

    The unit's own `monthly_rent`/`start_date` is the opening rate; each revision
    layers a new rate on top from its effective month. Historic months keep the
    rate that was in force at the time, so arrears and past demands stay accurate
    even after the rent moves. See `RentalUnit.rate_schedule`."""

    unit = models.ForeignKey(
        RentalUnit, on_delete=models.CASCADE, related_name="revisions"
    )

    # The month the new rent takes effect, held as year+month (like RentPayment's
    # period) so it lines up cleanly with the month-by-month rent charge.
    effective_year = models.PositiveIntegerField()
    effective_month = models.PositiveSmallIntegerField()  # 1–12

    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2)
    # A short label for why the rent changed (e.g. "Annual revision", "Market
    # drop") shown in the rent history.
    reason = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_rent_revisions",
    )

    class Meta:
        ordering = ["effective_year", "effective_month"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(monthly_rent__gte=Decimal("0")),
                name="rent_revision_amount_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(effective_month__gte=1)
                & models.Q(effective_month__lte=12),
                name="rent_revision_month_valid",
            ),
            models.UniqueConstraint(
                fields=["unit", "effective_year", "effective_month"],
                name="unique_rent_revision_per_unit_period",
            ),
        ]

    @property
    def effective_label(self):
        """Human-friendly effective month, e.g. “April 2025”."""
        import calendar

        name = (
            calendar.month_name[self.effective_month]
            if 1 <= self.effective_month <= 12
            else "?"
        )
        return f"{name} {self.effective_year}"

    def __str__(self):
        return f"{self.unit.name} → {self.monthly_rent} from {self.effective_label}"


class RentAdjustment(TenantScopedModel):
    """A one-off credit against a unit's rent for a single month — a rebate for
    poor condition, a goodwill discount, a negotiated concession.

    Rent is charged gross, so an adjustment does two things: it reduces what the
    tenant owes on the rent statement (a credit), and it posts a matching expense
    into Finance (see `transaction`) so the concession is visible in the books and
    net rental income comes out right."""

    unit = models.ForeignKey(
        RentalUnit, on_delete=models.CASCADE, related_name="adjustments"
    )

    # Which month's rent this rebate applies to (so it only bites once that month
    # has come due, the same way a charge does).
    period_year = models.PositiveIntegerField()
    period_month = models.PositiveSmallIntegerField()  # 1–12

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True)
    # Why the rebate was granted — shown on the ledger and copied to the finance
    # entry (e.g. "Poor condition", "Goodwill", "Repairs delayed").
    reason = models.CharField(max_length=120)
    # When it was granted, used as the finance entry's date and the ledger line.
    dated_on = models.DateField()
    note = models.TextField(blank=True)

    # The finance expense entry created for this rebate. SET_NULL so deleting the
    # ledger entry doesn't erase the rebate record (and vice versa).
    transaction = models.ForeignKey(
        "donations.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rent_adjustment",
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_rent_adjustments",
    )

    class Meta:
        ordering = ["-period_year", "-period_month", "-dated_on"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal("0")),
                name="rent_adjustment_amount_positive",
            ),
            models.CheckConstraint(
                check=models.Q(period_month__gte=1)
                & models.Q(period_month__lte=12),
                name="rent_adjustment_month_valid",
            ),
        ]
        indexes = [models.Index(fields=["organization", "unit"])]

    def save(self, *args, **kwargs):
        if not self.currency and self.organization_id:
            self.currency = self.organization.currency
        super().save(*args, **kwargs)

    @property
    def period_label(self):
        """Human-friendly period, e.g. “March 2026”."""
        import calendar

        name = (
            calendar.month_name[self.period_month]
            if 1 <= self.period_month <= 12
            else "?"
        )
        return f"{name} {self.period_year}"

    def __str__(self):
        return f"Rebate {self.amount} · {self.unit.name} · {self.period_label}"
