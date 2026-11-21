from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Shared pieces: template tags for the design system and the temporary home page."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
