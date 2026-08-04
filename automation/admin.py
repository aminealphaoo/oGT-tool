from django.contrib import admin

from .models import EmailLog, EmailTemplate


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "trigger_stage", "is_active", "created_at")
    list_filter = ("trigger_stage", "is_active")
    search_fields = ("name", "subject")


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("ep", "template", "subject", "status", "sent_at")
    list_filter = ("status", "sent_at")
    search_fields = ("ep__full_name", "subject")
    readonly_fields = ("sent_at",)
