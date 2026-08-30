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
    Daily check at 09:00:
    - Cold EPs (idle > 7 days): notify assigned_member, assigned_tl, VP
    - Ghost Opportunities (10+ days, no match): notify IR owner, IR TL, VP
    """
    from core.models import SiteConfig, Notification
    from members.models import Member
    from ops.models import EP, Interaction
    from partners.models import Opportunity

    config = SiteConfig.get()
    now = timezone.now()
    today = now.date()
    cold_notified = 0
    ghost_notified = 0

    vp = Member.objects.filter(role="VP", is_active=True).first()
    vp_user = vp.user if vp else None

    # ── Cold EPs ──────────────────────────────────────────────────────
    cold_cutoff = now - timedelta(days=7)
    cold_eps = EP.objects.filter(
        current_stage__in=["open", "matched_with_opp", "applied", "accepted", "approved"],
        last_activity_at__lt=cold_cutoff,
    ).select_related("assigned_to", "assigned_tl")

    for ep in cold_eps:
        # Deduplicate: only one COLD notification per EP per day
        already_sent = Notification.objects.filter(
            title__startswith=f"❄️ Cold EP: {ep.full_name}",
            created_at__date=today,
        ).exists()
        if already_sent:
            continue

        idle_days = (now - ep.last_activity_at).days
        msg = f"EP {ep.full_name} has been cold for {idle_days} days at stage '{ep.get_current_stage_display()}'. Please follow up."
        link = f"/eps/{ep.pk}/"

        # Notify assigned member
        if ep.assigned_to and ep.assigned_to.user:
            Notification.objects.create(
                user=ep.assigned_to.user,
                title=f"❄️ Cold EP: {ep.full_name}",
                message=msg,
                link=link,
            )
        # Notify TL
        if ep.assigned_tl and ep.assigned_tl.user:
            Notification.objects.create(
                user=ep.assigned_tl.user,
                title=f"❄️ Cold EP: {ep.full_name}",
                message=msg,
                link=link,
            )
        # Notify VP
        if vp_user and (not ep.assigned_to or ep.assigned_to.user != vp_user):
            Notification.objects.create(
                user=vp_user,
                title=f"❄️ Cold EP: {ep.full_name}",
                message=msg,
                link=link,
            )
        # Log interaction as before
        if ep.assigned_to:
            Interaction.objects.create(
                ep=ep,
                author=vp,
                note=f"⚠️ Auto-alert: EP cold for {idle_days} days at '{ep.get_current_stage_display()}'.",
            )
        cold_notified += 1

    # ── Ghost Opportunities ────────────────────────────────────────────
    ghost_cutoff = now - timedelta(days=10)
    ghost_opps = Opportunity.objects.filter(
        is_open=True,
        created_at__lt=ghost_cutoff,
        match_records__isnull=True,
    ).select_related("ir__assigned_to").distinct()

    for opp in ghost_opps:
        already_sent = Notification.objects.filter(
            title__startswith=f"👻 Ghost Opp: {opp.title}",
            created_at__date=today,
        ).exists()
        if already_sent:
            continue

        days_live = (now - opp.created_at).days
        msg = f"Opportunity '{opp.title}' from {opp.ir.entity_name} has been open {days_live} days with no matches. Re-profile or close."
        link = f"/partners/ir/{opp.ir.pk}/"

        # Notify IR owner
        if opp.ir.assigned_to and opp.ir.assigned_to.user:
            Notification.objects.create(
                user=opp.ir.assigned_to.user,
                title=f"👻 Ghost Opp: {opp.title}",
                message=msg,
                link=link,
            )
        # Notify VP
        if vp_user:
            Notification.objects.create(
                user=vp_user,
                title=f"👻 Ghost Opp: {opp.title}",
                message=msg,
                link=link,
            )
        ghost_notified += 1

    return {
        "cold_ep_notifications": cold_notified,
        "ghost_opp_notifications": ghost_notified,
        "message": f"Sent {cold_notified} cold EP + {ghost_notified} ghost opp alerts.",
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
