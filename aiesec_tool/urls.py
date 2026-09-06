"""
URL configuration for aiesec_tool.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from ops.urls_eps import (
    matching_patterns, problems_patterns, tasks_patterns,
    notifications_patterns, audit_patterns,
    match_lab_patterns, cxp_patterns, brand_patterns,
)

from core.api_whatsapp import WhatsAppWebhookView
from core.api import api_eps, api_health, api_irs, api_stats
from core.views import cron_runner, ping

urlpatterns = [
    path("admin/", admin.site.urls),
    path("public/", include("ops.urls_public")),
    path("ping/", ping, name="ping"),
    path("", include("dashboard.urls")),
    path("members/", include("members.urls")),
    path("eps/", include("ops.urls_eps")),
    path("irs/", include("partners.urls")),
    path("problems/", include(problems_patterns)),
    path("matching/", include(matching_patterns)),
    path("tasks/", include(tasks_patterns)),
    path("notifications/", include(notifications_patterns)),
    path("audit/", include(audit_patterns)),
    path("match-lab/", include(match_lab_patterns)),
    path("cxp/", include(cxp_patterns)),
    path("brand/", include(brand_patterns)),
    # API endpoints (no login — cron routes are secret-protected)
    path("api/cron/<str:task_name>/", cron_runner, name="cron_runner"),
    path("api/health/", api_health, name="api_health"),
    path("api/eps/", api_eps, name="api_eps"),
    path("api/irs/", api_irs, name="api_irs"),
    path("api/stats/", api_stats, name="api_stats"),
    path("api/whatsapp/webhook/", WhatsAppWebhookView.as_view(), name="whatsapp_webhook"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
