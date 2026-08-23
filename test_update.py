import os, sys, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aiesec_tool.settings')
import django
django.setup()
from ops.models import EP
from django.utils import timezone

ep = EP.objects.first()
print(f'EP: id={ep.id}, name={ep.full_name}')
ep.track = 'GTe'
ep.last_activity_at = timezone.now()
print('Saving with update_fields...')
ep.save(update_fields=['track', 'last_activity_at'])
print('SAVED OK!')
