import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aiesec_tool.settings")

app = Celery("aiesec_tool")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
