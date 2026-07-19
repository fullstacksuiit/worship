"""Expose the current organization's subscription and module entitlements to
every template, so the nav can hide gated areas (e.g. Finance) and pages can
surface plan state without each view threading it through context."""


def billing(request):
    sub = getattr(request, "subscription", None)
    # Feature flags only count when the subscription currently entitles the org;
    # an empty map means "nothing unlocked" and templates fail closed.
    features = dict(sub.plan.features) if (sub and sub.is_current) else {}
    return {"subscription": sub, "plan_features": features}
