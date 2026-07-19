"""Role-based access control within an organization.

Every login belongs to an org through a UserOrgMembership carrying an OrgRole.
This module is the single source of truth for what each role may do: it maps
roles to a small set of coarse *capabilities* (one per protected area), and
provides the pieces that enforce them —

  * ``require_cap(cap)``  – view decorator (used across every app)
  * ``role_can`` / ``user_can`` – predicate helpers
  * ``ROLE_META`` – labels + descriptions for the team-management UI

Keeping the matrix here (rather than scattered ``role in (...)`` checks) means
adding a role or moving a permission is a one-line change in one file.
"""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect, render

from .models import OrgRole


class Cap:
    """The protected areas of the app. Each constant is also the key templates
    read off ``caps`` (e.g. ``{% if caps.finance_access %}``)."""

    TEAM_MANAGE = "team_manage"
    SETTINGS_MANAGE = "settings_manage"
    BILLING_MANAGE = "billing_manage"
    FINANCE_ACCESS = "finance_access"
    DONATIONS_RECORD = "donations_record"
    REPORTS_VIEW = "reports_view"
    MEMBERS_VIEW = "members_view"
    MEMBERS_MANAGE = "members_manage"
    RENTALS_ACCESS = "rentals_access"
    EVENTS_ACCESS = "events_access"


ALL_CAPS = [
    Cap.TEAM_MANAGE,
    Cap.SETTINGS_MANAGE,
    Cap.BILLING_MANAGE,
    Cap.FINANCE_ACCESS,
    Cap.DONATIONS_RECORD,
    Cap.REPORTS_VIEW,
    Cap.MEMBERS_VIEW,
    Cap.MEMBERS_MANAGE,
    Cap.RENTALS_ACCESS,
    Cap.EVENTS_ACCESS,
]

# What each role may do. Owner and Admin run the whole organization; the rest
# are scoped to the work their title implies. General Member (staff) is the
# everyday volunteer: record gifts, browse the directory, see events.
ROLE_CAPABILITIES = {
    OrgRole.OWNER: set(ALL_CAPS),
    OrgRole.ADMIN: set(ALL_CAPS),
    OrgRole.TREASURER: {
        Cap.FINANCE_ACCESS,
        Cap.DONATIONS_RECORD,
        Cap.REPORTS_VIEW,
        Cap.MEMBERS_VIEW,
        Cap.MEMBERS_MANAGE,
        Cap.RENTALS_ACCESS,
        Cap.EVENTS_ACCESS,
    },
    OrgRole.ACCOUNTANT: {
        Cap.FINANCE_ACCESS,
        Cap.DONATIONS_RECORD,
        Cap.REPORTS_VIEW,
        Cap.MEMBERS_VIEW,
        Cap.EVENTS_ACCESS,
    },
    OrgRole.STAFF: {
        Cap.DONATIONS_RECORD,
        Cap.MEMBERS_VIEW,
        Cap.EVENTS_ACCESS,
    },
}

# Plain-language summary of each role, shown when adding/editing a team member.
ROLE_META = {
    OrgRole.OWNER: {
        "label": OrgRole.OWNER.label,
        "description": "Full control of the organization, including the team, "
        "billing, and settings.",
    },
    OrgRole.ADMIN: {
        "label": OrgRole.ADMIN.label,
        "description": "Full access like the owner — manage the team, finances, "
        "and settings.",
    },
    OrgRole.TREASURER: {
        "label": OrgRole.TREASURER.label,
        "description": "Runs the money: finances, rentals, reports, donations, "
        "and the member directory.",
    },
    OrgRole.ACCOUNTANT: {
        "label": OrgRole.ACCOUNTANT.label,
        "description": "Keeps the books: finances, reports, and recording "
        "donations. Can't manage members or rentals.",
    },
    OrgRole.STAFF: {
        "label": OrgRole.STAFF.label,
        "description": "Everyday helper: record donations, browse members, and "
        "view events.",
    },
}

# Roles an Owner/Admin can hand out. Ownership isn't assignable here — an org has
# exactly one owner, established at signup.
ASSIGNABLE_ROLES = [
    OrgRole.ADMIN,
    OrgRole.TREASURER,
    OrgRole.ACCOUNTANT,
    OrgRole.STAFF,
]
ASSIGNABLE_ROLE_CHOICES = [(r.value, r.label) for r in ASSIGNABLE_ROLES]


def role_caps(role):
    """The set of capabilities a role grants (empty for None/unknown)."""
    return ROLE_CAPABILITIES.get(role, set())


def role_can(role, cap):
    return cap in role_caps(role)


def user_can(request, cap):
    """Whether the signed-in user's role in the current org grants ``cap``.
    Relies on ``request.org_role`` set by CurrentOrganizationMiddleware."""
    return role_can(getattr(request, "org_role", None), cap)


def require_cap(cap):
    """View decorator: allow only users whose org role grants ``cap``.

    No organization → the standard 'no org' page. Insufficient role → a friendly
    message and a bounce back to the dashboard (rather than a bare 403), matching
    the app's ease-of-use tone. Assumes ``@login_required`` sits above it."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if getattr(request, "organization", None) is None:
                return render(request, "donations/no_org.html")
            if not user_can(request, cap):
                messages.error(
                    request,
                    "You don't have access to that area. Ask an owner or admin "
                    "if you need it.",
                )
                return redirect("donations:dashboard")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
