from datetime import timedelta

from django.db.models import Avg, Count, F, Q
from django.shortcuts import render
from django.utils import timezone

from core.models import SiteConfig, SyncLog
from members.models import Member
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

    # ── Scoped EP queryset ───────────────────────────────────────────
    eps = member.get_visible_eps()
    irs = member.get_visible_irs()

    # ── Date-filtered EP subset ──────────────────────────────────────
    if date_from:
        eps_filtered = eps.filter(last_activity_at__date__gte=date_from)
        if date_to:
            eps_filtered = eps_filtered.filter(last_activity_at__date__lte=date_to)
    else:
        eps_filtered = eps

    # ── Funnel counts per stage (always all-time) ────────────────────
    stage_order = [
        "open", "matched_with_opp", "applied", "accepted",
        "approved", "all_papers_done", "not_all_papers_done",
        "do_papers", "realized",
    ]
    stage_labels = [EP.Stage(s).label for s in stage_order]

    funnel_counts = []
    for s in stage_order:
        funnel_counts.append(eps.filter(current_stage=s).count())

    gt_funnel = []
    gte_funnel = []
    for s in stage_order:
        gt_funnel.append(eps.filter(current_stage=s, track="GT").count())
        gte_funnel.append(eps.filter(current_stage=s, track="GTe").count())

    # ── Totals ───────────────────────────────────────────────────────
    total_eps = eps.count()
    total_realized = eps_filtered.filter(current_stage="realized").count()
    total_problems = eps.exclude(problem_flag="none").count()

    # Stale computation (all-time, not date-filtered — staleness is about now)
    stale_ep_ids = set()
    for ep in eps.only("pk", "current_stage", "last_activity_at"):
        if (timezone.now() - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
            stale_ep_ids.add(ep.pk)
    total_stale = len(stale_ep_ids)

    # ── IR stats + EXPA sync ───────────────────────────────────────
    total_irs = irs.count()
    open_opps = sum(ir.open_opportunities_count for ir in irs)
    last_sync = SyncLog.objects.filter(status="success").order_by("-started_at").first()

    # ── Recent activity ──────────────────────────────────────────────
    interactions_qs = Interaction.objects.filter(ep__in=eps)
    if date_from:
        interactions_qs = interactions_qs.filter(date__date__gte=date_from)
        if date_to:
            interactions_qs = interactions_qs.filter(date__date__lte=date_to)

    recent_interactions = (
        interactions_qs.select_related("ep", "author")
        .order_by("-date")[:10]
    )

    recent_eps = eps_filtered.order_by("-last_activity_at")[:5]

    # ── Date-filtered period stats ───────────────────────────────────
    realized_period = eps_filtered.filter(current_stage="realized").count()
    interactions_period = interactions_qs.count()
    new_eps_period = eps.filter(created_at__date__gte=date_from).count() if date_from else eps.count()

    context = {
        # Funnel
        "stage_labels": stage_labels,
        "funnel_counts": funnel_counts,
        "gt_funnel": gt_funnel,
        "gte_funnel": gte_funnel,
        # Totals
        "total_eps": total_eps,
        "total_realized": total_realized,
        "total_problems": total_problems,
        "total_stale": total_stale,
        "total_irs": total_irs,
        "open_opps": open_opps,
        # Activity
        "recent_interactions": recent_interactions,
        "recent_eps": recent_eps,
        "realized_period": realized_period,
        "interactions_period": interactions_period,
        "new_eps_period": new_eps_period,
        # Date filter state
        "preset": preset,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        # Config
        "lc_name": config.lc_name,
        "current_term": config.current_term,
        "last_sync": last_sync,
        "expa_token_configured": bool(config.expa_access_token),
    }

    # ── Pipeline forecast ──────────────────────────────────────────
    # Rate: realized in last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    realized_last_30 = eps.filter(
        current_stage="realized",
        stage_history__changed_at__gte=thirty_days_ago,
        stage_history__stage="realized",
    ).distinct().count()

    daily_rate = realized_last_30 / 30 if realized_last_30 > 0 else 0
    # Days remaining in term (rough: 180 day term)
    term_start = timezone.datetime(2026, 1, 1, tzinfo=timezone.get_current_timezone())
    term_end = term_start + timedelta(days=180)
    remaining_days = max(0, (term_end - timezone.now()).days)
    forecast_realized = round(daily_rate * remaining_days)

    # Current realized + forecast = projected total
    current_realized = eps.filter(current_stage="realized").count()
    projected_total = current_realized + forecast_realized

    # Pipeline value: EPs past "matched_with_opp" but not yet realized
    pipeline_value = eps.filter(
        current_stage__in=["matched_with_opp", "applied", "accepted", "approved", "all_papers_done", "not_all_papers_done", "do_papers"]
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
    """Member engagement leaderboard — framed positively."""
    member = request.current_member
    eps = member.get_visible_eps()

    # ── Per-member stats (scoped to visible members) ─────────────────
    visible_members = Member.objects.filter(is_active=True)
    if not member.is_vp():
        if member.team:
            visible_members = visible_members.filter(team=member.team)
        else:
            visible_members = visible_members.filter(pk=member.pk)

    stats = []
    for m in visible_members:
        m_eps = eps.filter(assigned_to=m)
        realized = m_eps.filter(current_stage="realized").count()
        total = m_eps.count()

        # Avg resolution time: from first StageHistory to 'realized' stage
        realized_eps = m_eps.filter(current_stage="realized")
        avg_days = None
        if realized_eps.exists():
            total_days = 0
            count = 0
            for ep in realized_eps:
                first = ep.stage_history.order_by("changed_at").first()
                realized_entry = ep.stage_history.filter(stage="realized").order_by("-changed_at").first()
                if first and realized_entry:
                    delta = (realized_entry.changed_at - first.changed_at).days
                    total_days += max(delta, 1)
                    count += 1
            if count > 0:
                avg_days = round(total_days / count, 1)

        # Interactions this week
        week_ago = timezone.now() - timedelta(days=7)
        interactions_week = Interaction.objects.filter(
            author=m, ep__in=eps, date__gte=week_ago
        ).count()

        # Current open EPs
        open_eps = m_eps.exclude(current_stage="realized").count()

        stats.append({
            "member": m,
            "realized": realized,
            "total": total,
            "avg_days": avg_days,
            "interactions_week": interactions_week,
            "open_eps": open_eps,
        })

    # Sort by realized desc
    stats.sort(key=lambda x: x["realized"], reverse=True)

    # Top performers
    top_realized = [s for s in stats if s["realized"] > 0][:3]
    top_engagement = sorted(
        [s for s in stats if s["interactions_week"] > 0],
        key=lambda x: x["interactions_week"], reverse=True
    )[:3]

    context = {
        "stats": stats,
        "top_realized": top_realized,
        "top_engagement": top_engagement,
        "total_realized": sum(s["realized"] for s in stats),
    }
    return render(request, "dashboard/leaderboard.html", context)


def compare(request):
    """Term-over-term comparison dashboard."""
    member = request.current_member
    eps = member.get_visible_eps().filter(is_archived=False)

    # Available terms
    terms = sorted(
        eps.values_list("term", flat=True).distinct(),
        reverse=True,
    )

    # Default: compare current vs previous
    current_term = request.GET.get("term1", terms[0] if terms else "2026-S1")
    prev_term = request.GET.get("term2", terms[1] if len(terms) > 1 else "")

    def term_stats(term):
        t_eps = eps.filter(term=term)
        total = t_eps.count()
        realized = t_eps.filter(current_stage="realized").count()
        problems = t_eps.filter(problem_flag__in=["fix_ep_problem", "fix_ir_problem"]).count()
        interactions = Interaction.objects.filter(ep__term=term).count()

        stage_order = ["open", "matched_with_opp", "applied", "accepted", "approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"]
        funnel = []
        for s in stage_order:
            funnel.append({"label": EP.Stage(s).label, "count": t_eps.filter(current_stage=s).count()})

        # Conversion: open → realized rate
        conversion = round(realized / total * 100, 1) if total > 0 else 0

        return {
            "total": total,
            "realized": realized,
            "problems": problems,
            "interactions": interactions,
            "funnel": funnel,
            "conversion": conversion,
        }

    current_stats = term_stats(current_term)
    prev_stats = term_stats(prev_term) if prev_term else None

    # Delta calculations
    delta = None
    if prev_stats and prev_stats["total"] > 0:
        delta = {
            "total": current_stats["total"] - prev_stats["total"],
            "realized": current_stats["realized"] - prev_stats["realized"],
            "conversion": round(current_stats["conversion"] - prev_stats["conversion"], 1),
        }

    context = {
        "terms": terms,
        "current_term": current_term,
        "prev_term": prev_term,
        "current_stats": current_stats,
        "prev_stats": prev_stats,
        "delta": delta,
    }
    return render(request, "dashboard/compare.html", context)


def workload(request):
    """Team workload dashboard — per-member EP load with color coding."""
    member = request.current_member
    config = SiteConfig.get()
    eps = member.get_visible_eps().filter(is_archived=False)

    # Determine visible members
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

        stale_count = 0
        problem_count = m_eps.filter(
            problem_flag__in=["fix_ep_problem", "fix_ir_problem"]
        ).count()
        realized = m_eps.filter(current_stage="realized").count()

        # Stale per EP
        for ep in m_eps.only("pk", "current_stage", "last_activity_at"):
            if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
                stale_count += 1

        # Per-stage breakdown
        stage_breakdown = defaultdict(int)
        for ep in m_eps:
            stage_breakdown[ep.get_current_stage_display()] += 1

        members_data.append({
            "member": m,
            "total": total,
            "stale_count": stale_count,
            "problem_count": problem_count,
            "realized": realized,
            "stage_breakdown": dict(stage_breakdown),
        })

    members_data.sort(key=lambda x: x["total"], reverse=True)

    context = {
        "members_data": members_data,
        "total_eps": eps.count(),
        "total_members": len(visible_members),
    }
    return render(request, "dashboard/workload.html", context)


def trigger_expa_sync(request):
    """Manually trigger an EXPA sync from the dashboard."""
    from automation.tasks import sync_expa_eps

    sync_log = SyncLog.objects.create(status="running")
    sync_expa_eps.delay(sync_log_id=sync_log.pk)

    from django.contrib import messages
    messages.info(request, "🔄 EXPA sync started in background. Results will appear shortly.")
    return redirect("dashboard")
