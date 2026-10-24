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

    def test_regular_pages_do_not_start_the_display_feed(self):
        # Ein verstecktes Display-Overlay hat auf jeder Seite Display-Daten
        # geladen und einen SSE-Stream (einen Server-Thread) geöffnet.
        html = self.client.get(reverse("more")).content.decode()
        self.assertNotIn("display.js", html)
        self.assertNotIn(reverse("display_data"), html)

    def test_more_page_has_no_leaking_html_comments(self):
        html = self.client.get(reverse("more")).content.decode()
        self.assertNotIn("<!--", html)


class DashboardModuleCardsTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.fleet_models import Vehicle
        from core.models import Membership, Station, User
        from core.mpg_models import MedicalDevice

        self.station = Station.objects.create(name="Wache Lage", slug="wache-lage")
        self.user = User.objects.create_user("lage-admin", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        Vehicle.objects.create(
            station=self.station, slug="rtw-x", call_sign="RTW X", license_plate="X-1",
            tactical_status=Vehicle.TacticalStatus.WORKSHOP,
        )
        MedicalDevice.objects.create(
            station=self.station, slug="defi-x", name="Defi X",
            next_stk_date=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(self.user)

    def _attention(self):
        response = self.client.get(reverse("dashboard"))
        return {item["key"]: item for item in response.context["attention_items"]}, response.content.decode()

    def test_dashboard_shows_module_attention(self):
        items, html = self._attention()
        self.assertEqual((items["fleet"]["value"], items["fleet"]["title"]), (1, "Fahrzeug"))
        self.assertEqual((items["mpg"]["value"], items["mpg"]["title"]), (1, "Medizingerät"))
        self.assertIn(reverse("mpg_dashboard") + "?filter=urgent", html)

    def test_disabled_module_has_no_card(self):
        self.station.fleet_enabled = False
        self.station.save(update_fields=["fleet_enabled"])
        items, _html = self._attention()
        self.assertNotIn("fleet", items)


class FormAndRoleRegressionTests(TestCase):
    def setUp(self):
        from datetime import date

        from core.fleet_models import Vehicle
        from core.models import Membership, Station, User

        self.station = Station.objects.create(name="Wache Form", slug="wache-form")
        self.admin = User.objects.create_user("form-admin", password="pw-123456789")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.auditor = User.objects.create_user("form-audit", password="pw-123456789")
        Membership.objects.create(user=self.auditor, station=self.station, role=Membership.Role.AUDITOR)
        Vehicle.objects.create(
            station=self.station, slug="rtw-f", call_sign="RTW F", license_plate="F-1",
            next_hu_date=date(2027, 3, 9),
        )

    def test_edit_form_keeps_dates_in_iso_format(self):
        # type="date" akzeptiert nur JJJJ-MM-TT; ein lokalisierter Wert
        # erscheint leer und würde beim Speichern die Frist löschen.
        self.client.force_login(self.admin)
        html = self.client.get(reverse("fleet_vehicle_edit", args=["rtw-f"])).content.decode()
        self.assertIn('value="2027-03-09"', html)

    def test_vehicle_detail_has_unique_field_ids(self):
        import re

        self.client.force_login(self.admin)
        html = self.client.get(reverse("fleet_vehicle_detail", args=["rtw-f"])).content.decode()
        ids = re.findall(r'\sid="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)), sorted({i for i in ids if ids.count(i) > 1}))

    def test_auditor_more_page_only_links_reachable_areas(self):
        self.client.force_login(self.auditor)
        html = self.client.get(reverse("more")).content.decode()
        self.assertNotIn(reverse("fleet_dashboard"), html)
        self.assertNotIn(reverse("coffee"), html)
        self.assertIn(reverse("audit_log"), html)

    def test_auditor_account_page_has_no_forbidden_links(self):
        self.client.force_login(self.auditor)
        html = self.client.get(reverse("account_home")).content.decode()
        self.assertNotIn(reverse("chat"), html)
        self.assertNotIn(reverse("birthday_settings"), html)
