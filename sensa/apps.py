from django.apps import AppConfig


class SensaConfig(AppConfig):
    name = "sensa"

    def ready(self):
        from . import signals  # noqa: F401
