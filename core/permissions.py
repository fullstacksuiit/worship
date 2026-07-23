"""Roles and capabilities — the single source of truth for who-can-do-what.

Four roles, mapped to a set of capabilities. Views gate write actions with
`cap_required(...)`; templates hide buttons with the `caps` context. A role only
ever applies inside the person's own place — which place that is comes from
`request.organization`, never from the role.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

ADMIN = "admin"
TREASURER = "treasurer"
EDITOR = "editor"
VIEWER = "viewer"

ROLE_CHOICES = [
    (ADMIN, "Admin"),
    (TREASURER, "Treasurer"),
    (EDITOR, "Editor"),
    (VIEWER, "Viewer"),
]

ROLE_HELP = {
    ADMIN: "Full access, including managing the team.",
    TREASURER: "Manage money; view everything else.",
    EDITOR: "Manage members & events; view money.",
    VIEWER: "Read-only access.",
}

# What each role is allowed to change. Everyone signed in can *view*.
# `manage_categories` is admin-only on purpose: a label is shared by every
# module, so renaming or merging one rewrites what other people's records say.
# Adding a label isn't gated by it — typing a new word into any category box
# still just works, whatever your role.
CAPABILITIES = {
    ADMIN: {"manage_team", "manage_money", "manage_people", "manage_events",
            "manage_notices", "manage_rentals", "manage_categories"},
    TREASURER: {"manage_money"},
    EDITOR: {"manage_people", "manage_events", "manage_notices", "manage_rentals"},
    VIEWER: set(),
}


def get_role(user):
    """Resolve a user's role within their own place.

    Django superusers are admin wherever they belong; anyone else takes the role
    on their membership. A user with no active membership defaults to viewer —
    they can't reach a place's pages anyway (see `CurrentOrganizationMiddleware`).
    """
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMIN
    tm = getattr(user, "team_membership", None)
    if tm and tm.is_active:
        return tm.role
    return VIEWER


def user_caps(user):
    return CAPABILITIES.get(get_role(user), set())


def has_cap(user, cap):
    return cap in user_caps(user)


def cap_required(cap):
    """Decorator: block the view (friendly redirect) unless the user has `cap`."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not has_cap(request.user, cap):
                messages.error(request, "You don't have permission to do that.")
                return redirect("core:dashboard")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
