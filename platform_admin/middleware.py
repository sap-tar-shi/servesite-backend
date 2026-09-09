from .models import SuperAdmin


class SuperAdminSessionMiddleware:
    """
    Populates request.superadmin from session["superadmin_id"], entirely
    separate from request.user/AuthenticationMiddleware. Runs on every
    request but is a no-op unless that session key is set - cheap and
    harmless off the platform-admin origin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.superadmin = None
        superadmin_id = request.session.get("superadmin_id")
        if superadmin_id:
            request.superadmin = SuperAdmin.objects.filter(id=superadmin_id, is_active=True).first()
        return self.get_response(request)