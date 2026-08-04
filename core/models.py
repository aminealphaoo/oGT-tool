from django.db import models


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
