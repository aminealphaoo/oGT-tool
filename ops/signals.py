"""EP signals — queue / send stage emails without Celery on Render."""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from ops.models import EP


@receiver(pre_save, sender=EP)
def remember_ep_stage(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_stage = None
        return
    try:
        instance._previous_stage = (
            sender.objects.filter(pk=instance.pk)
            .values_list("current_stage", flat=True)
            .get()
        )
    except sender.DoesNotExist:
        instance._previous_stage = None


@receiver(post_save, sender=EP)
def send_emails_on_stage_change(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_stage", None)
    stage_changed = created or previous != instance.current_stage
    if not stage_changed:
        return

    from automation.tasks import queue_stage_emails_for_ep

    queue_stage_emails_for_ep(instance, stage=instance.current_stage)
