"""Printable rent slips — the rent *demand* (a bill for what's owed) and the
rent *payment receipt* (proof a tenant paid).

Each slip is one self-contained HTML page: it reads as a clean document on
screen, prints tidily (`@media print` hides the toolbar), and can be saved as a
PDF. A true server-rendered download is offered through WeasyPrint when its
native libraries are installed on the host; where they aren't, `render_pdf`
returns ``None`` and the view falls back to the printable page so a download link
never errors out.
"""

from decimal import Decimal

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone


def receipt_context(payment, as_of=None):
    """Everything the payment-receipt slip needs: the receipt itself plus the
    unit's account position, so the tenant can see where they stand after paying."""
    unit = payment.unit
    as_of = as_of or timezone.localdate()
    paid_total = unit.paid_total()
    balance = unit.balance(as_of=as_of, paid_total=paid_total)
    return {
        "unit": unit,
        "payment": payment,
        "as_of": as_of,
        "balance": balance,
        "in_arrears": unit.is_active and balance > 0,
    }


def demand_context(unit, as_of=None):
    """Everything the rent-demand slip needs: the full running statement (opening
    balance, monthly charges, payments) and the outstanding amount due."""
    as_of = as_of or timezone.localdate()
    entries = unit.ledger(as_of=as_of)
    amount_due = entries[-1]["running"] if entries else Decimal("0")
    return {
        "unit": unit,
        "as_of": as_of,
        "entries": entries,
        "expected": unit.expected_to_date(as_of),
        "paid_total": unit.paid_total(),
        "months_due": unit.months_due(as_of),
        "amount_due": amount_due,
        "in_arrears": unit.is_active and amount_due > 0,
    }


def render_pdf(request, template, context, filename):
    """Render `template` to a downloadable PDF via WeasyPrint.

    Returns an ``HttpResponse`` carrying the PDF, or ``None`` when WeasyPrint (or
    its native pango/cairo libraries) isn't available on this host — the caller
    then serves the printable HTML page instead, so the download link degrades
    gracefully rather than raising a 500."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        return None

    html = render_to_string(template, {**context, "pdf": True}, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
