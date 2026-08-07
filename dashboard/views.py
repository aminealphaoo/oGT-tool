from datetime import timedelta
from collections import defaultdict

from django.db.models import Avg, Count, F, Q
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone

from core.models import SiteConfig, SyncLog
from core.utils import parse_date_range, apply_date_filter, date_context
from members.models import Member, Team
from ops.models import EP, Interaction, StageHistory
from partners.models import IR


STAGE_ORDER = [
    "open", "matched_with_opp", "applied", "accepted",
    "approved", "all_papers_done", "not_all_papers_done",
    "do_papers", "realized",
]


def dashboard(request):
    """
    Role-scoped dashboard with admin-controlled stats.
    All counters come from DashboardStats (set by admin in /admin).
    Date filters are removed — the admin controls what's displayed.
    """
    member = request.current_member
    config = SiteConfig.get()
    date_from, date_to, preset = parse_date_range(request)

    eps = member.get_visible_eps()
    irs = member.get_visible_irs()

    # ── Admin-controlled stats (fallback to empty if table doesn't exist) ──
    from core.models import DashboardStats
    try:
        stats = DashboardStats.for_config(config)
    except Exception:
        # Table doesn't exist yet — use empty placeholder
        class _FallbackStats:
            funnel_counts = [0, 0, 0, 0, 0, 0, 0]
            total_eps = 0
            stage_realized = 0
            problem_cases = 0
            stale_cases = 0
            ir_partners = 0
            open_opps = 0
            interactions_period = 0
            realized_last_30 = 0
            pipeline_value = 0
            @property
            def expa_stats(self):
                return {"applied": 0, "accepted": 0, "approved": 0, "realized": 0, "finished": 0}
        stats = _FallbackStats()

    stage_labels = [EP.Stage(s).label for s in STAGE_ORDER]

    # ── Live data (not admin-controlled, always accurate) ──
    last_sync = SyncLog.objects.filter(status="success").order_by("-started_at").first()
    recent_interactions = (
        Interaction.objects.filter(ep__in=eps)
        .select_related("ep", "author")
        .order_by("-date")[:10]
    )
    recent_eps = eps.order_by("-last_activity_at")[:5]

    # ── Pipeline forecast (calculated live) ──
    thirty_days_ago = timezone.now() - timedelta(days=30)
    realized_last_30_live = eps.filter(
        current_stage="realized",
        last_activity_at__gte=thirty_days_ago,
    ).count()

    daily_rate = realized_last_30_live / 30 if realized_last_30_live > 0 else 0
    term_end = timezone.now() + timedelta(days=180)
    remaining_days = max(0, (term_end - timezone.now()).days)
    forecast_realized = round(daily_rate * remaining_days)

    # Pipeline value: EPs in non-terminal stages
    pipeline_live = eps.filter(
        current_stage__in=["matched_with_opp", "applied", "accepted", "approved",
                           "all_papers_done", "not_all_papers_done", "do_papers"]
    ).count()

    context = {
        # ── Admin check ──
        "is_admin": member.role in ('VP', 'TL', 'admin', 'super_admin'),
        "hide_edit": "" if member.role in ('VP', 'TL', 'admin', 'super_admin') else "d-none",

        # ── Admin-controlled counters (flat for template) ──
        "stage_labels": stage_labels,
        "funnel_counts": stats.funnel_counts,
        "total_eps": stats.total_eps,
        "total_realized": stats.stage_realized,
        "stage_realized": stats.stage_realized,
        "stage_open": stats.stage_open,
        "stage_matched": stats.stage_matched,
        "stage_applied": stats.stage_applied,
        "stage_accepted": stats.stage_accepted,
        "stage_approved": stats.stage_approved,
        "stage_papers": stats.stage_papers,
        "total_problems": stats.problem_cases,
        "problem_cases": stats.problem_cases,
        "total_stale": stats.stale_cases,
        "stale_cases": stats.stale_cases,
        "total_irs": stats.ir_partners,
        "ir_partners": stats.ir_partners,
        "open_opps": stats.open_opps,
        "expa_stats": stats.expa_stats,
        "realized_period": stats.stage_realized,
        "interactions_period": stats.interactions_period,

        # ── Live data ──
        "recent_interactions": recent_interactions,
        "recent_eps": recent_eps,
        "last_sync": last_sync,
        "forecast": {
            "realized_last_30": stats.realized_last_30,
            "daily_rate": round(daily_rate, 2),
            "remaining_days": remaining_days,
            "forecast_realized": forecast_realized,
            "projected_total": stats.stage_realized + forecast_realized,
            "pipeline_value": stats.pipeline_value,
        },

        # ── Config ──
        "lc_name": config.lc_name,
        "current_term": config.current_term,
        "expa_token_configured": bool(config.expa_access_token),
        **date_context(date_from, date_to, preset),
    }

    return render(request, "dashboard/index.html", context)


