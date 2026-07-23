from django.shortcuts import redirect
from django.urls import reverse


class CurrentOrganizationMiddleware:
    """Resolve which place of worship the signed-in person belongs to.

    Every record in the app hangs off an Organization, and a login reaches its
    Organization through its TeamMember row — so this runs once per request and
    every view can then trust `request.organization` instead of guessing. A view
    that filters on it can never leak another place's data.

    Someone signed in with no place yet (they just registered, or an admin
    removed them) is sent somewhere that explains itself rather than to an empty
    dashboard.
    """

    #: Paths that must work before you belong to a place — signing up, joining,
    #: signing in or out, the Django admin, and static files.
    PUBLIC_PREFIXES = ("/static/", "/admin/", "/accounts/", "/signup/", "/join/",
                       "/no-access/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            membership = getattr(user, "team_membership", None)
            if membership is not None and membership.is_active:
                request.organization = membership.organization
            elif not request.path.startswith(self.PUBLIC_PREFIXES):
                # Signed in, but not part of any place: explain, don't 404.
                return redirect("core:paused" if membership else "core:signup")

        return self.get_response(request)
