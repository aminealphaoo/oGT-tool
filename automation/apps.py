from django.apps import AppConfig


class AutomationConfig(AppConfig):
    name = 'automation'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """Import signal handlers so stage-change emails are dispatched."""
        import automation.signals  # noqa: F401
