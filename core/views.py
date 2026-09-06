"""HTTP cron + keep-alive views for Render free tier (cron-job.org)."""
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def _cron_secret_ok(request) -> bool:
    expected = getattr(settings, "CRON_SECRET", "") or ""
    provided = (
        request.headers.get("X-Cron-Secret")
        or request.META.get("HTTP_X_CRON_SECRET")
        or request.GET.get("secret")
        or ""
    )
    return bool(expected) and provided == expected


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
def ping(request):
    """Keep-alive for Render free-tier spin-down. No auth."""
    return JsonResponse({"status": "awake"})


@csrf_exempt
@require_http_methods(["GET", "POST", "HEAD"])
def cron_runner(request, task_name: str):
    """
    cron-job.org entrypoint.

    - ping: no secret (keep-alive)
    - stale / digest / stage_emails: header X-Cron-Secret (or ?secret=)
    """
    task_name = (task_name or "").strip().lower()

    if task_name == "ping":
        return JsonResponse({"status": "awake"})

    if not _cron_secret_ok(request):
        return JsonResponse({"status": "error", "message": "Forbidden"}, status=403)

    try:
        if task_name == "stale":
            from automation.tasks import check_stale_cases

            result = check_stale_cases()
            return JsonResponse({"status": "ok", "task": task_name, "result": result})

        if task_name == "digest":
            from automation.tasks import send_weekly_digest

            result = send_weekly_digest()
            return JsonResponse({"status": "ok", "task": task_name, "result": result})

        if task_name == "stage_emails":
            from automation.tasks import send_pending_stage_emails

            result = send_pending_stage_emails()
            return JsonResponse({"status": "ok", "task": task_name, "result": result})
    except Exception as exc:
        return JsonResponse(
            {"status": "error", "task": task_name, "message": str(exc)},
            status=500,
        )

    return JsonResponse(
        {
            "status": "error",
            "message": f"Unknown task '{task_name}'",
            "allowed": ["ping", "stale", "digest", "stage_emails"],
        },
        status=400,
    )
