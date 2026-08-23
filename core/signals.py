import json
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import models
from django.forms.models import model_to_dict
from .models import AuditLog, Notification
from ops.models import EP, Task
from partners.models import IR, Opportunity
from django.contrib.auth.models import User

# Thread-local storage to capture the current request user and IP address
import threading
_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_ip():
    return getattr(_thread_locals, 'ip_address', None)


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        # Capture IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        _thread_locals.ip_address = ip
        
        response = self.get_response(request)
        
        # Clean up thread local
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user
        if hasattr(_thread_locals, 'ip_address'):
            del _thread_locals.ip_address
            
        return response


# Track old values in pre_save
@receiver(pre_save, sender=EP)
@receiver(pre_save, sender=IR)
@receiver(pre_save, sender=Opportunity)
@receiver(pre_save, sender=Task)
def pre_save_audit(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_inst = sender.objects.get(pk=instance.pk)
            instance._old_values = model_to_dict(old_inst)
        except sender.DoesNotExist:
            instance._old_values = {}
    else:
        instance._old_values = {}


@receiver(post_save, sender=EP)
@receiver(post_save, sender=IR)
@receiver(post_save, sender=Opportunity)
@receiver(post_save, sender=Task)
def post_save_audit(sender, instance, created, **kwargs):
    user = get_current_user()
    if user and not user.is_authenticated:
        user = None
        
    action = "CREATE" if created else "UPDATE"
    
    # Custom match action detection
    if sender == EP and not created:
        old_opp = (instance._old_values.get("matched_opportunity") if hasattr(instance, "_old_values") else None)
        if instance.matched_opportunity_id and instance.matched_opportunity_id != old_opp:
            action = "MATCH"
            
    old_vals = getattr(instance, "_old_values", {})
    new_vals = model_to_dict(instance)
    
    # Serialize JSON safely
    def clean_dict(d):
        cleaned = {}
        for k, v in d.items():
            try:
                json.dumps(v)
                cleaned[k] = v
            except TypeError:
                cleaned[k] = str(v)
        return cleaned

    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=sender.__name__,
        object_id=str(instance.pk),
        old_values=clean_dict(old_vals),
        new_values=clean_dict(new_vals),
        ip_address=get_current_ip()
    )


@receiver(post_delete, sender=EP)
@receiver(post_delete, sender=IR)
@receiver(post_delete, sender=Opportunity)
@receiver(post_delete, sender=Task)
def post_delete_audit(sender, instance, **kwargs):
    user = get_current_user()
    if user and not user.is_authenticated:
        user = None

    AuditLog.objects.create(
        user=user,
        action="DELETE",
        model_name=sender.__name__,
        object_id=str(instance.pk),
        old_values=model_to_dict(instance),
        new_values={},
        ip_address=get_current_ip()
    )
