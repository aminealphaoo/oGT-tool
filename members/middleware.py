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
                # Use select_related to avoid N+1 if member is accessed
                request.current_member = request.user.member_profile
            except Member.DoesNotExist:
                pass
                
        return self.get_response(request)

class RequireLoginMiddleware:
    """Require login for all views except those starting with exempt paths."""
    
    EXEMPT_PATHS = ["/members/login/", "/admin/", "/static/", "/media/"]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        is_exempt = any(path.startswith(p) for p in self.EXEMPT_PATHS)
        
        if not is_exempt and not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect(f"/members/login/?next={path}")
            
        return self.get_response(request)
