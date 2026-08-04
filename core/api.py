"""Lightweight API endpoints — JSON responses, no auth required."""
import json

from django.http import JsonResponse
from django.utils import timezone

from core.models import SiteConfig
from ops.models import EP
from partners.models import IR


def api_health(request):
    """Health check endpoint."""
    from django.db import connections

    db_ok = True
    try:
        connections["default"].cursor()
    except Exception:
        db_ok = False

    return JsonResponse({
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "timestamp": timezone.now().isoformat(),
        "version": "1.0",
    })


def api_eps(request):
    """List EPs as JSON. Supports same filters as the web EP list."""
    eps = EP.objects.filter(is_archived=False).select_related("assigned_to", "matched_opportunity__ir")

    track = request.GET.get("track", "")
    stage = request.GET.get("stage", "")
    search = request.GET.get("q", "")
    if track:
        eps = eps.filter(track=track)
    if stage:
        eps = eps.filter(current_stage=stage)
    if search:
        from django.db.models import Q
        eps = eps.filter(
            Q(full_name__icontains=search) | Q(email__icontains=search)
        )

    limit = min(int(request.GET.get("limit", 100)), 500)
    eps = eps[:limit]

    data = []
    for ep in eps:
        data.append({
            "id": ep.pk,
            "full_name": ep.full_name,
            "phone": ep.phone,
            "email": ep.email,
            "track": ep.get_track_display(),
            "current_stage": ep.get_current_stage_display(),
            "problem_flag": ep.get_problem_flag_display(),
            "assigned_to": ep.assigned_to.name if ep.assigned_to else None,
            "matched_ir": ep.matched_opportunity.ir.entity_name if ep.matched_opportunity else None,
            "matched_country": ep.matched_opportunity.ir.country if ep.matched_opportunity else None,
            "idle_days": ep.idle_days,
            "created_at": ep.created_at.isoformat(),
            "last_activity_at": ep.last_activity_at.isoformat(),
        })

    return JsonResponse({"count": len(data), "results": data})


def api_irs(request):
    """List IRs as JSON."""
    irs = IR.objects.prefetch_related("opportunities")

    country = request.GET.get("country", "")
    if country:
        irs = irs.filter(country__icontains=country)

    limit = min(int(request.GET.get("limit", 100)), 500)
    irs = irs[:limit]

    data = []
    for ir in irs:
        data.append({
            "id": ir.pk,
            "entity_name": ir.entity_name,
            "country": ir.country,
            "status": ir.get_status_display(),
            "tier": ir.get_tier_display(),
            "open_opps": ir.open_opportunities_count,
            "realized": ir.realized_count,
            "total_matched": ir.total_matched,
            "rejection_rate": ir.rejection_rate,
            "response_time_days": ir.response_time_days,
        })

    return JsonResponse({"count": len(data), "results": data})


def api_stats(request):
    """Dashboard stats as JSON."""
    total_eps = EP.objects.filter(is_archived=False).count()
    realized = EP.objects.filter(current_stage="realized", is_archived=False).count()
    problems = EP.objects.filter(
        problem_flag__in=["fix_ep_problem", "fix_ir_problem"], is_archived=False
    ).count()

    stage_counts = {}
    for s in EP.Stage.choices:
        stage_counts[s[1]] = EP.objects.filter(current_stage=s[0], is_archived=False).count()

    return JsonResponse({
        "total_eps": total_eps,
        "realized": realized,
        "problems": problems,
        "total_irs": IR.objects.count(),
        "stage_counts": stage_counts,
    })
