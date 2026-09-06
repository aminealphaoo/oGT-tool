from django.apps import AppConfig


class OpsConfig(AppConfig):
    name = "ops"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import ops.signals  # noqa: F401
