"""Templates müssen mit der CSP ohne 'unsafe-inline' funktionieren.

Der Browser blockiert unter ``script-src 'self'; style-src 'self'`` jedes
Inline-Skript, jeden Inline-Handler (onclick=…) und jedes style-Attribut.
Solche Konstrukte sehen im Django-Testclient harmlos aus, sind im Browser aber
wirkungslos (Modals öffnen nicht, Layout fehlt). Verhalten gehört in
``core/static/core/ui.js`` (data-Attribute), Gestaltung in die CSS-Dateien.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"

INLINE_HANDLER = re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE)
STYLE_ATTRIBUTE = re.compile(r"<[^>]*\sstyle\s*=", re.IGNORECASE)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)(?![^>]*type=\"application/json\")[^>]*>", re.IGNORECASE)


def _templates():
    return sorted(TEMPLATE_ROOT.rglob("*.html"))


class TemplateCspComplianceTests(SimpleTestCase):
    def _offenders(self, pattern):
        found = []
        for path in _templates():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    found.append(f"{path.relative_to(TEMPLATE_ROOT)}:{number}")
        return found

    def test_no_inline_event_handlers(self):
        self.assertEqual(self._offenders(INLINE_HANDLER), [])

    def test_no_style_attributes(self):
        self.assertEqual(self._offenders(STYLE_ATTRIBUTE), [])

    def test_no_inline_scripts(self):
        self.assertEqual(self._offenders(INLINE_SCRIPT), [])


class CameraPermissionPolicyTests(TestCase):
    def setUp(self):
        from core.models import Membership, Station, User

        self.station = Station.objects.create(name="Wache CSP", slug="wache-csp")
        self.user = User.objects.create_user("csp-admin", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def test_camera_only_on_scanner_pages(self):
        scanner = self.client.get(reverse("mpg_dashboard"))
        self.assertEqual(scanner.status_code, 200)
        self.assertIn("camera=(self)", scanner["Permissions-Policy"])
        other = self.client.get(reverse("more"))
        self.assertIn("camera=()", other["Permissions-Policy"])

    def test_more_page_has_no_leaking_html_comments(self):
        html = self.client.get(reverse("more")).content.decode()
        self.assertNotIn("<!--", html)
