from django.contrib import admin

from .models import Member, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "tl", "member_count")
    search_fields = ("name",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "team", "has_password_badge", "is_active", "created_at")
    list_filter = ("role", "team", "is_active")
    search_fields = ("name", "email", "phone")
    fieldsets = (
        ("Identity", {"fields": ("name", "role", "team", "is_active")}),
        ("Contact", {"fields": ("phone", "email")}),
        ("Password", {"fields": ("password_raw",), "description": "Leave blank to keep the current password. Sets a new password for this member."}),
    )

    def has_password_badge(self, obj):
        return "Locked" if obj.has_password else "Open"
    has_password_badge.short_description = "Password"

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        from django import forms
        form.base_fields["password_raw"] = forms.CharField(
            label="New password",
            required=False,
            widget=forms.PasswordInput(attrs={"placeholder": "Leave blank to keep current"}),
            help_text="Leave blank to keep the existing password.",
        )
        return form

    def save_model(self, request, obj, form, change):
        raw = form.cleaned_data.get("password_raw", "")
        if raw:
            obj.set_password(raw)
        super().save_model(request, obj, form, change)
