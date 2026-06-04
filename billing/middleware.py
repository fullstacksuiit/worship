from .models import Subscription


class SubscriptionMiddleware:
    """Attaches `request.subscription` for the active organization, mirroring
    core.middleware.CurrentOrganizationMiddleware (which sets `request.organization`
    and must run before this). `request.subscription` is None when there is no
    active org or the org has no subscription; gating is left to view-level
    helpers in billing.access, so this never blocks a request on its own.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.subscription = self._resolve(request)
        return self.get_response(request)

    def _resolve(self, request):
        org = getattr(request, "organization", None)
        if org is None:
            return None
        return (
            Subscription.objects.filter(organization=org)
            .select_related("plan")
            .first()
        )
