import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aiesec_tool.settings")

USE_CELERY = os.environ.get("USE_CELERY", "False") == "True"

if USE_CELERY:
    from celery import Celery

    app = Celery("aiesec_tool")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
else:
    # Placeholder so `from aiesec_tool.celery import app` never crashes.
    app = None