def leaderboard(request):
    """Member engagement leaderboard — fully featured with filters, badges, charts, streaks."""
    member = request.current_member
    config = SiteConfig.get()
    eps = member.get_visible_eps()
    date_from, date_to, preset = parse_date_range(request)

    team_filter = request.GET.get("team", "")
    track_filter = request.GET.get("track", "")

    visible_members = Member.objects.filter(is_active=True).select_related("team")
    if not member.is_vp():
        if member.team:
            visible_members = visible_members.filter(team=member.team)
        else:
            visible_members = visible_members.filter(pk=member.pk)
    if team_filter:
        visible_members = visible_members.filter(team_id=team_filter)

    teams = Team.objects.all()

    # Interactions: always filter by date range
    interactions_qs = Interaction.objects.filter(ep__in=eps)
    if date_from:
        interactions_qs = interactions_qs.filter(date__date__gte=date_from)
        if date_to:
            interactions_qs = interactions_qs.filter(date__date__lte=date_to)

    if date_from:
        eps_filtered = eps.filter(last_activity_at__date__gte=date_from)
        if date_to:
            eps_filtered = eps_filtered.filter(last_activity_at__date__lte=date_to)
    else:
        eps_filtered = eps

    now = timezone.now()
    cache_key = f"leaderboard_{member.pk}_{date_from}_{date_to}_{team_filter}_{track_filter}"
    from django.core.cache import cache
    stats = cache.get(cache_key)

    if not stats:
        stats = []
        visible_members = visible_members.prefetch_related('assigned_eps', 'author')

        annotated_members = visible_members.annotate(
            total_eps=Count('assigned_eps', filter=Q(assigned_eps__in=eps)),
            realized_filtered=Count('assigned_eps', filter=Q(assigned_eps__in=eps_filtered, assigned_eps__current_stage="realized")),
            realized_alltime=Count('assigned_eps', filter=Q(assigned_eps__in=eps, assigned_eps__current_stage="realized")),
            problems_count=Count('assigned_eps', filter=Q(assigned_eps__in=eps, assigned_eps__problem_flag__in=["fix_ep_problem", "fix_ir_problem"])),
            open_eps_count=Count('assigned_eps', filter=~Q(assigned_eps__current_stage="realized") & Q(assigned_eps__in=eps)),
            interactions_total=Count('author', filter=Q(author__in=interactions_qs)),
            gt_count=Count('assigned_eps', filter=Q(assigned_eps__in=eps, assigned_eps__track="GT")),
            gte_count=Count('assigned_eps', filter=Q(assigned_eps__in=eps, assigned_eps__track="GTe")),
        )

        for m in annotated_members:
            m_eps = eps.filter(assigned_to=m)
            if track_filter:
                m_eps = m_eps.filter(track=track_filter)

            stale = sum(1 for ep in m_eps.only("pk", "current_stage", "last_activity_at")
                        if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage))

            realized_eps = m_eps.filter(current_stage="realized").prefetch_related("stage_history")
            avg_days = None
            if realized_eps.exists():
                total_days, cnt = 0, 0
                for ep in realized_eps:
                    history = list(ep.stage_history.all())
                    if not history:
                        continue
                    first = min(history, key=lambda x: x.changed_at)
                    realized_entries = [h for h in history if h.stage == "realized"]
                    if first and realized_entries:
                        realized_entry = max(realized_entries, key=lambda x: x.changed_at)
                        total_days += max((realized_entry.changed_at - first.changed_at).days, 1)
                        cnt += 1
                if cnt > 0:
                    avg_days = round(total_days / cnt, 1)

            new_eps = m_eps.filter(created_at__date__gte=date_from).count() if date_from else 0
            streak = _compute_streak(m, eps)
            score = (m.realized_filtered * 50) + m.interactions_total

            stats.append({
                "member": m, "total": m.total_eps, "realized": m.realized_filtered,
                "realized_alltime": m.realized_alltime, "problems": m.problems_count,
                "open_eps": m.open_eps_count, "stale": stale, "avg_days": avg_days,
                "interactions_count": m.interactions_total, "new_eps": new_eps,
                "streak": streak, "gt_count": m.gt_count, "gte_count": m.gte_count,
                "team_name": m.team.name if m.team else "—",
                "score": score,
            })

        cache.set(cache_key, stats, 300)

    sort_by = request.GET.get("sort", "realized")
    sort_order = request.GET.get("order", "desc")
    reverse = sort_order == "desc"
    key_map = {"realized": "realized", "total": "total", "interactions": "interactions_count",
               "avg_days": "avg_days", "open": "open_eps", "streak": "streak", "new": "new_eps"}
    key = key_map.get(sort_by, "realized")
    stats.sort(key=lambda x: (x[key] is None, x[key] if x[key] is not None else 0), reverse=reverse)

    top_realized = [s for s in stats if s["realized"] > 0][:3]
    top_engagement = sorted([s for s in stats if s["interactions_count"] > 0],
                            key=lambda x: x["interactions_count"], reverse=True)[:3]
    top_streak = sorted([s for s in stats if s["streak"] > 0],
                        key=lambda x: x["streak"], reverse=True)[:3]

    for s in stats:
        badges = []
        if s["realized_alltime"] >= 10:
            badges.append({"icon": "trophy", "label": "10+ Realized", "emoji": "🏆", "color": "gold"})
        elif s["realized_alltime"] >= 5:
            badges.append({"icon": "award", "label": "5+ Realized", "emoji": "⭐", "color": "silver"})
        if s["interactions_count"] >= 50:
            badges.append({"icon": "chat-dots", "label": "50+ Interactions", "emoji": "💬", "color": "blue"})
        if s["avg_days"] and s["avg_days"] < 30 and s["realized"] >= 3:
            badges.append({"icon": "lightning", "label": "Speed <30d", "emoji": "⚡", "color": "green"})
        if s["streak"] >= 4:
            badges.append({"icon": "fire", "label": f"{s['streak']}wk Streak", "emoji": "🔥", "color": "orange"})
        if s["stale"] == 0 and s["total"] > 0:
            badges.append({"icon": "shield-check", "label": "Zero Stale", "emoji": "🛡️", "color": "teal"})
        if s["new_eps"] >= 3:
            badges.append({"icon": "star", "label": "Rising Star", "emoji": "⭐", "color": "pink"})
        s["badges"] = badges

    chart_n = min(10, len(stats))
    chart_members = [s["member"].name for s in stats[:chart_n]]
    chart_realized = [s["realized"] for s in stats[:chart_n]]
    chart_interactions = [s["interactions_count"] for s in stats[:chart_n]]
    chart_total = [s["total"] for s in stats[:chart_n]]

    total_realized_all = sum(s["realized"] for s in stats)
    total_interactions_all = sum(s["interactions_count"] for s in stats)
    total_new_all = sum(s["new_eps"] for s in stats)
    avg_realized = round(total_realized_all / len(stats), 1) if stats else 0
    members_with_realized = sum(1 for s in stats if s["realized"] > 0)

    context = {
        "stats": stats, "top_realized": top_realized, "top_engagement": top_engagement,
        "top_streak": top_streak, "chart_members": chart_members,
        "chart_realized": chart_realized, "chart_interactions": chart_interactions,
        "chart_total": chart_total, "total_realized": total_realized_all,
        "total_interactions": total_interactions_all, "total_new": total_new_all,
        "avg_realized": avg_realized, "members_with_realized": members_with_realized,
        "teams": teams, "team_filter": team_filter, "track_filter": track_filter,
        "sort_by": sort_by, "sort_order": sort_order,
        "tracks": EP.Track.choices, "member_count": len(stats),
        **date_context(date_from, date_to, preset),
    }
    return render(request, "dashboard/leaderboard.html", context)


