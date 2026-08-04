from core.models import SiteConfig
from django.utils import timezone

from .models import Member


def identity(request):
    """Context processor — inject current_member, LC config, and notification badges."""
    member = getattr(request, "current_member", None)
    try:
        config = SiteConfig.get()
        lc_name = config.lc_name
    except Exception:
        lc_name = "AIESEC LC Carthage"

    # ── Notification badges ──────────────────────────────────────────
    nav_stale_count = 0
    nav_problem_count = 0
    nav_unassigned_count = 0

    if member:
        from ops.models import EP

        eps = member.get_visible_eps().filter(is_archived=False)

        # Stale count (lightweight — just count, no per-EP loop for scale)
        now = timezone.now()
        for ep in eps.only("pk", "current_stage", "last_activity_at"):
            threshold = config.get_threshold(ep.current_stage)
            if (now - ep.last_activity_at).days > threshold:
                nav_stale_count += 1

        nav_problem_count = eps.filter(
            problem_flag__in=["fix_ep_problem", "fix_ir_problem"]
        ).count()

        nav_unassigned_count = eps.filter(assigned_to__isnull=True).count()

    return {
        "current_member": member,
        "is_vp": member.is_vp() if member else False,
        "is_tl": member.is_tl() if member else False,
        "is_ops": member.is_ops() if member else False,
        "is_ir": member.is_ir() if member else False,
        "lc_name": lc_name,
        "nav_stale_count": nav_stale_count,
        "nav_problem_count": nav_problem_count,
        "nav_unassigned_count": nav_unassigned_count,
    }
