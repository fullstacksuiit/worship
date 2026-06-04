import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from core.models import Member
from donations.models import Donation

from .forms import BudgetForm, CategoryForm, PledgeForm, TransactionForm
from .models import Budget, Category, CategoryKind, Pledge, Transaction


def _require_org(request):
    """Return the current org or None — same 'no tenant' guard the other apps use."""
    return getattr(request, "organization", None)


def _no_org(request):
    return render(request, "donations/no_org.html")


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _current_year(request, field_name="year"):
    try:
        return int(request.GET.get(field_name))
    except (TypeError, ValueError):
        return timezone.localdate().year


# --- Unified overview ------------------------------------------------------


@login_required
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
            return redirect("finance:transactions")
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
def expense_create(request):
    return _transaction_create(request, CategoryKind.EXPENSE)


@login_required
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
            return redirect("finance:categories")

    all_categories = Category.objects.filter(organization=org).annotate(
        used=Count("transactions")
    )

    def form_for(kind):
        if posted_form is not None and submitted_kind == kind:
            return posted_form
        return CategoryForm(organization=org, kind=kind)

    context = {
        "income_categories": [c for c in all_categories if c.kind == CategoryKind.INCOME],
        "expense_categories": [c for c in all_categories if c.kind == CategoryKind.EXPENSE],
        "income_form": form_for(CategoryKind.INCOME),
        "expense_form": form_for(CategoryKind.EXPENSE),
        "open_kind": submitted_kind if posted_form is not None else None,
    }
    return render(request, "finance/categories.html", context)


# --- Budgets ---------------------------------------------------------------


@login_required
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
            return redirect("finance:budgets")
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
            return redirect("finance:pledges")
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