def _compute_streak(member, eps):
    """Compute consecutive weeks with at least 1 interaction."""
    now = timezone.now().date()
    streak = 0
    this_week_start = now - timedelta(days=now.weekday())
    this_week_count = Interaction.objects.filter(
        author=member, ep__in=eps, date__date__gte=this_week_start, date__date__lte=now,
    ).count()
    if this_week_count > 0:
        streak += 1
    for i in range(12):
        week_start = now - timedelta(days=now.weekday() + 7 * (i + 1))
        week_end = week_start + timedelta(days=6)
        count = Interaction.objects.filter(
            author=member, ep__in=eps, date__date__gte=week_start, date__date__lte=week_end,
        ).count()
        if count > 0:
            streak += 1
        else:
            break
    return streak


def leaderboard_export_csv(request):
    """Export current leaderboard as CSV."""
    import csv
    from django.http import HttpResponse

    member = request.current_member
    eps = member.get_visible_eps()
    visible_members = Member.objects.filter(is_active=True).select_related("team")
    if not member.is_vp():
        if member.team:
            visible_members = visible_members.filter(team=member.team)
        else:
            visible_members = visible_members.filter(pk=member.pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="leaderboard.csv"'
    writer = csv.writer(response)
    writer.writerow(["Rank", "Name", "Role", "Team", "Realized", "Total EPs", "Open EPs",
                     "Interactions", "Avg Days", "Streak", "Stale", "Badges"])
    for i, m in enumerate(visible_members, 1):
        m_eps = eps.filter(assigned_to=m)
        realized = m_eps.filter(current_stage="realized").count()
        interactions = Interaction.objects.filter(author=m, ep__in=eps).count()
        writer.writerow([i, m.name, m.get_role_display(), m.team.name if m.team else "",
                         realized, m_eps.count(), m_eps.exclude(current_stage="realized").count(),
                         interactions, "", "", "", ""])
    return response


def workload(request):
    """Member workload distribution."""
    member = request.current_member
    config = SiteConfig.get()
    eps = member.get_visible_eps()

    visible_members = Member.objects.filter(is_active=True).select_related("team")
    if not member.is_vp():
        if member.team:
            visible_members = visible_members.filter(team=member.team)
        else:
            visible_members = visible_members.filter(pk=member.pk)

    stage_filter = request.GET.get("stage", "")

    now = timezone.now()
    members_data = []
    all_stages = list(STAGE_ORDER)

    for m in visible_members:
        m_eps = eps.filter(assigned_to=m)
        stage_counts = {}
        for s in all_stages:
            stage_counts[s] = m_eps.filter(current_stage=s).count()
        total = sum(stage_counts.values())
        realized = stage_counts.get("realized", 0)
        stale = sum(1 for ep in m_eps.only("pk", "current_stage", "last_activity_at")
                    if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage))
        members_data.append({
            "member": m, "total": total, "realized": realized,
            "stage_counts": stage_counts, "stale": stale,
            "team_name": m.team.name if m.team else "—",
        })

    members_data.sort(key=lambda x: x["total"], reverse=True)

    chart_members = [d["member"].name for d in members_data[:10]]
    chart_totals = [d["total"] for d in members_data[:10]]

    context = {
        "members_data": members_data,
        "chart_members": chart_members,
        "chart_totals": chart_totals,
        "all_stages": all_stages,
        "stage_filter": stage_filter,
        "stages": EP.Stage.choices,
    }
    return render(request, "dashboard/workload.html", context)


