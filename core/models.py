from django.db import models
from django.core.validators import MinValueValidator


class SiteConfig(models.Model):
    """Singleton configuration — one row for the entire LC instance."""

    lc_name = models.CharField(max_length=200, default="AIESEC LC Carthage")
    current_term = models.CharField(max_length=20, default="2026-S1")
    contact_email = models.EmailField(blank=True, default="")
    expa_access_token = models.CharField(max_length=200, blank=True, default="", help_text="Token from auth.aiesec.org/developers/applications")

    # Stale thresholds (days) — JSON for flexibility
    stage_idle_thresholds = models.JSONField(
        default=dict,
        help_text='{"open": 14, "matched_with_opp": 7, ...}',
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return f"{self.lc_name} — {self.current_term}"

    @classmethod
    def get(cls):
        """Return the singleton config row, creating it if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_threshold(self, stage: str) -> int:
        """Return idle threshold in days for a given stage."""
        defaults = {
            "open": 14,
            "matched_with_opp": 7,
            "applied": 7,
            "accepted": 14,
            "approved": 14,
            "all_papers_done": 7,
            "not_all_papers_done": 7,
            "do_papers": 14,
        }
        thresholds = self.stage_idle_thresholds or {}
        return thresholds.get(stage, defaults.get(stage, 14))


class DashboardStats(models.Model):
    """
    Admin-controlled dashboard counters.
    The admin sets these values manually from the admin panel
    and they are displayed in the member dashboard.
    Each stat tracks a count; the dashboard shows this snapshot.
    """
    config = models.OneToOneField(SiteConfig, on_delete=models.CASCADE, primary_key=True, related_name="dashboard_stats")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last time stats were updated")

    # ── Overall ──
    total_eps = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Total EPs")

    # ── EXPA phases ──
    expa_applied = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="EXPA Applied")
    expa_accepted = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="EXPA Accepted")
    expa_approved = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="EXPA Approved")
    expa_realized = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="EXPA Realized")
    expa_finished = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="EXPA Finished / Completed")

    # ── Internal funnel stages ──
    stage_open = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Open")
    stage_matched = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Matched with Opp")
    stage_applied = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Applied")
    stage_accepted = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Accepted")
    stage_approved = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Approved")
    stage_papers = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Papers")
    stage_realized = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stage: Realized")

    # ── Other ──
    problem_cases = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Problem Cases")
    stale_cases = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Stale Cases")
    pipeline_value = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="EPs in Pipeline")
    realized_last_30 = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Realized (last 30 days)")
    ir_partners = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="IR Partners")
    open_opps = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Open Opportunities")
    interactions_period = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Interactions this period")

    class Meta:
        verbose_name = "Dashboard Stats"
        verbose_name_plural = "Dashboard Stats"

    def __str__(self):
        return f"Dashboard Stats ({self.updated_at:%Y-%m-%d %H:%M})"

    @classmethod
    def for_config(cls, config):
        obj, _ = cls.objects.get_or_create(config=config)
        return obj

    @property
    def expa_stats(self):
        return {
            "applied": self.expa_applied,
            "accepted": self.expa_accepted,
            "approved": self.expa_approved,
            "realized": self.expa_realized,
            "finished": self.expa_finished,
        }

    @property
    def funnel_counts(self):
        return [
            self.stage_open, self.stage_matched, self.stage_applied,
            self.stage_accepted, self.stage_approved, self.stage_papers,
            self.stage_realized,
        ]


class SyncLog(models.Model):
    """Track EXPA sync runs."""

    class SyncStatus(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=SyncStatus.choices, default=SyncStatus.RUNNING)
    created_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sync {self.started_at:%Y-%m-%d %H:%M} — {self.get_status_display()} (+{self.created_count})"
