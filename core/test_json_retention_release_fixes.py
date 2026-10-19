"""Fokus-Tests fuer die Release-Fixes F3 (Retention) und F4 (JS-Sprachkatalog).

F3: Diagnoseansicht und Supportexport muessen exakt dieselbe
Aufbewahrungsrichtlinie anwenden (Default 30 Tage / 200 Eintraege), inklusive
Stationsgrenze und Pagination.

F4: Der JS-Sprachkatalog wird als Django-``json_script`` ausgeliefert, damit
Anfuehrungszeichen, Backslashes, Zeilenumbrueche und ``</script>`` nicht aus dem
JSON ausbrechen koennen. Die 50 Schluessel und msgids bleiben identisch.
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from core.diagnostics_models import ErrorEvent
from core.models import Membership, Station
from core.templatetags.js_i18n import js_i18n_data
from scripts.i18n_catalog import extract_python, parse_po

WB_T_CALL_RE = re.compile(r"wbT\(\s*\"(?P<key>[a-z0-9_]+)\"")
JSON_SCRIPT_RE = re.compile(
    r'<script id="js-i18n" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)
EXECUTABLE_SCRIPT_RE = re.compile(r"<script(?![^>]*type=\"application/json\")")
_STATION_DEFAULT = object()


def _rendered_script() -> tuple[str, dict]:
    html = render_to_string("core/_js_i18n.html")
    match = JSON_SCRIPT_RE.search(html)
    assert match is not None, html
    return html, json.loads(match.group("payload"))


class RetentionParityBase(TestCase):
    def setUp(self):
        super().setUp()
        self.station = Station.objects.create(name="Wache Alpha", slug="wache-alpha")
        self.other_station = Station.objects.create(name="Wache Beta", slug="wache-beta")
        self.admin = self._user("admin_a", self.station, Membership.Role.ADMIN)
        self._user("admin_b", self.other_station, Membership.Role.ADMIN)

    def _user(self, username, station, role):
        user = User.objects.create_user(username=username, password="x" * 12)
        Membership.objects.create(user=user, station=station, role=role)
        return user

    def _event(self, correlation_id, *, station=_STATION_DEFAULT, age_days=0):
        event = ErrorEvent.objects.create(
            correlation_id=correlation_id,
            route_name="handover_list",
            category=ErrorEvent.Category.SERVER,
            http_status=500,
            app_version="0.17.0",
            station=self.station if station is _STATION_DEFAULT else station,
        )
        if age_days:
            ErrorEvent.objects.filter(pk=event.pk).update(
                occurred_at=timezone.now() - timedelta(days=age_days)
            )
            event.refresh_from_db()
        return event

    def _view_ids(self, client=None):
        client = client or self.client
        if not client.session.get("_auth_user_id"):
            client.force_login(self.admin)
        response = client.get(reverse("error_events"))
        self.assertEqual(response.status_code, 200)
        return [event.correlation_id for event in response.context["page_obj"].object_list], response

    def _export_ids(self):
        client = self.client
        client.force_login(self.admin)
        response = client.get(reverse("support_export"))
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        header, _, body = text.partition("Zeitpunkt | Korrelations-ID")
        return re.findall(r"corr-[a-z0-9-]+", body)


class RetentionViewTests(RetentionParityBase):
    def test_view_hides_events_older_than_retention(self):
        self._event("corr-expired", age_days=31)
        self._event("corr-fresh")
        ids, response = self._view_ids()
        self.assertEqual(ids, ["corr-fresh"])
        self.assertNotContains(response, "corr-expired")

    @override_settings(ERROR_EVENT_RETENTION_DAYS=7)
    def test_view_and_export_apply_identical_retention_policy(self):
        self._event("corr-ten-days", age_days=10)
        self._event("corr-six-days", age_days=6)
        self._event("corr-now")
        view_ids, _ = self._view_ids()
        export_ids = self._export_ids()
        self.assertEqual(view_ids, ["corr-now", "corr-six-days"])
        self.assertEqual(view_ids, export_ids)

    def test_view_excludes_foreign_station_and_global_events(self):
        self._event("corr-own")
        self._event("corr-foreign", station=self.other_station)
        self._event("corr-global", station=None)
        self._event("corr-own-expired", age_days=45)
        ids, _ = self._view_ids()
        self.assertEqual(ids, ["corr-own"])

    def test_pagination_never_leaks_expired_or_foreign_events(self):
        for index in range(30):
            self._event(f"corr-fresh-{index:02d}")
        for index in range(5):
            self._event(f"corr-expired-{index:02d}", age_days=45)
        for index in range(3):
            self._event(f"corr-foreign-{index:02d}", station=self.other_station)

        client = self.client
        client.force_login(self.admin)
        page_one = client.get(reverse("error_events"))
        page_two = client.get(reverse("error_events"), {"seite": 2})
        ids = [
            event.correlation_id
            for response in (page_one, page_two)
            for event in response.context["page_obj"].object_list
        ]
        self.assertEqual(len(page_one.context["page_obj"].object_list), 25)
        self.assertEqual(len(page_two.context["page_obj"].object_list), 5)
        self.assertEqual(len(ids), 30)
        self.assertTrue(all(correlation.startswith("corr-fresh-") for correlation in ids))
        for response in (page_one, page_two):
            self.assertNotContains(response, "corr-expired-")
            self.assertNotContains(response, "corr-foreign-")

    @override_settings(ERROR_EVENT_RETENTION_DAYS=0)
    def test_retention_zero_keeps_existing_export_semantics(self):
        self._event("corr-zero")
        view_ids, _ = self._view_ids()
        self.assertEqual(view_ids, [])
        self.assertEqual(self._export_ids(), [])

    @override_settings(ERROR_EVENT_RETENTION_DAYS=-1)
    def test_negative_retention_keeps_existing_export_semantics(self):
        self._event("corr-negative")
        view_ids, _ = self._view_ids()
        self.assertEqual(view_ids, [])
        self.assertEqual(self._export_ids(), [])


class JsI18nPayloadTests(TestCase):
    def test_payload_is_json_script_with_expected_id_and_type(self):
        html, data = _rendered_script()
        self.assertIn('<script id="js-i18n" type="application/json">', html)
        self.assertEqual(len(data), 50)
        self.assertTrue(all(isinstance(value, str) and value for value in data.values()))

    def test_payload_keys_match_every_javascript_consumer(self):
        static_dir = pathlib.Path(settings.BASE_DIR) / "core" / "static" / "core"
        used = set()
        for path in sorted(static_dir.glob("*.js")):
            used.update(WB_T_CALL_RE.findall(path.read_text(encoding="utf-8")))
        self.assertEqual(len(used), 50, used)
        _, data = _rendered_script()
        self.assertEqual(set(data), used)

    def test_payload_uses_the_active_language_at_render_time(self):
        with translation.override("en"):
            _, english = _rendered_script()
        with translation.override("de"):
            _, german = _rendered_script()
        self.assertEqual(english["request_failed"], "Request failed.")
        self.assertEqual(german["request_failed"], "Anfrage fehlgeschlagen.")
        self.assertNotEqual(english["unlock"], german["unlock"])

    def test_hostile_translation_cannot_close_the_script_element(self):
        hostile = '</script><script>alert("x")</script>\\\n<> & \''
        with mock.patch("core.templatetags.js_i18n.gettext", side_effect=lambda msgid: hostile):
            html, data = _rendered_script()
        self.assertEqual(html.count("</script>"), 1)
        self.assertNotIn("<script>alert", html)
        self.assertIn("\\u003C", html)
        self.assertEqual(len(data), 50)
        self.assertEqual(set(data.values()), {hostile})
        self.assertEqual(data["request_failed"], hostile)

    def test_fragment_has_no_executable_inline_script(self):
        html, _ = _rendered_script()
        self.assertEqual(EXECUTABLE_SCRIPT_RE.findall(html), [])
        self.assertNotIn("{%", html)

    def test_tag_returns_only_static_catalog_values(self):
        data = js_i18n_data()
        self.assertEqual(len(data), 50)
        self.assertTrue(all(key.islower() for key in data))
        self.assertTrue(all(isinstance(value, str) for value in data.values()))
        copied_msgid = "Kopiert"
        self.assertEqual(data["copied"], str(translation.gettext(copied_msgid)))

    def test_extractor_sees_identical_msgids_and_catalogs_cover_them(self):
        module = pathlib.Path(__file__).with_name("templatetags") / "js_i18n.py"
        extracted = {
            msgid
            for _context, msgid, _plural, _line in extract_python(
                module, module.read_text(encoding="utf-8")
            )
        }
        with translation.override("de"):
            msgids = set(js_i18n_data().values())
        self.assertEqual(len(extracted), 50)
        self.assertEqual(extracted, msgids)

        for language in ("de", "en"):
            po_path = (
                pathlib.Path(settings.BASE_DIR) / "locale" / language / "LC_MESSAGES" / "django.po"
            )
            catalog = {entry["msgid"]: entry for entry in parse_po(po_path)}
            for msgid in msgids:
                with self.subTest(language=language, msgid=msgid):
                    self.assertIn(msgid, catalog)
                    self.assertTrue(catalog[msgid]["msgstr"])
                    self.assertFalse(catalog[msgid]["fuzzy"])
