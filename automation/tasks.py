"""
Background tasks — Phase 2+.
"""
import os
from datetime import timedelta

import django
from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aiesec_tool.settings")
django.setup()

from core.models import SiteConfig
from members.models import Member
from ops.models import EP, Interaction
from partners.models import IR


@shared_task
def sync_expa_eps(sync_log_id=None):
    """
    Pull applications from EXPA GraphQL API and create/update EPs.
    Uses allOpportunityApplication query with pagination.
    """
    import json
    from urllib.request import Request, urlopen

    config = SiteConfig.get()
    token = config.expa_access_token or "5zPLES-3w6pq82iPrXgojR3JoV99Qnx6kogE-yJE0EY"
    api_url = f"https://api.aiesec.org/graphql?access_token={token}"

    from core.models import SyncLog
    if sync_log_id:
        try:
            sync_log = SyncLog.objects.get(pk=sync_log_id)
        except SyncLog.DoesNotExist:
            sync_log = SyncLog.objects.create(status="running")
    else:
        sync_log = SyncLog.objects.create(status="running")

    created = 0
    skipped = 0
    page = 1
    per_page = 50

    try:
        while True:
            query = """
            query($page: Int, $perPage: Int) {
              allOpportunityApplication(page: $page, per_page: $perPage, sort: "-created_at") {
                data {
                  id
                  created_at
                  updated_at
                  status
                  person {
                    id
                    full_name
                    email
                    phone
                    home_lc { id name }
                    home_mc { id name }
                  }
                  opportunity {
                    id
                    title
                    programme { short_name_display }
                    host_lc { id name }
                  }
                  meta {
                    date_matched
                    date_approved
                    date_realized
                  }
                }
                paging {
                  total_pages
                  current_page
                  total_items
                }
              }
            }
            """
            payload = json.dumps({"query": query, "variables": {"page": page, "perPage": per_page}}).encode()
            req = Request(api_url, data=payload, headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=30)
            result = json.loads(resp.read())

            applications = result.get("data", {}).get("allOpportunityApplication", {})
            data = applications.get("data", [])
            paging = applications.get("paging", {})

            if not data:
                break

            for app in data:
                try:
                    person = app.get("person") or {}
                    email = (person.get("email") or "").strip()
                    full_name = (person.get("full_name") or "").strip()
                    phone = (person.get("phone") or "").strip()

                    if not full_name and not email:
                        skipped += 1
                        continue

                    programme_name = ""
                    if app.get("opportunity") and app["opportunity"].get("programme"):
                        programme_name = app["opportunity"]["programme"].get("short_name_display", "")

                    track = "GT"
                    if "teacher" in programme_name.lower() or "gte" in programme_name.lower():
                        track = "GTe"

                    expa_status = (app.get("status") or "").lower()
                    stage = _expa_status_to_stage(expa_status, app.get("meta", {}))

                    existing = None
                    if email:
                        existing = EP.objects.filter(email=email).first()

                    if existing:
                        if existing.source == "expa_sync":
                            existing.track = track
                            existing.current_stage = stage
                            existing.last_activity_at = timezone.now()
                            existing.save(update_fields=["track", "current_stage", "last_activity_at"])
                            skipped += 1
                        else:
                            skipped += 1
                    else:
                        home_lc_name = ""
                        if person.get("home_lc"):
                            home_lc_name = person["home_lc"].get("name", "")

                        EP.objects.create(
                            full_name=full_name or "Unknown EP",
                            email=email,
                            phone=phone,
                            track=track,
                            current_stage=stage,
                            term=config.current_term,
                            source="expa_sync",
                            university=home_lc_name,
                            last_edited_by=None,
                        )
                        created += 1

                except Exception:
                    skipped += 1

            page += 1
            if paging.get("total_pages") and page > paging["total_pages"]:
                break

        sync_log.status = "success"
        sync_log.created_count = created
        sync_log.skipped_count = skipped
        sync_log.finished_at = timezone.now()
        sync_log.save()

        return {"status": "success", "created": created, "skipped": skipped, "pages_fetched": page - 1}

    except Exception as exc:
        sync_log.status = "failed"
        sync_log.error_message = str(exc)[:500]
        sync_log.finished_at = timezone.now()
        sync_log.save()
        return {"status": "failed", "error": str(exc)}


def _expa_status_to_stage(expa_status, meta):
    """Map EXPA application status to our EP stage."""
    if meta.get("date_realized"):
        return "realized"
    if meta.get("date_approved"):
        return "approved"
    if meta.get("date_matched"):
        return "matched_with_opp"

    status_map = {
        "open": "open", "applied": "applied", "in_progress": "applied",
        "accepted": "accepted", "approved": "approved",
        "realized": "realized", "finished": "realized", "completed": "realized",
        "withdrawn": "open", "rejected": "open", "pending": "open",
        "matched": "matched_with_opp",
    }
    return status_map.get(expa_status, "open")


@shared_task
def check_stale_cases():
    """
    Daily check: find EPs exceeding per-stage idle thresholds.
    Uses stage-loop queries instead of per-EP loop — 9 queries max.
    """
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
