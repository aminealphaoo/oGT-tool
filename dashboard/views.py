from datetime import timedelta

from django.db.models import Avg, Count, F, Q
from django.shortcuts import render
from django.utils import timezone

from core.models import SiteConfig, SyncLog
from members.models import Member, Team
from ops.models import EP, Interaction, StageHistory
from partners.models import IR

from collections import defaultdict


def _parse_date_range(request):
    """Parse date_from/date_to from request.GET. Returns (date_from, date_to, preset)."""
    from datetime import date

    preset = request.GET.get("preset", "all")
    now = timezone.now().date()

    if preset == "week":
        return now - timedelta(days=7), now, preset
    if preset == "month":
        return now - timedelta(days=30), now, preset
    if preset == "term":
        return now - timedelta(days=180), now, preset

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    try:
        date_from = date.fromisoformat(date_from) if date_from else None
    except ValueError:
        date_from = None
    try:
        date_to = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        date_to = None

    return date_from, date_to, preset


def dashboard(request):
    """Role-scoped dashboard with funnel stats, problem counts, stale counts, date filter."""
    member = request.current_member
    config = SiteConfig.get()
    date_from, date_to, preset = _parse_date_range(request)

    eps = member.get_visible_eps()
    irs = member.get_visible_irs()

    if date_from:
        eps_filtered = eps.filter(last_activity_at__date__gte=date_from)
        if date_to:
            eps_filtered = eps_filtered.filter(last_activity_at__date__lte=date_to)
    else:
        eps_filtered = eps

    stage_order = ["open", "matched_with_opp", "applied", "accepted", "approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"]
    stage_labels = [EP.Stage(s).label for s in stage_order]

    funnel_counts = [eps.filter(current_stage=s).count() for s in stage_order]
    gt_funnel = [eps.filter(current_stage=s, track="GT").count() for s in stage_order]
    gte_funnel = [eps.filter(current_stage=s, track="GTe").count() for s in stage_order]

    total_eps = eps.count()
    total_realized = eps_filtered.filter(current_stage="realized").count()
    total_problems = eps.exclude(problem_flag="none").count()

    stale_ep_ids = set()
    for ep in eps.only("pk", "current_stage", "last_activity_at"):
        if (timezone.now() - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
            stale_ep_ids.add(ep.pk)
    total_stale = len(stale_ep_ids)

    total_irs = irs.count()
    open_opps = sum(ir.open_opportunities_count for ir in irs)
    last_sync = SyncLog.objects.filter(status="success").order_by("-started_at").first()

    interactions_qs = Interaction.objects.filter(ep__in=eps)
    if date_from:
        interactions_qs = interactions_qs.filter(date__date__gte=date_from)
        if date_to:
            interactions_qs = interactions_qs.filter(date__date__lte=date_to)

    recent_interactions = interactions_qs.select_related("ep", "author").order_by("-date")[:10]
    recent_eps = eps_filtered.order_by("-last_activity_at")[:5]

    realized_period = eps_filtered.filter(current_stage="realized").count()
    interactions_period = interactions_qs.count()
    new_eps_period = eps.filter(created_at__date__gte=date_from).count() if date_from else eps.count()

    context = {
        "stage_labels": stage_labels, "funnel_counts": funnel_counts,
        "gt_funnel": gt_funnel, "gte_funnel": gte_funnel,
        "total_eps": total_eps, "total_realized": total_realized,
        "total_problems": total_problems, "total_stale": total_stale,
        "total_irs": total_irs, "open_opps": open_opps,
        "recent_interactions": recent_interactions, "recent_eps": recent_eps,
        "realized_period": realized_period, "interactions_period": interactions_period,
        "new_eps_period": new_eps_period,
        "preset": preset, "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "lc_name": config.lc_name, "current_term": config.current_term,
        "last_sync": last_sync, "expa_token_configured": bool(config.expa_access_token),
    }

    thirty_days_ago = timezone.now() - timedelta(days=30)
    realized_last_30 = eps.filter(current_stage="realized", stage_history__changed_at__gte=thirty_days_ago, stage_history__stage="realized").distinct().count()
    daily_rate = realized_last_30 / 30 if realized_last_30 > 0 else 0
    term_start = timezone.datetime(2026, 1, 1, tzinfo=timezone.get_current_timezone())
    term_end = term_start + timedelta(days=180)
    remaining_days = max(0, (term_end - timezone.now()).days)
    forecast_realized = round(daily_rate * remaining_days)
    current_realized = eps.filter(current_stage="realized").count()
    projected_total = current_realized + forecast_realized
    pipeline_value = eps.filter(current_stage__in=["matched_with_opp", "applied", "accepted", "approved", "all_papers_done", "not_all_papers_done", "do_papers"]).count()

    context["forecast"] = {"realized_last_30": realized_last_30, "daily_rate": round(daily_rate, 2), "remaining_days": remaining_days, "forecast_realized": forecast_realized, "projected_total": projected_total, "pipeline_value": pipeline_value}
    return render(request, "dashboard/index.html", context)


def leaderboard(request):
    """Member engagement leaderboard with filters, badges, charts, streaks."""
    member = request.current_member
    config = SiteConfig.get()
    eps = member.get_visible_eps()
    date_from, date_to, preset = _parse_date_range(request)

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
    stats = []
    for m in visible_members:
        m_eps = eps.filter(assigned_to=m)
        m_eps_filtered = eps_filtered.filter(assigned_to=m)
        if track_filter:
            m_eps = m_eps.filter(track=track_filter)
            m_eps_filtered = m_eps_filtered.filter(track=track_filter)

        total = m_eps.count()
        realized = m_eps_filtered.filter(current_stage="realized").count()
        realized_alltime = m_eps.filter(current_stage="realized").count()
        problems = m_eps.filter(problem_flag__in=["fix_ep_problem", "fix_ir_problem"]).count()
        open_eps = m_eps.exclude(current_stage="realized").count()
        stale = sum(1 for ep in m_eps.only("pk", "current_stage", "last_activity_at") if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage))

        realized_eps = m_eps.filter(current_stage="realized")
        avg_days = None
        if realized_eps.exists():
            total_days, cnt = 0, 0
            for ep in realized_eps:
                first = ep.stage_history.order_by("changed_at").first()
                realized_entry = ep.stage_history.filter(stage="realized").order_by("-changed_at").first()
                if first and realized_entry:
                    total_days += max((realized_entry.changed_at - first.changed_at).days, 1)
                    cnt += 1
            if cnt > 0:
                avg_days = round(total_days / cnt, 1)

        m_interactions = interactions_qs.filter(author=m)
        interactions_count = m_interactions.count()
        new_eps = m_eps.filter(created_at__date__gte=date_from).count() if date_from else 0
        streak = _compute_streak(m, eps)

        gt_count = m_eps.filter(track="GT").count()
        gte_count = m_eps.filter(track="GTe").count()

        stats.append({
            "member": m, "total": total, "realized": realized,
            "realized_alltime": realized_alltime, "problems": problems,
            "open_eps": open_eps, "stale": stale, "avg_days": avg_days,
            "interactions_count": interactions_count, "new_eps": new_eps,
            "streak": streak, "gt_count": gt_count, "gte_count": gte_count,
            "team_name": m.team.name if m.team else "—",
        })

    sort_by = request.GET.get("sort", "realized")
    sort_order = request.GET.get("order", "desc")
    reverse = sort_order == "desc"
    key_map = {"realized": "realized", "total": "total", "interactions": "interactions_count", "avg_days": "avg_days", "open": "open_eps", "streak": "streak", "new": "new_eps"}
    key = key_map.get(sort_by, "realized")
    stats.sort(key=lambda x: (x[key] is None, x[key] if x[key] is not None else 0), reverse=reverse)

    top_realized = [s for s in stats if s["realized"] > 0][:3]
    top_engagement = sorted([s for s in stats if s["interactions_count"] > 0], key=lambda x: x["interactions_count"], reverse=True)[:3]
    top_streak = sorted([s for s in stats if s["streak"] > 0], key=lambda x: x["streak"], reverse=True)[:3]

    for s in stats:
        badges = []
        if s["realized_alltime"] >= 10:
            badges.append({"icon": "trophy", "label": "10+ Realized", "emoji": "\ud83c\udfc6", "color": "gold"})
        elif s["realized_alltime"] >= 5:
            badges.append({"icon": "award", "label": "5+ Realized", "emoji": "\u2b50", "color": "silver"})
        if s["interactions_count"] >= 50:
            badges.append({"icon": "chat-dots", "label": "50+ Interactions", "emoji": "\ud83d\udcac", "color": "blue"})
        if s["avg_days"] and s["avg_days"] < 30 and s["realized"] >= 3:
            badges.append({"icon": "lightning", "label": "Speed <30d", "emoji": "\u26a1", "color": "green"})
        if s["streak"] >= 4:
            badges.append({"icon": "fire", "label": f"{s['streak']}wk Streak", "emoji": "\ud83d\udd25", "color": "orange"})
        if s["stale"] == 0 and s["total"] > 0:
            badges.append({"icon": "shield-check", "label": "Zero Stale", "emoji": "\ud83d\udee1\ufe0f", "color": "teal"})
        if s["new_eps"] >= 3:
            badges.append({"icon": "star", "label": "Rising Star", "emoji": "\ud83c\udf1f", "color": "pink"})
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
        "sort_by": sort_by, "sort_order": sort_order, "preset": preset,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "tracks": EP.Track.choices, "member_count": len(stats),
    }
    return render(request, "dashboard/leaderboard.html", context)


