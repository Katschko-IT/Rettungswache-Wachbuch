"""Regressionstests für den Installationshinweis.

Der Hinweis darf nur eingeblendet werden, wenn der Browser ihn anbietet, und
muss sich dauerhaft schließen lassen. Zusätzlich darf das hidden-Attribut nicht
durch eine Layout-Regel überstimmt werden – genau das machte das Banner zuvor
unschließbar sichtbar.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Membership, Station


class InstallBannerTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Banner", slug="banner")
        self.user = User.objects.create_user("banner-user", password="Banner-Test-12345")
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.MEMBER
        )

    def test_banner_is_rendered_hidden(self):
        self.client.force_login(self.user)
        response = self.client.get("/uebergaben/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-install-banner hidden", html)

    def test_stylesheet_enforces_hidden_attribute(self):
        css = (Path(settings.BASE_DIR) / "core/static/core/app.css").read_text(encoding="utf-8")
        self.assertIn("[hidden] { display: none !important; }", css)

    def test_dismiss_is_respected_by_javascript(self):
        js = (Path(settings.BASE_DIR) / "core/static/core/app.js").read_text(encoding="utf-8")
        # Vor dem Einblenden muss der gespeicherte Wunsch geprüft werden.
        self.assertIn("rwsth-install-dismissed", js)
        self.assertIn("!installDismissed()", js)
