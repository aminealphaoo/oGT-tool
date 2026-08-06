# AIESEC LC Carthage — EP/IR Centralization Tool
# Ensure Celery app is loaded when Django starts, enabling task autodiscovery.
from .celery import app as celery_app

__all__ = ("celery_app",)
