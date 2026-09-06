"""
Background / scheduled jobs.

Callable as plain Python functions (Render + cron-job.org).
When USE_CELERY=True they are also registered as Celery tasks.
Do NOT call django.setup() here.
"""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def _optional_shared_task(func):
    """Decorate with Celery @shared_task only when USE_CELERY is enabled."""
    if getattr(settings, "USE_CELERY", False):
        from celery import shared_task

        return shared_task(func)
    return func


def dispatch_task(func, *args, **kwargs):
    """Run a task via Celery .delay() when enabled, otherwise call it in-process."""
    if getattr(settings, "USE_CELERY", False) and hasattr(func, "delay"):
        return func.delay(*args, **kwargs)
    return func(*args, **kwargs)


@_optional_shared_task
def check_stale_cases():
    """
    Daily check:
    - Cold EPs (idle > 7 days): notify assigned member, team TL, VP
    - Ghost Opportunities (10+ days, no match): notify IR owner, VP
    """
    from core.models import Notification
    from members.models import Member
    from ops.models import EP, Interaction
    from partners.models import Opportunity

    now = timezone.now()
    today = now.date()
    cold_notified = 0
    ghost_notified = 0

    vp = Member.objects.filter(role="VP", is_active=True).first()
    vp_user = vp.user if vp else None

    cold_cutoff = now - timedelta(days=7)
    cold_eps = EP.objects.filter(
        current_stage__in=["open", "matched_with_opp", "applied", "accepted", "approved"],
        last_activity_at__lt=cold_cutoff,
        is_archived=False,
    ).select_related("assigned_to", "assigned_member", "assigned_area", "assigned_area__tl")

    for ep in cold_eps:
        already_sent = Notification.objects.filter(
            title__startswith=f"❄️ Cold EP: {ep.full_name}",
            created_at__date=today,
        ).exists()
        if already_sent:
            continue

        idle_days = (now - ep.last_activity_at).days
        msg = (
            f"EP {ep.full_name} has been cold for {idle_days} days at stage "
            f"'{ep.get_current_stage_display()}'. Please follow up."
        )
        link = f"/eps/{ep.pk}/"
        notified_user_ids = set()

        assignee = ep.assigned_member or ep.assigned_to
        if assignee and assignee.user:
            Notification.objects.create(
                user=assignee.user,
                title=f"❄️ Cold EP: {ep.full_name}",
                message=msg,
                link=link,
            )
            notified_user_ids.add(assignee.user_id)

        tl = ep.assigned_area.tl if ep.assigned_area else None
        if tl and tl.user and tl.user_id not in notified_user_ids:
            Notification.objects.create(
                user=tl.user,
                title=f"❄️ Cold EP: {ep.full_name}",
                message=msg,
                link=link,
            )
            notified_user_ids.add(tl.user_id)

        if vp_user and vp_user.id not in notified_user_ids:
            Notification.objects.create(
                user=vp_user,
                title=f"❄️ Cold EP: {ep.full_name}",
                message=msg,
                link=link,
            )

        Interaction.objects.create(
            ep=ep,
            author=vp,
            note=f"⚠️ Auto-alert: EP cold for {idle_days} days at '{ep.get_current_stage_display()}'.",
        )
        cold_notified += 1

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
        msg = (
            f"Opportunity '{opp.title}' from {opp.ir.entity_name} has been open "
            f"{days_live} days with no matches. Re-profile or close."
        )
        link = f"/irs/{opp.ir.pk}/"

        if opp.ir.assigned_to and opp.ir.assigned_to.user:
            Notification.objects.create(
                user=opp.ir.assigned_to.user,
                title=f"👻 Ghost Opp: {opp.title}",
                message=msg,
                link=link,
            )
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


