# AIESEC LC Carthage — EP/IR Centralization Tool
# Celery is optional (USE_CELERY=True). Render free tier runs without Redis.
import os

celery_app = None
if os.environ.get("USE_CELERY", "False") == "True":
    from .celery import app as celery_app

__all__ = ("celery_app",)
