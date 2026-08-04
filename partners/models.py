from django.db import models

from members.models import Member


class IR(models.Model):
    """Incoming Realization partner entity."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"
        PRIORITY = "priority", "Priority"

    class Tier(models.TextChoices):
        BRONZE = "bronze", "Bronze"
        SILVER = "silver", "Silver"
        GOLD = "gold", "Gold"
        PLATINUM = "platinum", "Platinum"

    entity_name = models.CharField(max_length=200)
    country = models.CharField(max_length=100)

    # ── Lifecycle ──────────────────────────────────────────────────────
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    tier = models.CharField(max_length=15, choices=Tier.choices, default=Tier.BRONZE, db_index=True)
    contract_start = models.DateField(null=True, blank=True, help_text="Partnership contract start date")
    contract_end = models.DateField(null=True, blank=True, help_text="Partnership contract end date")

    # ── Links ─────────────────────────────────────────────────────────
    testimonials_link = models.URLField(blank=True, default="")
    opportunities_page_link = models.URLField(blank=True, default="")
    whatsapp_group_link = models.URLField(blank=True, default="")

    # ── Contact ───────────────────────────────────────────────────────
    vp_contact = models.CharField(max_length=200, blank=True, default="", help_text="Name / role / phone of VP contact")

    # ── Assignment ────────────────────────────────────────────────────
    assigned_to = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_irs",
        help_text="IR member responsible",
    )

    # ── Metadata ──────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    last_edited_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_irs",
    )
    last_edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country", "entity_name"]
        verbose_name = "IR Partner"
        verbose_name_plural = "IR Partners"
        constraints = [
            models.UniqueConstraint(
                fields=["entity_name", "country"],
                name="unique_ir_entity_country",
            )
        ]

    def __str__(self):
        return f"{self.entity_name} ({self.country})"

    # ── Computed performance ──────────────────────────────────────────
    @property
    def approved_count(self) -> int:
        """Number of EPs matched to this IR's opportunities who are at 'approved' or beyond."""
        from ops.models import EP

        opp_ids = self.opportunities.values_list("id", flat=True)
        return EP.objects.filter(
            matched_opportunity_id__in=opp_ids,
            current_stage__in=["approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"],
        ).count()

    @property
    def realized_count(self) -> int:
        """Number of EPs realized through this IR."""
        from ops.models import EP

        opp_ids = self.opportunities.values_list("id", flat=True)
        return EP.objects.filter(
            matched_opportunity_id__in=opp_ids,
            current_stage="realized",
        ).count()

    @property
    def total_matched(self) -> int:
        from ops.models import EP

        opp_ids = self.opportunities.values_list("id", flat=True)
        return EP.objects.filter(matched_opportunity_id__in=opp_ids).count()

    @property
    def rejection_rate(self) -> float:
        """Approximate rejection rate: (applied but not accepted) / total applied."""
        from ops.models import EP

        opp_ids = self.opportunities.values_list("id", flat=True)
        total = EP.objects.filter(matched_opportunity_id__in=opp_ids).count()
        if total == 0:
            return 0.0
        # Count EPs that went through this IR that ended up not accepted
        rejected = EP.objects.filter(
            matched_opportunity_id__in=opp_ids,
        ).exclude(
            current_stage__in=["accepted", "approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"],
        ).count()
        return round(rejected / total * 100, 1)

    @property
    def open_opportunities_count(self) -> int:
        return self.opportunities.filter(is_open=True).count()

    @property
    def response_time_days(self) -> float | None:
        """Average days from 'matched_with_opp' to 'applied' for this IR's EPs."""
        from ops.models import EP, StageHistory

        opp_ids = self.opportunities.values_list("id", flat=True)
        eps = EP.objects.filter(matched_opportunity_id__in=opp_ids)

        total_days = 0
        count = 0
        for ep in eps:
            matched = StageHistory.objects.filter(
                ep=ep, stage="matched_with_opp"
            ).order_by("changed_at").first()
            applied = StageHistory.objects.filter(
                ep=ep, stage__in=["applied", "accepted", "approved"]
            ).order_by("changed_at").first()
            if matched and applied and applied.changed_at > matched.changed_at:
                total_days += (applied.changed_at - matched.changed_at).days
                count += 1

        return round(total_days / count, 1) if count > 0 else None


class Opportunity(models.Model):
    """An open position/track offered by an IR partner."""

    class OppType(models.TextChoices):
        TEACHING = "teaching", "Teaching"
        IT = "it", "IT"
        MARKETING = "marketing", "Marketing"
        BUSINESS = "business", "Business"
        ENGINEERING = "engineering", "Engineering"
        OTHER = "other", "Other"

    ir = models.ForeignKey(IR, on_delete=models.CASCADE, related_name="opportunities")
    title = models.CharField(max_length=200, blank=True, default="")
    type = models.CharField(max_length=20, choices=OppType.choices, default=OppType.OTHER)
    description = models.TextField(blank=True, default="")
    is_open = models.BooleanField(default=True)
    expires_at = models.DateField(null=True, blank=True)
    track = models.CharField(
        max_length=5,
        choices=[("GT", "Global Talent"), ("GTe", "Global Teacher")],
        default="GT",
        help_text="Which AIESEC track this opportunity aligns with",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_open", "-created_at"]
        verbose_name_plural = "Opportunities"

    def __str__(self):
        return f"{self.ir.entity_name} — {self.get_type_display()}" + (
            " [OPEN]" if self.is_open else " [CLOSED]"
        )
