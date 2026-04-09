from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    name = 'academics'

    def ready(self):
        from .audit_trail import register_signals

        register_signals()
