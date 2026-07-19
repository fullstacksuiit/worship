from .models import UserOrgMembership

SESSION_KEY = "current_organization_id"


class CurrentOrganizationMiddleware:
    """Attaches `request.organization`, `request.org_membership`, and
    `request.org_role` for authenticated users based on their (active)
    UserOrgMembership. Honours a session-selected org (the org switcher),
    otherwise falls back to the user's default membership, otherwise the first.

    Deactivated memberships are ignored, so a member who has been switched off
    loses access to that organization. All three attributes are None for
    anonymous users or users with no active membership; views are responsible
    for handling that case.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        membership = self._resolve(request)
        request.org_membership = membership
        request.organization = membership.organization if membership else None
        request.org_role = membership.role if membership else None
        return self.get_response(request)

    def _resolve(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        memberships = list(
            UserOrgMembership.objects.filter(
                user=user, is_active=True
            ).select_related("organization")
        )
        if not memberships:
            return None

        selected_id = request.session.get(SESSION_KEY)
        if selected_id is not None:
            for m in memberships:
                if m.organization_id == selected_id:
                    return m

        for m in memberships:
            if m.is_default:
                return m
        return memberships[0]
