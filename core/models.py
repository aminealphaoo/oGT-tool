from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User



class SiteConfig(models.Model):
    """Singleton configuration — one row for the entire LC instance."""

    lc_name = models.CharField(max_length=200, default="AIESEC LC Carthage")
    current_term = models.CharField(max_length=20, default="2026-S1")
    contact_email = models.EmailField(blank=True, default="")
    matching_weights = models.JSONField(
        default=dict,
        help_text='{"skills": 30, "languages": 20, "study_field": 15, "preferred_countries": 25, "semantic": 20, "duration": 10, "availability": 10, "tier": 40, "open_slots": 20, "rejection_rate": -1, "response_time": 10}',
    )
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

    def get_weight(self, key: str) -> int:
        """Return weight for a matching criterion."""
        defaults = {
            "skills": 30,
            "languages": 20,
            "study_field": 15,
            "preferred_countries": 25,
            "semantic": 20,
            "duration": 10,
            "availability": 10,
            "tier": 40,
            "open_slots": 20,
            "rejection_rate": -1,
            "response_time": 10,
        }
        weights = self.matching_weights or {}
        return weights.get(key, defaults.get(key, 0))


class DashboardStats(models.Model):
    """
    Admin-controlled dashboard counters.
    The admin sets these values manually from the admin panel
    and they are displayed in the member dashboard.
    """
    config = models.OneToOneField(SiteConfig, on_delete=models.CASCADE, primary_key=True, related_name="dashboard_stats")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last time stats were updated")

    # ── Overall ──
    total_eps = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Total EPs")

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
    def funnel_counts(self):
        return [
            self.stage_open, self.stage_matched, self.stage_applied,
            self.stage_accepted, self.stage_approved, self.stage_papers,
            self.stage_realized,
        ]


class EmailTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Utilisez {{ep.first_name}}, {{partner.name}}, etc.")
    variables = models.JSONField(default=list, help_text="Liste des variables disponibles")
    track = models.CharField(max_length=20, choices=[('GT','Global Talent'),('GTe','Global Teacher'),('All','Tous')], default='All')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)  # CREATE, UPDATE, DELETE, MATCH
    model_name = models.CharField(max_length=50)
    object_id = models.CharField(max_length=100)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.action} on {self.model_name} ({self.object_id}) at {self.timestamp}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"