@_optional_shared_task
def send_stage_email(log_id: int):
    """Render and send a pending EmailLog via Django's email backend."""
    from core.models import SiteConfig
    from automation.models import EmailLog
    from ops.models import Interaction

    try:
        log = EmailLog.objects.select_related("ep", "template").get(pk=log_id)
    except EmailLog.DoesNotExist:
        return {"status": "error", "message": f"EmailLog {log_id} not found"}

    if log.status != "pending":
        return {"status": "skipped", "message": f"EmailLog {log_id} already {log.status}"}

    if not log.ep.email:
        log.status = "skipped"
        log.save(update_fields=["status"])
        return {"status": "skipped", "message": f"EP {log.ep.full_name} has no email"}

    if not log.template:
        log.status = "failed"
        log.save(update_fields=["status"])
        return {"status": "failed", "message": "Template missing"}

    config = SiteConfig.get()

    try:
        rendered = log.template.render(log.ep, lc_name=config.lc_name)

        send_mail(
            subject=rendered["subject"],
            message=rendered["body"],
            from_email=None,
            recipient_list=[log.ep.email],
            fail_silently=False,
        )

        log.subject = rendered["subject"]
        log.body = rendered["body"]
        log.status = "sent"
        log.save(update_fields=["subject", "body", "status"])

        Interaction.objects.create(
            ep=log.ep,
            author=None,
            note=f'📧 Auto-email sent: "{rendered["subject"]}" (template: {log.template.name})',
        )

        return {"status": "sent", "ep": log.ep.full_name, "template": log.template.name}

    except Exception as exc:
        log.status = "failed"
        log.save(update_fields=["status"])
        return {"status": "failed", "error": str(exc)}


def queue_stage_emails_for_ep(ep, stage: str | None = None):
    """Create pending EmailLogs for an EP stage and send them (sync, or Celery if enabled)."""
    from automation.models import EmailLog, EmailTemplate

    trigger = stage or ep.current_stage
    templates = EmailTemplate.objects.filter(trigger_stage=trigger, is_active=True)
    results = []
    for template in templates:
        log = EmailLog.objects.create(
            ep=ep,
            template=template,
            subject=template.subject,
            body=template.body,
            status="pending",
        )
        results.append(dispatch_task(send_stage_email, log.pk))
    return results


def send_pending_stage_emails():
    """Drain the EmailLog pending queue (cron fallback if sync SMTP failed)."""
    from automation.models import EmailLog

    pending_ids = list(
        EmailLog.objects.filter(status="pending").values_list("pk", flat=True)
    )
    results = [send_stage_email(log_id) for log_id in pending_ids]
    sent = sum(1 for r in results if r.get("status") == "sent")
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    return {
        "processed": len(results),
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }


@_optional_shared_task
def send_weekly_digest():
    """Weekly digest: aggregates stats for WhatsApp / EB meeting."""
    from core.models import SiteConfig
    from members.models import Member
    from ops.models import EP, Interaction
    from partners.models import IR

    now = timezone.now()
    week_ago = now - timedelta(days=7)

    total_eps = EP.objects.count()
    realized_this_week = (
        EP.objects.filter(
            current_stage="realized",
            stage_history__changed_at__gte=week_ago,
            stage_history__stage="realized",
        )
        .distinct()
        .count()
    )

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
    for ep in EP.objects.exclude(current_stage="realized").only("pk", "current_stage", "last_activity_at"):
        if (now - ep.last_activity_at).days > config.get_threshold(ep.current_stage):
            stale_count += 1

    stage_order = [
        "open",
        "matched_with_opp",
        "applied",
        "accepted",
        "approved",
        "all_papers_done",
        "not_all_papers_done",
        "do_papers",
        "realized",
    ]
    funnel = {EP.Stage(s).label: EP.objects.filter(current_stage=s).count() for s in stage_order}

    irs = IR.objects.all()
    top_irs = sorted(
        [{"name": ir.entity_name, "country": ir.country, "realized": ir.realized_count} for ir in irs],
        key=lambda x: x["realized"],
        reverse=True,
    )[:3]

    interactions_this_week = Interaction.objects.filter(date__gte=week_ago).count()

    ops_members = Member.objects.filter(role__in=["MEM", "TL"], is_active=True)
    top_ops = []
    for m in ops_members:
        realized = EP.objects.filter(assigned_to=m, current_stage="realized").count()
        if realized > 0:
            top_ops.append({"name": m.name, "realized": realized})
    top_ops.sort(key=lambda x: x["realized"], reverse=True)

    return {
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