def compare(request):
    """Term-over-term comparison view."""
    member = request.current_member
    config = SiteConfig.get()
    eps = member.get_visible_eps()

    terms = []
    for year in [2025, 2026]:
        for half in [("H1", 1, 6), ("H2", 7, 12)]:
            terms.append({
                "label": f"{year} {half[0]}",
                "start": timezone.datetime(year, half[1], 1),
                "end": timezone.datetime(year, half[2], 28 if half[2] == 6 else 31, 23, 59, 59),
            })

    term_a = request.GET.get("term_a", "")
    term_b = request.GET.get("term_b", "")

    def term_stats(term_label):
        if not term_label:
            return None
        term = next((t for t in terms if t["label"] == term_label), None)
        if not term:
            return None
        t_eps = eps.filter(last_activity_at__gte=term["start"], last_activity_at__lte=term["end"])
        funnel = []
        for s in STAGE_ORDER:
            funnel.append(t_eps.filter(current_stage=s).count())
        total = t_eps.count()
        realized = t_eps.filter(current_stage="realized").count()
        return {
            "label": term_label,
            "total": total,
            "realized": realized,
            "funnel": funnel,
            "conversion": round(realized / total * 100, 1) if total else 0,
        }

    stats_a = term_stats(term_a)
    stats_b = term_stats(term_b)

    stage_labels = [EP.Stage(s).label for s in STAGE_ORDER]

    context = {
        "terms": terms,
        "term_a": term_a,
        "term_b": term_b,
        "stats_a": stats_a,
        "stats_b": stats_b,
        "stage_labels": stage_labels,
    }
    return render(request, "dashboard/compare.html", context)


