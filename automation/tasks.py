"""
Background tasks — Phase 2+.
Celery worker calls django.setup() via aiesec_tool/celery.py.
Do NOT call django.setup() here — it causes double-init when imported by Django.
"""
from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone



@shared_task
def check_stale_cases():
    """
    Daily check: find EPs exceeding per-stage idle thresholds.
    Uses stage-loop queries instead of per-EP loop — 9 queries max.
    """
    from core.models import SiteConfig
    from members.models import Member
    from ops.models import EP, Interaction

    config = SiteConfig.get()
    now = timezone.now()
    stale_eps = []

    stage_thresholds = {
        "open": 14,
        "matched_with_opp": 7,
        "applied": 7,
        "accepted": 14,
        "approved": 14,
        "all_papers_done": 7,
        "not_all_papers_done": 7,
        "do_papers": 14,
    }

    for stage, default_threshold in stage_thresholds.items():
        threshold = config.get_threshold(stage) or default_threshold
        cutoff = now - timedelta(days=threshold)
        stage_stales = EP.objects.filter(
            current_stage=stage,
            last_activity_at__lt=cutoff,
        )
        stale_eps.extend(list(stage_stales))

    if not stale_eps:
        return {"stale_count": 0, "message": "No stale cases today."}

    system_member = Member.objects.filter(role="VP", is_active=True).first()
    for ep in stale_eps:
        Interaction.objects.create(
            ep=ep,
            author=system_member,
            note=(
                f"⚠️ Auto-alert: EP has been idle for "
                f"{(timezone.now() - ep.last_activity_at).days} days "
                f"at stage '{ep.get_current_stage_display()}'. "
                f"Threshold: {config.get_threshold(ep.current_stage)} days. "
                f"Please follow up."
            ),
        )

    summary_lines = [
        f"EP: {ep.full_name} — {ep.get_current_stage_display()} — idle {(timezone.now() - ep.last_activity_at).days}d"
        for ep in stale_eps
    ]

    return {
        "stale_count": len(stale_eps),
        "stale_eps": summary_lines,
        "message": f"Found {len(stale_eps)} stale case(s). Interactions logged.",
    }


@shared_task
def send_stage_email(log_id: int):
    """Render and actually send a pending EmailLog via Django's email backend."""
    from automation.models import EmailLog
    from ops.models import Interaction

    try:
        log = EmailLog.objects.select_related("ep", "template").get(pk=log_id)
    except EmailLog.DoesNotExist:
        return {"status": "error", "message": f"EmailLog {log_id} not found"}

    if log.status != "pending":
        return {"status": "skipped", "message": f"EmailLog {log_id} already {log.status}"}

    config = SiteConfig.get()

    try:
        rendered = log.template.render(log.ep, lc_name=config.lc_name)

        # Send via Django email backend
        send_mail(
            subject=rendered["subject"],
            message=rendered["body"],
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[log.ep.email],
            fail_silently=False,
        )

        log.subject = rendered["subject"]
        log.body = rendered["body"]
        log.status = "sent"
        log.save(update_fields=["subject", "body", "status"])

        # Log as interaction
        Interaction.objects.create(
            ep=log.ep,
            author=None,
            note=f"📧 Auto-email sent: \"{rendered['subject']}\" (template: {log.template.name})",
        )

        return {"status": "sent", "ep": log.ep.full_name, "template": log.template.name}

    except Exception as exc:
        log.status = "failed"
        log.save(update_fields=["status"])
        return {"status": "failed", "error": str(exc)}


@shared_task
def send_weekly_digest():
    """
    Weekly digest: aggregates stats for WhatsApp / EB meeting.
    Returns a dict with all key metrics.
    """
    from core.models import SiteConfig
    from members.models import Member
    from ops.models import EP, Interaction
    from partners.models import IR

    now = timezone.now()
    week_ago = now - timedelta(days=7)

    total_eps = EP.objects.count()
    realized_this_week = EP.objects.filter(
        current_stage="realized",
        stage_history__changed_at__gte=week_ago,
        stage_history__stage="realized",
    ).distinct().count()

    new_eps_this_week = EP.objects.filter(created_at__gte=week_ago).count()

    active_problems = EP.objects.filter(
        problem_flag__in=["fix_ep_problem", "fix_ir_problem"]
    ).count()
    new_problems_this_week = EP.objects.filter(
        problem_flag__in=["fix_ep_problem", "fix_ir_problem"],
        last_activity_at__gte=week_ago,
    ).count()

    config = SiteConfig.get()
    stale_count = 0
    for ep in EP.objects.exclude(current_stage="realized"):
        if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
            stale_count += 1

    stage_order = [
        "open", "matched_with_opp", "applied", "accepted",
        "approved", "all_papers_done", "not_all_papers_done",
        "do_papers", "realized",
    ]
    funnel = {}
    for s in stage_order:
        funnel[EP.Stage(s).label] = EP.objects.filter(current_stage=s).count()

    irs = IR.objects.all()
    top_irs = sorted(
        [{"name": ir.entity_name, "country": ir.country, "realized": ir.realized_count}
         for ir in irs],
        key=lambda x: x["realized"], reverse=True
    )[:3]

    interactions_this_week = Interaction.objects.filter(date__gte=week_ago).count()

    ops_members = Member.objects.filter(role__in=["OPS", "TL"], is_active=True)
    top_ops = []
    for m in ops_members:
        realized = EP.objects.filter(assigned_to=m, current_stage="realized").count()
        if realized > 0:
            top_ops.append({"name": m.name, "realized": realized})
    top_ops.sort(key=lambda x: x["realized"], reverse=True)

    digest = {
        "period": f"{week_ago.strftime('%b %d')} → {now.strftime('%b %d, %Y')}",
        "realized_this_week": realized_this_week,
        "new_eps_this_week": new_eps_this_week,
        "total_eps": total_eps,
        "active_problems": active_problems,
        "new_problems_this_week": new_problems_this_week,
        "stale_count": stale_count,
        "interactions_this_week": interactions_this_week,
        "funnel": funnel,
        "top_irs": top_irs,
        "top_ops": top_ops,
    }

    return digest
