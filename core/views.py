from django.http import JsonResponse
from .test_models import Widget


def widget_list_view(request):
    """
    Throwaway view, used only by the P1-T7 isolation suite to prove the full
    HTTP-request pipeline (middleware -> GUC -> RLS -> response) never leaks
    cross-tenant data. Real endpoints arrive in P1-T14+ and will follow this
    same request-scoped-manager pattern (no unscoped/raw queries in view code).
    """
    names = list(Widget.objects.values_list("name", flat=True))
    return JsonResponse({"widgets": names})
