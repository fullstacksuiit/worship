import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.permissions import cap_required

from .forms import TransactionForm
from .models import Transaction


def _totals(qs):
    income = qs.filter(kind=Transaction.INCOME).aggregate(s=Sum("amount"))["s"] or 0
    expense = qs.filter(kind=Transaction.EXPENSE).aggregate(s=Sum("amount"))["s"] or 0
    return {"income": income, "expense": expense, "net": income - expense}


@login_required
def overview(request):
    org = request.organization
    year = int(request.GET.get("year") or timezone.localdate().year)
    qs = Transaction.objects.filter(organization=org, date__year=year).select_related("category", "member")
    totals = _totals(qs)

    years = sorted(
        {d.year for d in Transaction.objects.filter(organization=org).dates("date", "year")}
        | {timezone.localdate().year},
        reverse=True,
    )
    return render(request, "finance/overview.html", {
        "org": org,
        "totals": totals,
        "recent": qs[:10],
        "year": year,
        "years": years,
    })


@login_required
@cap_required("manage_money")
def add(request, kind):
    org = request.organization
    if kind not in (Transaction.INCOME, Transaction.EXPENSE):
        return redirect("finance:overview")

    if request.method == "POST":
        form = TransactionForm(request.POST, org=org, kind=kind)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.organization = org
            txn.kind = kind
            txn.save()
            messages.success(request, "Entry saved.")
            return redirect("finance:overview")
    else:
        form = TransactionForm(org=org, kind=kind, initial={"date": timezone.localdate()})

    donation_term = org.preset["donation_term"]
    heading = f"Record {donation_term} / income" if kind == Transaction.INCOME else "Record expense"
    return render(request, "finance/form.html", {
        "form": form, "kind": kind, "heading": heading, "mode": "add",
    })


@login_required
@cap_required("manage_money")
def edit(request, pk):
    org = request.organization
    txn = get_object_or_404(Transaction, pk=pk, organization=org)
    if request.method == "POST":
        form = TransactionForm(request.POST, instance=txn, org=org, kind=txn.kind)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("finance:ledger")
    else:
        form = TransactionForm(instance=txn, org=org, kind=txn.kind)
    heading = "Edit entry"
    return render(request, "finance/form.html", {
        "form": form, "kind": txn.kind, "heading": heading, "mode": "edit", "txn": txn,
    })


@login_required
@cap_required("manage_money")
def delete(request, pk):
    org = request.organization
    txn = get_object_or_404(Transaction, pk=pk, organization=org)
    if request.method == "POST":
        txn.delete()
        messages.success(request, "Entry removed.")
        return redirect("finance:ledger")
    return render(request, "finance/confirm_delete.html", {"txn": txn})


@login_required
def ledger(request):
    org = request.organization
    kind = request.GET.get("kind", "")
    qs = Transaction.objects.filter(organization=org).select_related("category", "member")
    if kind in (Transaction.INCOME, Transaction.EXPENSE):
        qs = qs.filter(kind=kind)
    return render(request, "finance/ledger.html", {
        "org": org, "transactions": qs, "kind": kind, "totals": _totals(qs),
    })


@login_required
def export_csv(request):
    org = request.organization
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="ledger-{date.today()}.csv"'
    writer = csv.writer(resp)
    writer.writerow(["Date", "Type", "Category", "Party", "Amount", "Note"])
    for t in Transaction.objects.filter(organization=org).select_related("category", "member"):
        writer.writerow([t.date, t.get_kind_display(), t.category or "", t.party, t.amount, t.note])
    return resp
