from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Keep the already large core/models.py stable while registering
        # additional domains as normal models of the same Django app.
        from . import privacy_models  # noqa: F401
        from . import wachalltag_models  # noqa: F401
        from . import mpg_models  # noqa: F401
        from . import warehouse_models  # noqa: F401
        from . import fleet_models  # noqa: F401
        from . import orga_models  # noqa: F401
        from . import notification_models  # noqa: F401
        from . import image_privacy  # noqa: F401
        from . import checks  # noqa: F401
        from . import auth_session  # noqa: F401

        from django.db.models import fields

        from .i18n import BLANK_CHOICE_LABEL

        fields.BLANK_CHOICE_LABEL = BLANK_CHOICE_LABEL
