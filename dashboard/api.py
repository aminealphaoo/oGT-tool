from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
from ops.models import EP, MatchRecord
from partners.models import Opportunity

def sd_ratio_api(request):
    """
    Returns Supply & Demand (S&D) Ratio for GTa and GTe.
    """
    supply_gta = EP.objects.filter(track="GTa").exclude(current_stage__in=["realized", "archived"]).count()
    demand_gta = Opportunity.objects.filter(track="GTa", is_open=True).count()
    
    supply_gte = EP.objects.filter(track="GTe").exclude(current_stage__in=["realized", "archived"]).count()
    demand_gte = Opportunity.objects.filter(track="GTe", is_open=True).count()

    return JsonResponse({
        "gta": {
            "supply": supply_gta,
            "demand": demand_gta,
            "ratio": round(demand_gta / supply_gta, 2) if supply_gta > 0 else 0
        },
        "gte": {
            "supply": supply_gte,
            "demand": demand_gte,
            "ratio": round(demand_gte / supply_gte, 2) if supply_gte > 0 else 0
        }
    })

def ghost_opps_api(request):
    threshold_date = timezone.now() - timedelta(days=10)
    ghost_count = Opportunity.objects.filter(
        is_open=True,
        created_at__lt=threshold_date
    ).annotate(
        match_count=Count('match_records')
    ).filter(match_count=0).count()
    
    return JsonResponse({"ghost_opps": ghost_count})

def cold_eps_api(request):
    threshold_date = timezone.now() - timedelta(days=7)
    cold_count = EP.objects.filter(
        current_stage__in=["open", "matched_with_opp", "applied", "accepted", "approved"],
        last_activity_at__lt=threshold_date
    ).count()
    
    return JsonResponse({"cold_eps": cold_count})
