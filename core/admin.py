from django.contrib import admin

from .models import DashboardStats, SiteConfig, SyncLog


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = [
        ("LC Info", {"fields": ["lc_name", "current_term", "contact_email"]}),
        ("EXPA Integration", {"fields": ["expa_access_token"]}),
        ("Stale Thresholds", {"fields": ["stage_idle_thresholds"]}),
    ]


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("started_at", "status", "created_count", "skipped_count", "finished_at")
    list_filter = ("status",)
    readonly_fields = ("started_at", "finished_at", "created_count", "skipped_count", "error_message")


@admin.register(DashboardStats)
class DashboardStatsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Overall", {"fields": ("total_eps",)}),
        ("EXPA Phases", {"fields": ("expa_applied", "expa_accepted", "expa_approved", "expa_realized", "expa_finished")}),
        ("Funnel Stages", {"fields": ("stage_open", "stage_matched", "stage_applied", "stage_accepted", "stage_approved", "stage_papers", "stage_realized")}),
        ("Stats", {"fields": ("problem_cases", "stale_cases", "pipeline_value", "realized_last_30", "ir_partners", "open_opps", "interactions_period")}),
        ("Meta", {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)
    list_display = ("__str__", "total_eps", "stage_realized", "updated_at")
