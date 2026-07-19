import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from billing.access import feature_gate, has_feature
from core.models import Member
from events.models import Event

from core.permissions import Cap, require_cap

from .forms import (
    BudgetForm,
    CategoryForm,
    DonationForm,
    PledgeForm,
    TransactionForm,
)
from .models import (
    Budget,
    Category,
    CategoryKind,
    Donation,
    Fund,
    Pledge,
    Transaction,
)


def _require_org(request):
    """Return the current org or None. Centralises the 'no tenant' guard so
    every view handles a membership-less user the same way."""
    return getattr(request, "organization", None)


@login_required
def dashboard(request):
    org = _require_org(request)
    if org is None:
        return render(request, "donations/no_org.html")

    donations = Donation.objects.filter(organization=org).select_related(
        "fund", "donor"
    )

    totals = donations.aggregate(total=Sum("amount"), count=Count("id"))
    total_amount = totals["total"] or 0
    total_count = totals["count"] or 0

    by_fund = list(
        donations.values("fund__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    # Annotate each fund with its share of the total so the template can draw
    # proportion bars without re-deriving the math.
    for row in by_fund:
        row["pct"] = round((row["total"] / total_amount) * 100) if total_amount else 0

    # This-month contribution total, for an at-a-glance momentum metric.
    today = timezone.localdate()
    this_month_total = (
        donations.filter(
            received_at__year=today.year, received_at__month=today.month
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    # Average gift size — a simple but premium-feeling secondary stat.
    avg_amount = round(total_amount / total_count) if total_count else 0

    context = {
        "total_amount": total_amount,
        "total_count": total_count,
        "this_month_total": this_month_total,
        "avg_amount": avg_amount,
        "by_fund": by_fund,
        "active_fund_count": Fund.objects.filter(
            organization=org, is_active=True
        ).count(),
        "recent": donations[:10],
    }

    # When the org's plan includes the events module, surface the next few
    # gatherings right on the landing dashboard so the schedule is one glance away.
    if has_feature(request, "events"):
        context["upcoming_events"] = list(
            Event.objects.filter(
                organization=org, starts_at__gte=timezone.now()
            ).select_related("lead").order_by("starts_at")[:4]
        )

    return render(request, "donations/dashboard.html", context)


@login_required
@require_cap(Cap.DONATIONS_RECORD)
def donation_create(request):
    org = _require_org(request)
    if org is None:
        return render(request, "donations/no_org.html")

    if request.method == "POST":
        form = DonationForm(request.POST, organization=org)
        if form.is_valid():
            donation = form.save(commit=False)
            donation.recorded_by = request.user
            donation.save()
            messages.success(
                request,
                f"Receipt #{donation.receipt_number} recorded — "
                f"{donation.amount} {donation.currency} to {donation.fund.name}.",
            )
            return redirect("donations:dashboard")
    else:
        initial = {"received_at": timezone.localdate()}
        # Pre-select the donor when arriving from a member's page (?donor=<pk>),
        # but only if that member really belongs to the current org.
        donor_id = request.GET.get("donor")
        if donor_id and Member.objects.filter(
            pk=donor_id, organization=org
        ).exists():
            initial["donor"] = donor_id
        form = DonationForm(organization=org, initial=initial)

    return render(request, "donations/donation_form.html", {"form": form})


# --- Reports ---------------------------------------------------------------


def _parse_date(value):
    """Parse an ISO date (YYYY-MM-DD) from a query param, or None if absent/bad."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _filtered_donations(request, org):
    """Apply the report's date-range and fund filters to an org's donations.
    Shared by the report page and the CSV export so they always agree."""
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))
    fund_id = request.GET.get("fund") or None

    qs = Donation.objects.filter(organization=org).select_related("fund", "donor")
    if start:
        qs = qs.filter(received_at__gte=start)
    if end:
        qs = qs.filter(received_at__lte=end)
    if fund_id and Fund.objects.filter(pk=fund_id, organization=org).exists():
        qs = qs.filter(fund_id=fund_id)
    else:
        fund_id = None  # ignore a fund that isn't this org's

    return qs, {"start": start, "end": end, "fund_id": fund_id}


@login_required
@require_cap(Cap.REPORTS_VIEW)
def report(request):
    org = _require_org(request)
    if org is None:
        return render(request, "donations/no_org.html")

    qs, filters = _filtered_donations(request, org)

    totals = qs.aggregate(total=Sum("amount"), count=Count("id"))
    total = totals["total"] or 0
    count = totals["count"] or 0

    by_fund = list(
        qs.values("fund__name").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")
    )
    by_method = list(
        qs.values("method").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")
    )
    by_month = list(
        qs.annotate(month=TruncMonth("received_at"))
        .values("month")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("month")
    )
    # Distinct members who gave (free-text/anonymous gifts have no member).
    member_donors = qs.exclude(donor=None).values("donor").distinct().count()

    method_labels = dict(Donation._meta.get_field("method").choices)
    by_method = [
        {**row, "label": method_labels.get(row["method"], row["method"])}
        for row in by_method
    ]

    # Annotate each breakdown row with its share of the grand total so templates
    # can draw proportion bars. Monthly bars scale to the peak month instead, to
    # keep the tallest bar full-width regardless of the period's size.
    for row in by_fund:
        row["pct"] = round((row["total"] / total) * 100) if total else 0
    for row in by_method:
        row["pct"] = round((row["total"] / total) * 100) if total else 0
    peak_month = max((r["total"] for r in by_month), default=0)
    for row in by_month:
        row["pct"] = round((row["total"] / peak_month) * 100) if peak_month else 0

    context = {
        "filters": filters,
        "funds": Fund.objects.filter(organization=org).order_by("name"),
        "total": total,
        "count": count,
        "average": (total / count) if count else 0,
        "member_donors": member_donors,
        "by_fund": by_fund,
        "by_method": by_method,
        "by_month": by_month,
        "querystring": request.GET.urlencode(),
    }
    return render(request, "donations/report.html", context)


@login_required
@require_cap(Cap.REPORTS_VIEW)
def report_export(request):
    org = _require_org(request)
    if org is None:
        return render(request, "donations/no_org.html")

    qs, _ = _filtered_donations(request, org)
    qs = qs.order_by("received_at", "receipt_number")

    response = HttpResponse(content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}-donations-{stamp}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        ["Receipt", "Date", "Donor", "Fund", "Method", "Amount", "Currency", "Reference"]
    )
    for d in qs:
        writer.writerow(
            [
                d.receipt_number,
                d.received_at.isoformat(),
                d.display_donor,
                d.fund.name,
                d.get_method_display(),
                d.amount,
                d.currency,
                d.reference,
            ]
        )
    return response


# ===========================================================================
# Finance: the wider books — non-donation income/expense, budgets, pledges,
# and the unified overview that sums donations and transactions together.
# These pages are gated behind the "finance" plan feature; the donation pages
# above are always available.
# ===========================================================================


def _no_org(request):
    return render(request, "donations/no_org.html")


def _current_year(request, field_name="year"):
    try:
        return int(request.GET.get(field_name))
    except (TypeError, ValueError):
        return timezone.localdate().year


# --- Unified overview ------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def overview(request):
    """The single financial picture for a worship place: donations + other income
    coming in, expenses going out, and the net balance, for a chosen year."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    year = _current_year(request)

    donations = Donation.objects.filter(organization=org, received_at__year=year)
    txns = Transaction.objects.filter(organization=org, occurred_at__year=year)
    income_txns = txns.filter(kind=CategoryKind.INCOME)
    expense_txns = txns.filter(kind=CategoryKind.EXPENSE)

    donation_total = donations.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    income_total = income_txns.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense_total = expense_txns.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    total_income = donation_total + income_total
    net = total_income - expense_total

    # Money-out broken down by expense category for the year.
    by_expense_category = (
        expense_txns.values("category__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )

    # A combined recent ledger: latest donations and transactions interleaved.
    feed = [
        {
            "when": t.occurred_at,
            "label": t.category.name,
            "party": t.party,
            "kind": t.kind,
            "amount": t.amount,
            "currency": t.currency,
        }
        for t in txns.select_related("category")[:10]
    ] + [
        {
            "when": d.received_at,
            "label": f"Donation · {d.fund.name}",
            "party": d.display_donor,
            "kind": CategoryKind.INCOME,
            "amount": d.amount,
            "currency": d.currency,
        }
        for d in donations.select_related("fund")[:10]
    ]
    feed.sort(key=lambda r: r["when"], reverse=True)
    feed = feed[:10]

    # Years that actually have activity, so the year picker only offers real ones.
    years = sorted(
        set(
            donations.model.objects.filter(organization=org)
            .dates("received_at", "year")
            .values_list("received_at__year", flat=True)
        )
        | set(
            Transaction.objects.filter(organization=org)
            .dates("occurred_at", "year")
            .values_list("occurred_at__year", flat=True)
        )
        | {year, timezone.localdate().year},
        reverse=True,
    )

    context = {
        "year": year,
        "years": years,
        "donation_total": donation_total,
        "income_total": income_total,
        "total_income": total_income,
        "expense_total": expense_total,
        "net": net,
        "by_expense_category": by_expense_category,
        "feed": feed,
    }
    return render(request, "finance/overview.html", context)


# --- Transactions (income & expense) --------------------------------------

_KIND_META = {
    CategoryKind.INCOME: {
        "noun": "income",
        "title": "Record income",
        "party_label": "Received from",
        "blurb": "Non-donation income — hall rental, sales, grants, events.",
    },
    CategoryKind.EXPENSE: {
        "noun": "expense",
        "title": "Record expense",
        "party_label": "Paid to",
        "blurb": "Money going out — utilities, salaries, maintenance, payouts.",
    },
}


def _transaction_create(request, kind):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    meta = _KIND_META[kind]
    has_category = Category.objects.filter(
        organization=org, kind=kind, is_active=True
    ).exists()

    if request.method == "POST":
        form = TransactionForm(request.POST, organization=org, kind=kind)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.recorded_by = request.user
            txn.save()
            messages.success(
                request,
                f"Voucher #{txn.voucher_number} recorded — "
                f"{txn.amount} {txn.currency} ({txn.category.name}).",
            )
            return redirect("donations:transactions")
    else:
        form = TransactionForm(
            organization=org,
            kind=kind,
            initial={"occurred_at": timezone.localdate()},
        )

    return render(
        request,
        "finance/transaction_form.html",
        {"form": form, "meta": meta, "kind": kind, "has_category": has_category},
    )


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def expense_create(request):
    return _transaction_create(request, CategoryKind.EXPENSE)


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def income_create(request):
    return _transaction_create(request, CategoryKind.INCOME)


def _filtered_transactions(request, org):
    """Apply the ledger's kind / date-range / category filters. Shared by the
    ledger page and the CSV export so they always agree."""
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))
    kind = request.GET.get("kind") or None
    category_id = request.GET.get("category") or None

    qs = Transaction.objects.filter(organization=org).select_related("category")
    if kind in (CategoryKind.INCOME, CategoryKind.EXPENSE):
        qs = qs.filter(kind=kind)
    else:
        kind = None
    if start:
        qs = qs.filter(occurred_at__gte=start)
    if end:
        qs = qs.filter(occurred_at__lte=end)
    if category_id and Category.objects.filter(
        pk=category_id, organization=org
    ).exists():
        qs = qs.filter(category_id=category_id)
    else:
        category_id = None

    filters = {"start": start, "end": end, "kind": kind, "category_id": category_id}
    return qs, filters


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def transactions(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    qs, filters = _filtered_transactions(request, org)

    income_total = (
        qs.filter(kind=CategoryKind.INCOME).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    expense_total = (
        qs.filter(kind=CategoryKind.EXPENSE).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )

    context = {
        "transactions": qs[:300],
        "filters": filters,
        "categories": Category.objects.filter(organization=org).order_by(
            "kind", "name"
        ),
        "income_total": income_total,
        "expense_total": expense_total,
        "net": income_total - expense_total,
        "querystring": request.GET.urlencode(),
    }
    return render(request, "finance/transactions.html", context)


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def transactions_export(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    qs, _ = _filtered_transactions(request, org)
    qs = qs.order_by("occurred_at", "voucher_number")

    response = HttpResponse(content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}-ledger-{stamp}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        ["Voucher", "Date", "Type", "Category", "Party", "Method",
         "Amount", "Signed", "Currency", "Reference"]
    )
    for t in qs:
        writer.writerow(
            [
                t.voucher_number,
                t.occurred_at.isoformat(),
                t.get_kind_display(),
                t.category.name,
                t.party,
                t.get_method_display(),
                t.amount,
                t.signed_amount,
                t.currency,
                t.reference,
            ]
        )
    return response


# --- Categories ------------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def categories(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    # Which side a submitted add-form belongs to comes from the POST.
    submitted_kind = request.POST.get("kind")
    if submitted_kind not in (CategoryKind.INCOME, CategoryKind.EXPENSE):
        submitted_kind = CategoryKind.INCOME

    posted_form = None
    if request.method == "POST":
        posted_form = CategoryForm(
            request.POST, organization=org, kind=submitted_kind
        )
        if posted_form.is_valid():
            category = posted_form.save()
            messages.success(
                request,
                f"Added {category.get_kind_display().lower()} category "
                f"“{category.name}”.",
            )
            return redirect("donations:categories")

    all_categories = Category.objects.filter(organization=org).annotate(
        used=Count("transactions", distinct=True),
        total=Sum("transactions__amount"),
    )
    income = [c for c in all_categories if c.kind == CategoryKind.INCOME]
    expense = [c for c in all_categories if c.kind == CategoryKind.EXPENSE]

    # Income sources fed by other modules, shown read-only so the same money is
    # never recorded twice: donations (their own module) and any system income
    # categories such as rent (posted from the Rentals module).
    donation_agg = Donation.objects.filter(organization=org).aggregate(
        total=Sum("amount"), count=Count("id")
    )
    income_sources = [
        {
            "name": "Donations",
            "blurb": "Gifts recorded in the donations module",
            "total": donation_agg["total"] or Decimal("0"),
            "count": donation_agg["count"] or 0,
            "url_name": "donations:dashboard",
        }
    ]
    for c in income:
        if c.is_system:
            income_sources.append(
                {
                    "name": c.name,
                    "blurb": "Posted automatically from the Rentals module",
                    "total": c.total or Decimal("0"),
                    "count": c.used,
                    "url_name": "rentals:overview",
                }
            )

    def form_for(kind):
        if posted_form is not None and submitted_kind == kind:
            return posted_form
        return CategoryForm(organization=org, kind=kind)

    context = {
        # Only user-managed categories are editable in the list; system ones
        # (rent) appear under income_sources instead.
        "income_categories": [c for c in income if not c.is_system],
        "expense_categories": expense,
        "income_sources": income_sources,
        "income_form": form_for(CategoryKind.INCOME),
        "expense_form": form_for(CategoryKind.EXPENSE),
        "open_kind": submitted_kind if posted_form is not None else None,
    }
    return render(request, "finance/categories.html", context)


# --- Budgets ---------------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def budgets(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if request.method == "POST":
        form = BudgetForm(request.POST, organization=org)
        if form.is_valid():
            budget = form.save()
            messages.success(
                request,
                f"Budget set: {budget.category.name} {budget.year} — "
                f"{budget.amount} {org.currency}.",
            )
            return redirect("donations:budgets")
    else:
        form = BudgetForm(
            organization=org, initial={"year": timezone.localdate().year}
        )

    rows = []
    for budget in Budget.objects.filter(organization=org).select_related("category"):
        actual = (
            Transaction.objects.filter(
                organization=org,
                category=budget.category,
                occurred_at__year=budget.year,
            ).aggregate(t=Sum("amount"))["t"]
            or Decimal("0")
        )
        planned = budget.amount or Decimal("0")
        pct = int((actual / planned) * 100) if planned else 0
        rows.append(
            {
                "budget": budget,
                "actual": actual,
                "remaining": planned - actual,
                "pct": pct,
                "bar": min(pct, 100),
                "over": actual > planned,
            }
        )

    has_category = Category.objects.filter(organization=org, is_active=True).exists()
    return render(
        request,
        "finance/budgets.html",
        {"form": form, "rows": rows, "has_category": has_category},
    )


# --- Pledges ---------------------------------------------------------------


@login_required
@feature_gate("finance", "Finance")
@require_cap(Cap.FINANCE_ACCESS)
def pledges(request):
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if request.method == "POST":
        form = PledgeForm(request.POST, organization=org)
        if form.is_valid():
            pledge = form.save()
            messages.success(
                request,
                f"Pledge recorded: {pledge.member.full_name} → "
                f"{pledge.fund.name} {pledge.year}.",
            )
            return redirect("donations:pledges")
    else:
        form = PledgeForm(
            organization=org, initial={"year": timezone.localdate().year}
        )

    rows = []
    for pledge in Pledge.objects.filter(organization=org).select_related(
        "member", "fund"
    ):
        fulfilled = pledge.fulfilled_amount()
        pledged = pledge.amount or Decimal("0")
        pct = int((fulfilled / pledged) * 100) if pledged else 0
        rows.append(
            {
                "pledge": pledge,
                "fulfilled": fulfilled,
                "remaining": max(pledged - fulfilled, Decimal("0")),
                "pct": min(pct, 100),
                "met": fulfilled >= pledged,
            }
        )

    can_pledge = Member.objects.filter(organization=org, is_active=True).exists()
    return render(
        request,
        "finance/pledges.html",
        {"form": form, "rows": rows, "can_pledge": can_pledge},
    )
