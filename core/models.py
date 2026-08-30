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




class EmailTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Utilisez {{ep.first_name}}, {{partner.name}}, etc.")
    variables = models.JSONField(default=list, help_text="Liste des variables disponibles")
    track = models.CharField(max_length=20, choices=[('GTa','Global Talent'),('GTe','Global Teacher'),('All','Tous')], default='All')
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

