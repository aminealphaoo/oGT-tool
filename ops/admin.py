from django.contrib import admin

from .models import Attachment, EP, Interaction, StageHistory


class StageHistoryInline(admin.TabularInline):
    model = StageHistory
    extra = 0
    readonly_fields = ("changed_at",)


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(EP)
class EPAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "track",
        "current_stage",
        "problem_flag",
        "assigned_to",
        "term",
        "last_activity_at",
    )
    list_filter = ("track", "current_stage", "problem_flag", "term", "source")
    search_fields = ("full_name", "phone", "email", "university")
    inlines = [StageHistoryInline, InteractionInline, AttachmentInline]
    readonly_fields = ("last_activity_at", "last_edited_at", "created_at")


@admin.register(StageHistory)
class StageHistoryAdmin(admin.ModelAdmin):
    list_display = ("ep", "stage", "previous_stage", "changed_by", "changed_at")
    list_filter = ("stage", "changed_at")


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ("ep", "author", "date")
    list_filter = ("date",)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("ep", "label", "uploaded_at")
    list_filter = ("label",)
