from datetime import timedelta
from collections import defaultdict

from django.db.models import Avg, Count, F, Q
from django.shortcuts import render
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
    Role-scoped dashboard with funnel stats, problem counts, stale counts.

    Date filter behaviour:
    - When a date range is selected, the funnel shows the number of EPs that
      *entered* each stage during that period (via StageHistory.changed_at),
      plus EPs that were already in that stage at period start and never moved.
    - Without a date range, it shows the current snapshot (EP.current_stage).
    """
    member = request.current_member
    config = SiteConfig.get()
    date_from, date_to, preset = parse_date_range(request)

    eps = member.get_visible_eps()
    irs = member.get_visible_irs()

    stage_labels = [EP.Stage(s).label for s in STAGE_ORDER]

    if date_from:
        # ── Date-filtered mode: snapshot of EPs that were created or active in the period ──
        # Filter: EPs created during the period OR EPs that had activity during the period
        eps_filtered = eps.filter(
            Q(created_at__date__gte=date_from) |
            Q(last_activity_at__date__gte=date_from)
        )
        if date_to:
            eps_filtered = eps_filtered.filter(
                Q(created_at__date__lte=date_to) |
                Q(last_activity_at__date__lte=date_to)
            )

        funnel_counts = [eps_filtered.filter(current_stage=s).count() for s in STAGE_ORDER]
        gt_funnel = [eps_filtered.filter(current_stage=s, track="GT").count() for s in STAGE_ORDER]
        gte_funnel = [eps_filtered.filter(current_stage=s, track="GTe").count() for s in STAGE_ORDER]
        total_eps = eps_filtered.count()
        total_realized = eps_filtered.filter(current_stage="realized").count()
        total_problems = eps_filtered.exclude(problem_flag="none").count()

        # EXPA status breakdowns (snapshot of filtered EPs)
        try:
            expa_stats = {
                "applied": eps_filtered.filter(expa_status__in=["applied", "in_progress"]).count(),
                "accepted": eps_filtered.filter(expa_status__in=["accepted_by_host", "accepted"]).count(),
                "approved": eps_filtered.filter(expa_status__in=["approved_by_home", "approved_by_host", "approved"]).count(),
                "realized": eps_filtered.filter(expa_status="realized").count(),
                "finished": eps_filtered.filter(expa_status__in=["finished", "completed"]).count(),
            }
        except Exception:
            expa_stats = {"applied": 0, "accepted": 0, "approved": 0, "realized": 0, "finished": 0}

    else:
        # ── All-time mode: current snapshot ──
        funnel_counts = [eps.filter(current_stage=s).count() for s in STAGE_ORDER]
        gt_funnel = [eps.filter(current_stage=s, track="GT").count() for s in STAGE_ORDER]
        gte_funnel = [eps.filter(current_stage=s, track="GTe").count() for s in STAGE_ORDER]
        total_eps = eps.count()
        total_realized = eps.filter(current_stage="realized").count()
        total_problems = eps.exclude(problem_flag="none").count()

        # EXPA status breakdowns (current snapshot)
        try:
            expa_stats = {
                "applied": eps.filter(expa_status__in=["applied", "in_progress"]).count(),
                "accepted": eps.filter(expa_status__in=["accepted_by_host", "accepted"]).count(),
                "approved": eps.filter(expa_status__in=["approved_by_home", "approved_by_host", "approved"]).count(),
                "realized": eps.filter(expa_status="realized").count(),
                "finished": eps.filter(expa_status__in=["finished", "completed"]).count(),
            }
        except Exception:
            expa_stats = {"applied": 0, "accepted": 0, "approved": 0, "realized": 0, "finished": 0}

    # Stale computation — always uses all-time
    stale_ep_ids = set()
    for ep in eps.only("pk", "current_stage", "last_activity_at"):
        if (timezone.now() - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
            stale_ep_ids.add(ep.pk)
    total_stale = len(stale_ep_ids)

    # IR stats
    total_irs = irs.count()
    open_opps = sum(ir.open_opportunities_count for ir in irs)
    last_sync = SyncLog.objects.filter(status="success").order_by("-started_at").first()

    # Recent activity
    interactions_qs = Interaction.objects.filter(ep__in=(eps_filtered if date_from else eps))
    if date_from:
        interactions_qs = interactions_qs.filter(date__date__gte=date_from)
        if date_to:
            interactions_qs = interactions_qs.filter(date__date__lte=date_to)

    recent_interactions = interactions_qs.select_related("ep", "author").order_by("-date")[:10]

    if date_from:
        recent_eps = eps_filtered.order_by("-last_activity_at")[:5]
    else:
        recent_eps = eps.order_by("-last_activity_at")[:5]

    realized_period = total_realized
    interactions_period = interactions_qs.count()
    new_eps_period = eps.filter(created_at__date__gte=date_from).count() if date_from else eps.count()

    context = {
        "stage_labels": stage_labels,
        "funnel_counts": funnel_counts,
        "gt_funnel": gt_funnel,
        "gte_funnel": gte_funnel,
        "total_eps": total_eps,
        "total_realized": total_realized,
        "total_problems": total_problems,
        "total_stale": total_stale,
        "total_irs": total_irs,
        "open_opps": open_opps,
        "recent_interactions": recent_interactions,
        "recent_eps": recent_eps,
        "realized_period": realized_period,
        "interactions_period": interactions_period,
        "new_eps_period": new_eps_period,
        "expa_stats": expa_stats,
        "lc_name": config.lc_name,
        "current_term": config.current_term,
        "last_sync": last_sync,
        "expa_token_configured": bool(config.expa_access_token),
        **date_context(date_from, date_to, preset),
    }

    # Pipeline forecast
    thirty_days_ago = timezone.now() - timedelta(days=30)
    realized_last_30 = eps.filter(
        current_stage="realized",
        stage_history__changed_at__gte=thirty_days_ago,
        stage_history__stage="realized",
    ).distinct().count()

    daily_rate = realized_last_30 / 30 if realized_last_30 > 0 else 0
    term_start = timezone.datetime(2026, 1, 1, tzinfo=timezone.get_current_timezone())
    term_end = term_start + timedelta(days=180)
    remaining_days = max(0, (term_end - timezone.now()).days)
    forecast_realized = round(daily_rate * remaining_days)
    current_realized = eps.filter(current_stage="realized").count()
    projected_total = current_realized + forecast_realized

    pipeline_value = eps.filter(
        current_stage__in=["matched_with_opp", "applied", "accepted", "approved",
                           "all_papers_done", "not_all_papers_done", "do_papers"]
    ).count()

    context["forecast"] = {
        "realized_last_30": realized_last_30,
        "daily_rate": round(daily_rate, 2),
        "remaining_days": remaining_days,
        "forecast_realized": forecast_realized,
        "projected_total": projected_total,
        "pipeline_value": pipeline_value,
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

    interactions_qs = Interaction.objects.filter(ep__in=(eps_filtered if date_from else eps))
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