def _compute_streak(member, eps):
    now = timezone.now().date()
    streak = 0
    this_week_start = now - timedelta(days=now.weekday())
    this_week_count = Interaction.objects.filter(author=member, ep__in=eps, date__date__gte=this_week_start, date__date__lte=now).count()
    if this_week_count > 0:
        streak += 1
    for i in range(12):
        week_start = now - timedelta(days=now.weekday() + 7 * (i + 1))
        week_end = week_start + timedelta(days=6)
        count = Interaction.objects.filter(author=member, ep__in=eps, date__date__gte=week_start, date__date__lte=week_end).count()
        if count > 0:
            streak += 1
        else:
            break
    return streak


def leaderboard_export_csv(request):
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
    writer.writerow(["Rank", "Name", "Role", "Team", "Realized", "Total EPs", "Open EPs", "Interactions", "Avg Days", "Streak", "Stale", "Badges"])
    for i, m in enumerate(visible_members, 1):
        m_eps = eps.filter(assigned_to=m)
        realized = m_eps.filter(current_stage="realized").count()
        interactions = Interaction.objects.filter(author=m, ep__in=eps).count()
        writer.writerow([i, m.name, m.get_role_display(), m.team.name if m.team else "", realized, m_eps.count(), m_eps.exclude(current_stage="realized").count(), interactions, "", "", "", ""])
    return response


