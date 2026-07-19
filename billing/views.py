"""Customer-facing billing pages: a subscription overview (plan, status, usage,
invoices) and a pricing table to switch plans. With no payment gateway wired in
yet, plan changes are applied directly via the subscription lifecycle service
and recorded with provider="manual"."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Member, OrgRole, UserOrgMembership

from core.permissions import Cap, require_cap
from .models import Plan
from .services import start_subscription

# Roles allowed to change the org's plan / billing.
BILLING_ROLES = (OrgRole.OWNER, OrgRole.ADMIN)


def _require_org(request):
    return getattr(request, "organization", None)


def _no_org(request):
    return render(request, "donations/no_org.html")


def _role(request, org):
    return (
        UserOrgMembership.objects.filter(user=request.user, organization=org)
        .values_list("role", flat=True)
        .first()
    )


def _usage(org, plan):
    """Live counts against a plan's limits, shaped for the usage bars in the
    template. A NULL cap renders as 'unlimited' (no bar)."""
    rows = []
    for label, field, count in (
        ("Members", "max_members", Member.objects.filter(organization=org).count()),
        (
            "Staff logins",
            "max_users",
            UserOrgMembership.objects.filter(organization=org).count(),
        ),
    ):
        cap = getattr(plan, field) if plan else None
        pct = None
        if cap:
            pct = min(100, round(count / cap * 100))
        rows.append(
            {
                "label": label,
                "count": count,
                "cap": cap,
                "pct": pct,
                "unlimited": cap is None,
                "over": cap is not None and count >= cap,
            }
        )
    return rows


@login_required
@require_cap(Cap.BILLING_MANAGE)
def overview(request):
    """The org's current subscription: plan, status, renewal, usage vs limits,
    and invoice history."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    sub = getattr(request, "subscription", None)
    plan = sub.plan if sub else None

    return render(
        request,
        "billing/overview.html",
        {
            "subscription": sub,
            "plan": plan,
            "usage": _usage(org, plan),
            "invoices": list(sub.invoices.all()) if sub else [],
            "can_manage": _role(request, org) in BILLING_ROLES,
        },
    )


@login_required
@require_cap(Cap.BILLING_MANAGE)
def plans(request):
    """Public pricing table. Plans share a `tier` across their monthly/yearly
    variants; the template offers a billing-period toggle and highlights the
    org's current plan."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    sub = getattr(request, "subscription", None)
    current_code = sub.plan.code if sub else None

    available = list(
        Plan.objects.filter(is_active=True, is_public=True).order_by(
            "tier", "interval", "price_amount"
        )
    )
    has_yearly = any(p.interval == "yearly" for p in available)

    return render(
        request,
        "billing/plans.html",
        {
            "available": available,
            "current_code": current_code,
            "has_yearly": has_yearly,
            "can_manage": _role(request, org) in BILLING_ROLES,
        },
    )


@login_required
@require_cap(Cap.BILLING_MANAGE)
@require_POST
def change_plan(request):
    """Switch the org onto the chosen plan. Owners/Admins only. Without a payment
    gateway this applies immediately (trial dates derived from the plan)."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    if _role(request, org) not in BILLING_ROLES:
        messages.error(request, "You don't have permission to change the plan.")
        return redirect("billing:overview")

    plan = get_object_or_404(
        Plan, code=request.POST.get("plan"), is_active=True, is_public=True
    )
    start_subscription(org, plan, provider="manual")
    messages.success(request, f"You're now on the {plan.name} plan.")
    return redirect("billing:overview")


@login_required
@require_cap(Cap.BILLING_MANAGE)
@require_POST
def cancel(request):
    """Schedule the subscription to lapse at the end of the current period.
    Owners/Admins only."""
    org = _require_org(request)
    if org is None:
        return _no_org(request)

    sub = getattr(request, "subscription", None)
    if _role(request, org) not in BILLING_ROLES:
        messages.error(request, "You don't have permission to cancel the plan.")
        return redirect("billing:overview")
    if sub is None:
        return redirect("billing:plans")

    sub.cancel_at_period_end = True
    sub.save(update_fields=["cancel_at_period_end", "updated_at"])
    messages.success(
        request, "Your plan is set to cancel at the end of the current period."
    )
    return redirect("billing:overview")
