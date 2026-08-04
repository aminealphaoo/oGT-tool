"""Signal handlers — trigger emails on EP stage changes."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from ops.models import StageHistory

from .models import EmailLog, EmailTemplate


@receiver(post_save, sender=StageHistory)
def trigger_stage_email(sender, instance, created, **kwargs):
    """When a StageHistory is created, find matching EmailTemplates and dispatch send tasks."""
    if not created:
        return

    templates = EmailTemplate.objects.filter(
        trigger_stage=instance.stage,
        is_active=True,
    )

    if not templates.exists():
        return

    from .tasks import send_stage_email

    for template in templates:
        # Log first with pending status
        log = EmailLog.objects.create(
            ep=instance.ep,
            template=template,
            subject=template.subject,
            body=template.body,
            status="pending",
        )
        # Dispatch Celery task to actually send
        send_stage_email.delay(log.pk)
