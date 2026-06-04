from .models import UserOrgMembership

SESSION_KEY = "current_organization_id"


class CurrentOrganizationMiddleware:
    """Attaches `request.organization` for authenticated users based on their
    UserOrgMembership. Honours a session-selected org (the org switcher),
    otherwise falls back to the user's default membership, otherwise the first.

    `request.organization` is None for anonymous users or users with no
    membership; views are responsible for handling that case.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = self._resolve(request)
        return self.get_response(request)

    def _resolve(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        memberships = list(
            UserOrgMembership.objects.filter(user=user).select_related(
                "organization"
            )
        )
        if not memberships:
            return None

        selected_id = request.session.get(SESSION_KEY)
        if selected_id is not None:
            for m in memberships:
                if m.organization_id == selected_id:
                    return m.organization

        for m in memberships:
            if m.is_default:
                return m.organization
        return memberships[0].organization
