from django.shortcuts import redirect

from .models import Member


class CurrentMemberMiddleware:
    """Attach current_member to request based on authenticated user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.current_member = None
        if hasattr(request, "user") and request.user.is_authenticated:
            try:
                request.current_member = request.user.member_profile
            except Member.DoesNotExist:
                pass

        return self.get_response(request)


class RequireLoginMiddleware:
    """Require login for all views except public, API, ping, login, admin, static."""

    EXEMPT_PREFIXES = (
        "/members/login/",
        "/admin/",
        "/static/",
        "/media/",
        "/public/",
        "/api/",
        "/ping/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        is_exempt = any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES)

        if not is_exempt and not request.user.is_authenticated:
            return redirect(f"/members/login/?next={path}")

        return self.get_response(request)
