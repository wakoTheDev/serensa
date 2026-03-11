from django.apps import AppConfig


class SensaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sensa"

    def ready(self):
        from . import signals  # noqa: F401
