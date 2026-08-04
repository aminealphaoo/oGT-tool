from django.contrib import admin

from .models import SiteConfig, SyncLog


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
