from .settings import *  # noqa: F403


STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    }
}
MIDDLEWARE = [
    item for item in MIDDLEWARE  # noqa: F405
    if item != "whitenoise.middleware.WhiteNoiseMiddleware"
]

# Tests laufen ohne Zugriff auf externe Hosts (siehe core/test_runner.py).
TEST_RUNNER = "core.test_runner.HermeticDiscoverRunner"
