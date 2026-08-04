from django.contrib import admin

from .models import IR, Opportunity


class OpportunityInline(admin.TabularInline):
    model = Opportunity
    extra = 0


@admin.register(IR)
class IRAdmin(admin.ModelAdmin):
    list_display = (
        "entity_name",
        "country",
        "assigned_to",
        "realized_count",
        "open_opportunities_count",
    )
    list_filter = ("country",)
    search_fields = ("entity_name", "country", "vp_contact")
    inlines = [OpportunityInline]


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("__str__", "ir", "type", "is_open", "track", "expires_at")
    list_filter = ("type", "is_open", "track")
    search_fields = ("ir__entity_name", "title")
