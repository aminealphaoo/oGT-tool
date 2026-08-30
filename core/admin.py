from django.contrib import admin
from .models import SiteConfig, EmailTemplate, AuditLog, Notification


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = [
        ("LC Info", {"fields": ["lc_name", "current_term", "contact_email"]}),
        ("Matching Configuration", {"fields": ["matching_weights"]}),
        ("Stale Thresholds", {"fields": ["stage_idle_thresholds"]}),
    ]


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "track", "is_active")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "model_name", "object_id", "user", "timestamp")
    readonly_fields = ("timestamp",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "is_read", "created_at")