def compare(request):
    """Term-over-term comparison dashboard."""
    member = request.current_member
    eps = member.get_visible_eps().filter(is_archived=False)
    terms = sorted(eps.values_list("term", flat=True).distinct(), reverse=True)
    current_term = request.GET.get("term1", terms[0] if terms else "2026-S1")
    prev_term = request.GET.get("term2", terms[1] if len(terms) > 1 else "")

    def term_stats(term):
        t_eps = eps.filter(term=term)
        total = t_eps.count()
        realized = t_eps.filter(current_stage="realized").count()
        problems = t_eps.filter(problem_flag__in=["fix_ep_problem", "fix_ir_problem"]).count()
        interactions = Interaction.objects.filter(ep__term=term).count()
        stage_order = ["open", "matched_with_opp", "applied", "accepted", "approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"]
        funnel = [{"label": EP.Stage(s).label, "count": t_eps.filter(current_stage=s).count()} for s in stage_order]
        conversion = round(realized / total * 100, 1) if total > 0 else 0
        return {"total": total, "realized": realized, "problems": problems, "interactions": interactions, "funnel": funnel, "conversion": conversion}

    current_stats = term_stats(current_term)
    prev_stats = term_stats(prev_term) if prev_term else None
    delta = None
    if prev_stats and prev_stats["total"] > 0:
        delta = {"total": current_stats["total"] - prev_stats["total"], "realized": current_stats["realized"] - prev_stats["realized"], "conversion": round(current_stats["conversion"] - prev_stats["conversion"], 1)}
    context = {"terms": terms, "current_term": current_term, "prev_term": prev_term, "current_stats": current_stats, "prev_stats": prev_stats, "delta": delta}
    return render(request, "dashboard/compare.html", context)


def workload(request):
    member = request.current_member
    config = SiteConfig.get()
    eps = member.get_visible_eps().filter(is_archived=False)
    if member.is_vp():
        visible_members = Member.objects.filter(is_active=True)
    elif member.is_tl() and member.team:
        visible_members = Member.objects.filter(team=member.team, is_active=True)
    else:
        visible_members = Member.objects.filter(pk=member.pk, is_active=True)
    now = timezone.now()
    members_data = []
    for m in visible_members:
        m_eps = eps.filter(assigned_to=m)
        total = m_eps.count()
        stale_count, problem_count = 0, m_eps.filter(problem_flag__in=["fix_ep_problem", "fix_ir_problem"]).count()
        realized = m_eps.filter(current_stage="realized").count()
        for ep in m_eps.only("pk", "current_stage", "last_activity_at"):
            if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
                stale_count += 1
        stage_breakdown = defaultdict(int)
        for ep in m_eps:
            stage_breakdown[ep.get_current_stage_display()] += 1
        members_data.append({"member": m, "total": total, "stale_count": stale_count, "problem_count": problem_count, "realized": realized, "stage_breakdown": dict(stage_breakdown)})
    members_data.sort(key=lambda x: x["total"], reverse=True)
    context = {"members_data": members_data, "total_eps": eps.count(), "total_members": len(visible_members)}
    return render(request, "dashboard/workload.html", context)


def trigger_expa_sync(request):
    from automation.tasks import sync_expa_eps
    sync_log = SyncLog.objects.create(status="running")
    sync_expa_eps.delay(sync_log_id=sync_log.pk)
    from django.contrib import messages
    messages.info(request, "EXPA sync started in background.")
    return redirect("dashboard")
