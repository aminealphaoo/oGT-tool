from django.db import models

from ops.models import EP


class EmailTemplate(models.Model):
    """Email template that auto-fires when an EP reaches a specific stage."""

    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=300)
    body = models.TextField(
        help_text="Use {{ep.full_name}}, {{ep.track}}, {{ep.current_stage}}, {{lc_name}} as placeholders."
    )
    trigger_stage = models.CharField(
        max_length=30,
        choices=EP.Stage.choices,
        help_text="Email is sent automatically when an EP enters this stage.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["trigger_stage", "name"]

    def __str__(self):
        return f"{self.name} → {self.get_trigger_stage_display()}"

    def render(self, ep: EP, lc_name: str = "AIESEC LC Carthage") -> dict:
        """Render subject and body with EP context."""
        ctx = {
            "ep": ep,
            "lc_name": lc_name,
        }
        subject = self.subject
        body = self.body
        for key, val in ctx.items():
            if hasattr(val, "__getitem__"):
                pass  # skip nested
            subject = subject.replace(f"{{{{{key}}}}}", str(val))
            body = body.replace(f"{{{{{key}}}}}", str(val))
        # Also support ep.field placeholders
        subject = subject.replace("{{ep.full_name}}", ep.full_name)
        subject = subject.replace("{{ep.track}}", ep.get_track_display())
        subject = subject.replace("{{ep.current_stage}}", ep.get_current_stage_display())
        body = body.replace("{{ep.full_name}}", ep.full_name)
        body = body.replace("{{ep.track}}", ep.get_track_display())
        body = body.replace("{{ep.current_stage}}", ep.get_current_stage_display())
        body = body.replace("{{lc_name}}", lc_name)
        return {"subject": subject, "body": body}


class EmailLog(models.Model):
    """Record of a triggered email sent to an EP."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    ep = models.ForeignKey(EP, on_delete=models.CASCADE, related_name="email_logs")
    template = models.ForeignKey(
        EmailTemplate, on_delete=models.SET_NULL, null=True, related_name="logs"
    )
    subject = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Email to {self.ep.full_name}: {self.subject} [{self.get_status_display()}]"