def trigger_expa_sync(request):
    """GET: show automation dashboard. POST: trigger background EXPA sync."""
    from django.conf import settings
    from django.shortcuts import redirect
    from core.models import SiteConfig, SyncLog

    config = SiteConfig.get()

    if request.method == "POST":
        from django.contrib import messages
        try:
            from automation.tasks import sync_expa_eps
            sync_expa_eps.delay()
            messages.success(request, "EXPA sync task dispatched to background worker.")
        except Exception:
            import subprocess, sys
            proc = subprocess.Popen(
                [sys.executable, "sync_expa_standalone.py"],
                cwd=str(settings.BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            messages.info(
                request,
                "Celery unavailable — EXPA sync started as local subprocess (PID {}).".format(proc.pid),
            )
        return redirect("trigger_expa_sync")

    sync_logs = SyncLog.objects.all()[:15]
    from automation.models import EmailTemplate
    email_templates = EmailTemplate.objects.all()

    context = {
        "expa_token_configured": bool(config.expa_access_token),
        "expa_token": config.expa_access_token or "5zPLES-3w6pq82iPrXgo...",
        "smtp_host": getattr(settings, "EMAIL_HOST", ""),
        "sender_email": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        "sync_logs": sync_logs,
        "email_templates": email_templates,
        "lc_name": config.lc_name,
        "current_member": request.current_member,
    }
    return render(request, "dashboard/automation.html", context)


# ── Admin: inline stats update ──
@require_POST
def update_stats(request):
    """Save DashboardStats from the dashboard inline edit form (admin only)."""
    if not request.current_member or request.current_member.role not in ('VP', 'TL', 'admin', 'super_admin'):
        return JsonResponse({"ok": False, "error": "Permission denied"}, status=403)

    from core.models import DashboardStats
    config = SiteConfig.get()
    stats = DashboardStats.for_config(config)

    # Update all fields from POST
    int_fields = [
        'total_eps',
        'expa_applied', 'expa_accepted', 'expa_approved', 'expa_realized', 'expa_finished',
        'stage_open', 'stage_matched', 'stage_applied', 'stage_accepted', 'stage_approved', 'stage_papers', 'stage_realized',
        'problem_cases', 'stale_cases', 'pipeline_value', 'realized_last_30',
        'ir_partners', 'open_opps', 'interactions_period',
    ]
    for field in int_fields:
        val = request.POST.get(field, '')
        if val.isdigit() or (val.startswith('-') and val[1:].isdigit()):
            setattr(stats, field, int(val))

    stats.save()
    return JsonResponse({"ok": True, "updated_at": stats.updated_at.isoformat()})
