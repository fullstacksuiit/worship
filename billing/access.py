"""View-level entitlement checks. The SubscriptionMiddleware attaches
`request.subscription`; these helpers turn it into yes/no decisions about
modules and limits. Kept explicit (opt-in per view/action) rather than a global
redirect."""

from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def has_feature(request, feature):
    """True if the org's current subscription grants `feature` (a flag in
    Plan.features, e.g. "finance" / "events")."""
    sub = getattr(request, "subscription", None)
    return bool(sub and sub.is_current and sub.plan.allows(feature))


def feature_required(feature):
    """View decorator: 403 unless the org's plan currently includes `feature`."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_feature(request, feature):
                raise PermissionDenied(
                    f"Your plan does not include the '{feature}' module."
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def feature_gate(feature, label=None):
    """User-facing module gate for nav-reachable pages: instead of a bare 403,
    redirect to the pricing page with an explanatory message inviting an upgrade.
    Use `feature_required` for strict/non-navigable endpoints."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_feature(request, feature):
                messages.info(
                    request,
                    f"{label or feature.title()} is available on a higher plan — "
                    "upgrade to unlock it.",
                )
                return redirect("billing:plans")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def within_limit(request, limit_field, current_count):
    """True if adding one more record stays within a numeric plan limit.

    `limit_field` is a Plan attribute such as "max_members" or "max_users".
    A NULL limit (unlimited) always passes; no current subscription fails closed.
    """
    sub = getattr(request, "subscription", None)
    if not (sub and sub.is_current):
        return False
    cap = getattr(sub.plan, limit_field, None)
    if cap is None:  # unlimited
        return True
    return current_count < cap
