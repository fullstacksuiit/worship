import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from core.models import Member

from .forms import DonationForm
from .models import Donation, Fund


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
    by_fund = (
        donations.values("fund__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )

    context = {
        "total_amount": totals["total"] or 0,
        "total_count": totals["count"] or 0,
        "by_fund": by_fund,
        "active_fund_count": Fund.objects.filter(
            organization=org, is_active=True
        ).count(),
        "recent": donations[:10],
    }
    return render(request, "donations/dashboard.html", context)


@login_required
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
def report(request):
    org = _require_org(request)
    if org is None:
        return render(request, "donations/no_org.html")

    qs, filters = _filtered_donations(request, org)

    totals = qs.aggregate(total=Sum("amount"), count=Count("id"))
    total = totals["total"] or 0
    count = totals["count"] or 0

    by_fund = (
        qs.values("fund__name").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")
    )
    by_method = (
        qs.values("method").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")
    )
    by_month = (
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
