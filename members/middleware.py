from django.shortcuts import redirect

from .models import Member


class IdentityMiddleware:
    """Attach current_member to request based on session identity."""

    EXEMPT_PATHS = ["/members/picker/", "/members/clear/", "/admin/", "/static/", "/media/"]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip identity check for exempt paths
        path = request.path
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                return self.get_response(request)

        member_id = request.session.get("identity_member_id")
        if member_id:
            try:
                member = Member.objects.select_related("team").get(pk=member_id, is_active=True)
                request.current_member = member
            except Member.DoesNotExist:
                request.current_member = None
        else:
            request.current_member = None

        # Redirect to identity picker if no identity set
        if request.current_member is None and not path.startswith("/members/picker/"):
            return redirect(f"/members/picker/?next={path}")

        return self.get_response(request)
