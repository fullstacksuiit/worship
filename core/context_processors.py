from .navigation import visible_modules
from .permissions import get_role, user_caps


def organization(request):
    """Expose the signed-in person's place of worship (and its faith preset).

    `org` is None on the signed-out screens — sign in, sign up, join — so those
    templates fall back to neutral wording. Everywhere else templates use
    `org.preset.member_term` etc. for faith-aware wording.
    """
    return {"org": getattr(request, "organization", None)}


def capabilities(request):
    """Expose the signed-in user's role + capabilities so templates can hide
    buttons the user isn't allowed to use. `caps.manage_money` etc."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    caps = user_caps(user)
    return {
        "role": get_role(user),
        "caps": {
            "manage_team": "manage_team" in caps,
            "manage_money": "manage_money" in caps,
            "manage_people": "manage_people" in caps,
            "manage_events": "manage_events" in caps,
            "manage_notices": "manage_notices" in caps,
            "manage_rentals": "manage_rentals" in caps,
            "manage_categories": "manage_categories" in caps,
        },
    }


def navigation(request):
    """Expose the module list to the shell (sidebar, drawer, phone tab bar).

    Each entry knows whether it's the page you're on, so the nav can highlight
    itself without every template having to say where it lives.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav": []}
    org = getattr(request, "organization", None)
    if org is None:
        return {"nav": []}
    return {"nav": visible_modules(org, user, getattr(request, "resolver_match", None))}
