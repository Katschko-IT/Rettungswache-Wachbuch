"""Datenkatalog (core/data_catalog.py, docs/DATENKATALOG.md).

Die Tests halten den Katalog ehrlich: Jedes Modell steht genau einmal darin,
der committete Referenzkatalog ist aktuell, und die Angaben zu Terminal,
Display, Auditor, Django-Admin, Auswertungen und append-only stimmen mit dem
Code überein. Neue Modelle, Felder, Modulschalter oder Auswertungs-URLs
anderer Pakete machen diese Tests rot, bis sie im Katalog eingetragen sind
und ``python manage.py data_catalog --write`` gelaufen ist.
"""
from __future__ import annotations

import io
import re
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import connection, models
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, reverse
from django.utils import timezone

from core import data_catalog as dc
from core.admin import ReadOnlyAdmin
from core.api.views import DEFAULT_MOBILE_SCOPES, hash_api_token
from core.models import ApiToken, Membership, Station
from core.terminal import OPEN_MODE_BLOCKED, OPEN_MODE_PATHS

ADD_HINT = "im Datenkatalog (core/data_catalog.py) eintragen, dann python manage.py data_catalog --write"

ALL_MODULE_FLAGS = {
    "calendar_enabled": True,
    "birthdays_enabled": True,
    "coffee_enabled": True,
    "feeds_enabled": True,
    "tasks_enabled": True,
    "chat_enabled": True,
    "pinboard_enabled": True,
    "checklists_enabled": True,
    "mpg_enabled": True,
    "warehouse_enabled": True,
    "fleet_enabled": True,
    "display_enabled": True,
    "orga_enabled": True,
    "waste_calendar_enabled": True,
}


def _registry_labels():
    return [spec.label for _module, spec in dc.iter_model_specs()]


def _url_names():
    return {key for key in get_resolver().reverse_dict.keys() if isinstance(key, str)}


def _terminal_reachable(prefix: str) -> bool:
    """Ist ein Bereich im Alltagsmodus des Terminals erreichbar (Präfixe in beide Richtungen)?"""
    for open_path in OPEN_MODE_PATHS:
        if prefix.startswith(open_path):
            target = prefix
        elif open_path.startswith(prefix):
            target = open_path
        else:
            continue
        if not any(target.startswith(blocked) for blocked in OPEN_MODE_BLOCKED):
            return True
    return False


def _module(key):
    return next(module for module in dc.MODULES if module.key == key)


class DataCatalogCoverageTests(SimpleTestCase):
    def test_every_concrete_model_is_catalogued(self):
        labels = _registry_labels()
        missing = sorted(model._meta.label for model in dc.catalog_models() if model._meta.label not in labels)
        self.assertEqual(missing, [], f"Modelle fehlen im Datenkatalog: {missing} – {ADD_HINT}")
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        self.assertEqual(duplicates, [], f"Modelle stehen mehrfach im Datenkatalog: {duplicates}")

    def test_registry_has_no_stale_models(self):
        for label in _registry_labels():
            with self.subTest(label=label):
                model = apps.get_model(label)  # LookupError bei Tippfehler oder entferntem Modell
                self.assertFalse(model._meta.auto_created)

    def test_every_station_module_flag_is_covered(self):
        station_flags = {
            f.name
            for f in Station._meta.concrete_fields
            if isinstance(f, models.BooleanField) and (f.name.endswith("_enabled") or f.name == "traffic_local_sources")
        }
        declared = {module.flag for module in dc.MODULES if module.flag}
        covered = declared | set(dc.STATION_FLAGS_WITHOUT_OWN_DATA)
        self.assertEqual(
            sorted(station_flags - covered), [],
            f"Neue Modulschalter einem Modul oder STATION_FLAGS_WITHOUT_OWN_DATA zuordnen – {ADD_HINT}",
        )
        self.assertEqual(sorted(covered - station_flags), [], "Katalog nennt Schalter, die es an Station nicht gibt")
        for module in dc.MODULES:
            if module.gate:
                self.assertIn(module.gate, dc.GATES)

    def test_retention_keys_and_field_overrides_exist(self):
        for module, spec in dc.iter_model_specs():
            with self.subTest(label=spec.label):
                self.assertIn(spec.retention, dc.RETENTION_RULES)
                self.assertTrue(set(spec.read) <= set(dc.ROLE_LABELS), spec.read)
                self.assertTrue(set(spec.write) <= set(dc.ROLE_LABELS), spec.write)
                self.assertTrue(set(spec.channels) <= set(dc.CHANNEL_LABELS), spec.channels)
                self.assertTrue(spec.purpose)
        for key in dc.FIELD_OVERRIDES:
            with self.subTest(override=key):
                app_label, model_name, field_name = key.split(".")
                model = apps.get_model(app_label, model_name)
                self.assertIn(field_name, [f.name for f in dc.model_fields(model)], f"veralteter Eintrag in FIELD_OVERRIDES: {key}")
        for module, evaluation in dc.all_evaluations():
            self.assertTrue(set(evaluation.roles) <= set(dc.ROLE_LABELS), evaluation)

    def test_committed_reference_catalog_is_current(self):
        current = dc.REFERENCE_PATH.read_text(encoding="utf-8") if dc.REFERENCE_PATH.exists() else ""
        self.assertTrue(
            current == dc.reference_markdown(),
            "docs/DATENKATALOG.md ist veraltet. Neu erzeugen mit: python manage.py data_catalog --write "
            "(auch nach Updates von Django oder django-axes nötig, weil deren Tabellen im Katalog stehen).",
        )

    def test_reference_is_independent_of_environment(self):
        expected = dc.reference_markdown()
        with override_settings(RETENTION_FEED_DAYS=5, RETENTION_AUDIT_DAYS=400, FEEDBACK_RETENTION_DAYS=1, APP_VERSION="9.9.9"):
            with mock.patch.dict("os.environ", {"LOGIN_LOG_RETENTION_DAYS": "3"}):
                self.assertEqual(dc.reference_markdown(), expected)
        self.assertNotIn("9.9.9", expected)

    def test_catalog_renders_no_choice_labels(self):
        text = dc.reference_markdown()
        from core.fleet_models import DisinfectionProtocol

        for f in DisinfectionProtocol._meta.concrete_fields:
            for _value, label in f.choices or ():
                with self.subTest(field=f.name, label=str(label)):
                    self.assertNotIn(str(label), text)
        self.assertNotIn("MRSA", text)

    def test_product_boundary_field_names(self):
        for word in ("patient_name", "einsatz_nr", "pathogen", "mission_id", "triage", "erreger_typ"):
            self.assertRegex(word, dc.FORBIDDEN_FIELD_NAME_RE)
        for word in ("disinfection_level", "decommissioned_at", "user_permissions", "alert_sent_at", "last_disinfection",
                     "disinfectant", "transmission", "permissions"):
            self.assertNotRegex(word, dc.FORBIDDEN_FIELD_NAME_RE)
        hits = sorted(
            f"{model._meta.label}.{f.name}"
            for model in dc.catalog_models()
            for f in dc.model_fields(model)
            if dc.FORBIDDEN_FIELD_NAME_RE.search(f.name)
        )
        self.assertEqual(hits, [], "Feldnamen mit Patienten-, Einsatz- oder Erregerbezug verletzen die Produktgrenze (AGENTS.md § 1)")

    def test_name_fields_are_classified_as_names(self):
        for label in dc.NAME_FIELDS:
            with self.subTest(field=label):
                app_label, model_name, field_name = label.split(".")
                model = apps.get_model(app_label, model_name)
                kind, _note = dc.field_kind(model, model._meta.get_field(field_name))
                self.assertEqual(kind, "Kontakt/Name")

    def test_no_free_text_for_auditor_readable_models(self):
        readable = [spec for _module, spec in dc.iter_model_specs() if "auditor" in spec.read]
        self.assertIn("core.AuditEvent", [spec.label for spec in readable])
        for spec in readable:
            model = apps.get_model(spec.label)
            for f in dc.model_fields(model):
                with self.subTest(field=f"{spec.label}.{f.name}"):
                    self.assertNotEqual(dc.field_kind(model, f)[0], "Freitext")

    def test_terminal_channel_matches_open_mode_paths(self):
        for module in dc.MODULES:
            with self.subTest(module=module.key):
                expected = any(_terminal_reachable(prefix) for prefix in module.web_prefixes)
                self.assertEqual("terminal" in dc.module_channels(module), expected)
        for key in ("mpg", "lager", "fuhrpark", "orga", "kaffeekasse", "audit", "geraete", "chat"):
            self.assertNotIn("terminal", dc.module_channels(_module(key)), key)
        # /konto/avatar/ ist am Terminal offen: Profilbilder sind dort sichtbar.
        self.assertIn("terminal", dc.module_channels(_module("konto")))
        _module_spec, profile = dc.spec_for_label("core.UserProfile")
        self.assertIn("terminal", profile.channels)

    def test_django_admin_channel_matches_registry(self):
        reachable = set(admin.site._registry)
        for model_admin in admin.site._registry.values():
            reachable.update(inline.model for inline in model_admin.inlines)
        for model in dc.catalog_models():
            with self.subTest(model=model._meta.label):
                access = dc.admin_access(model)
                self.assertEqual(bool(access), model in reachable)
                registered = admin.site._registry.get(model)
                if isinstance(registered, ReadOnlyAdmin):
                    self.assertEqual(access, "lesen")
        text = dc.reference_markdown()
        self.assertIn("Django-Admin (lesen)", text)
        self.assertIn("Django-Admin (lesen, anlegen, ändern, löschen)", text)

    def test_db_append_only_matches_grant_command(self):
        source = (Path(settings.BASE_DIR) / "core" / "management" / "commands" / "grant_database_access.py").read_text(encoding="utf-8")
        match = re.search(r"REVOKE UPDATE, DELETE ON(.*?)FROM", source, re.S)
        self.assertIsNotNone(match)
        tables = set(re.findall(r"core_[a-z_]+", match.group(1)))
        by_table = {model._meta.db_table: model._meta.label for model in dc.catalog_models()}
        self.assertEqual({by_table[table] for table in tables}, set(dc.DB_APPEND_ONLY))
        for label in dc.DB_APPEND_ONLY:
            _module_spec, spec = dc.spec_for_label(label)
            self.assertTrue(spec.evidence, label)

    def test_every_evaluation_url_is_catalogued(self):
        names = _url_names()
        catalogued = {evaluation.url_name for _module, evaluation in dc.all_evaluations()}
        matching = {name for name in names if dc.EVALUATION_URL_RE.search(name)}
        self.assertGreaterEqual(len(matching), 13)
        missing = sorted(matching - catalogued - set(dc.NOT_EVALUATIONS))
        self.assertEqual(missing, [], f"Auswertungen/Exporte fehlen im Datenkatalog: {missing} – {ADD_HINT}")
        stale = sorted((catalogued | set(dc.NOT_EVALUATIONS)) - names)
        self.assertEqual(stale, [], f"Katalog nennt unbekannte URL-Namen: {stale}")
        for name, reason in dc.NOT_EVALUATIONS.items():
            self.assertTrue(reason)
            self.assertNotIn(name, catalogued)

    def test_person_list_views_are_flagged(self):
        evaluations = {evaluation.url_name: evaluation for _module, evaluation in dc.all_evaluations()}
        names = _url_names()
        for name in dc.PERSON_LIST_VIEWS:
            with self.subTest(url_name=name):
                self.assertIn(name, names)
                self.assertIn(name, evaluations)
                self.assertTrue(evaluations[name].person_related)
        for name in ("coffee_export", "coffee_ledger", "coffee_book", "sop_export_audit", "audit_log", "api_v1_handover_acks", "mpg_geraetepass"):
            self.assertTrue(evaluations[name].person_related, name)

    def test_device_section_lists_all_cookies(self):
        from core.display_views import COOKIE_NAME as DISPLAY_COOKIE
        from core.terminal import COOKIE_NAME as TERMINAL_COOKIE

        text = dc.reference_markdown()
        for name in (
            settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME, settings.LANGUAGE_COOKIE_NAME,
            "wb_theme", TERMINAL_COOKIE, DISPLAY_COOKIE, "rwsth-install-dismissed",
        ):
            self.assertIn(f"`{name}`", text)
        ui_js = (Path(settings.BASE_DIR) / "core" / "static" / "core" / "ui.js").read_text(encoding="utf-8")
        self.assertIn('"wb_theme=', ui_js)

    def test_snapshot_is_sorted_by_model_label(self):
        text = dc.reference_markdown()
        for module in dc.MODULES:
            positions = [text.index(f"\n### {label}\n") for label in sorted(spec.label for spec in module.models)]
            self.assertEqual(positions, sorted(positions), module.key)


class DisplayChannelTests(TestCase):
    def test_display_models_match_display_queries(self):
        from core.display import display_payload

        station = Station.objects.create(name="Wache Display", slug="wache-display", weather_enabled=True, traffic_enabled=True, **ALL_MODULE_FLAGS)
        tables = {model._meta.db_table: model._meta.label for model in dc.catalog_models()}
        with mock.patch("core.weather.forecast_for_station", side_effect=RuntimeError("kein Netz")), mock.patch(
            "core.traffic.traffic_payload", side_effect=RuntimeError("kein Netz")
        ):
            with CaptureQueriesContext(connection) as queries:
                display_payload(station)
        read = set()
        for query in queries.captured_queries:
            for name in re.findall(r'"([A-Za-z0-9_]+)"', query["sql"]):
                if name in tables:
                    read.add(tables[name])
        read |= set(dc.DISPLAY_VIEW_MODELS)
        declared = {spec.label for _module, spec in dc.iter_model_specs() if "display" in spec.channels}
        self.assertEqual(sorted(declared - read), [], "Katalog nennt Display-Daten, die core/display.py nicht liest")
        self.assertEqual(sorted(read - declared), [], f"core/display.py liest Daten ohne Kanal Display – {ADD_HINT}")


@override_settings(MFA_REQUIRED=False)
class AuditorAccessTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Prüfung", slug="wache-pruefung", **ALL_MODULE_FLAGS)
        self.auditor = User.objects.create_user(username="pruefer", password="pruefer-passwort-123")
        Membership.objects.create(user=self.auditor, station=self.station, role=Membership.Role.AUDITOR)

    def test_auditor_is_refused_where_catalog_says_so(self):
        self.client.force_login(self.auditor)
        refused = [module for module in dc.MODULES if module.entry_url and "auditor" not in dc.module_read_roles(module)]
        keys = {module.key for module in refused}
        for key in ("uebergaben", "kalender", "aufgaben", "neuigkeiten", "wiki", "pinnwand", "maengel", "geraete",
                    "mpg", "lager", "fuhrpark", "orga", "kaffeekasse", "geburtstage", "lage", "checklisten", "chat"):
            self.assertIn(key, keys)
        with self.assertLogs("django.request", "WARNING"):
            for module in refused:
                with self.subTest(module=module.key):
                    response = self.client.get(reverse(module.entry_url))
                    self.assertNotEqual(response.status_code, 200)
        self.assertIn("auditor", dc.module_read_roles(_module("audit")))
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 200)

    def test_auditor_api_token_is_refused(self):
        raw = "wb_test_auditor_catalog_token_1234567890"
        ApiToken.objects.create(
            user=self.auditor,
            label="Prüfung",
            token_prefix=raw[:11],
            token_hash=hash_api_token(raw),
            scopes=list(DEFAULT_MOBILE_SCOPES),
            expires_at=timezone.now() + timedelta(days=1),
        )
        auth = {"HTTP_AUTHORIZATION": f"Token {raw}"}
        with self.assertLogs("django.request", "WARNING"):
            for path in ("/api/v1/handovers/", "/api/v1/kalender/", "/api/v1/kaffeekasse/", "/api/v1/checklisten/", "/api/v1/pinnwand/"):
                with self.subTest(path=path):
                    self.assertNotEqual(self.client.get(path, **auth).status_code, 200)


class StationCatalogTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Süd", slug="wache-sued", coffee_enabled=False, birthdays_enabled=False, fleet_enabled=True,
        )

    def test_station_catalog_lists_only_active_modules(self):
        text = dc.station_markdown(self.station)
        self.assertIn("# Datenkatalog – Wache Süd", text)
        for key in ("fuhrpark", "uebergaben", "konto"):
            self.assertIn(f'<a id="modul-{key}"></a>', text)
        self.assertNotIn('<a id="modul-kaffeekasse"></a>', text)
        self.assertNotIn('<a id="modul-geburtstage"></a>', text)
        self.assertNotIn("## Kaffeekasse (freiwillig)", text)
        self.station.coffee_enabled = True
        self.station.save(update_fields=["coffee_enabled"])
        self.assertIn('<a id="modul-kaffeekasse"></a>', dc.station_markdown(self.station))

    @override_settings(RETENTION_FEED_DAYS=14, RETENTION_AUDIT_DAYS=365)
    def test_station_catalog_shows_configured_periods(self):
        self.station.feeds_enabled = True
        self.station.save(update_fields=["feeds_enabled"])
        text = dc.station_markdown(self.station)
        self.assertIn("14 Tage nach dem letzten Abruf", text)
        self.assertIn("365 Tage (RETENTION_AUDIT_DAYS", text)
        self.assertIn(dc.PERIOD_DECISION_TEXT, text)
        reference = dc.reference_markdown()
        self.assertIn("90 Tage nach dem letzten Abruf", reference)
        self.assertNotIn("14 Tage nach dem letzten Abruf", reference)

    def test_station_catalog_prints_no_proposed_periods(self):
        text = dc.station_markdown(self.station)
        self.assertNotIn("Vorschlag", text)

    def test_settings_gated_modules(self):
        def anchors():
            text = dc.station_markdown(self.station)
            return {key for key in ("terminal", "signal", "demo", "feedback") if f'<a id="modul-{key}"></a>' in text}

        with override_settings(TERMINAL_ENABLED=False, SIGNAL_API_URL="", SIGNAL_NUMBER="", DEMO_SANDBOX=False, FEEDBACK_ENABLED=False):
            self.assertEqual(anchors(), set())
        with override_settings(TERMINAL_ENABLED=True, SIGNAL_API_URL="", DEMO_SANDBOX=False, FEEDBACK_ENABLED=False):
            self.assertEqual(anchors(), {"terminal"})
        with override_settings(TERMINAL_ENABLED=False, SIGNAL_API_URL="http://signal:8080", SIGNAL_NUMBER="+4915112345678",
                               DEMO_SANDBOX=False, FEEDBACK_ENABLED=False):
            self.assertEqual(anchors(), {"signal"})
        with override_settings(TERMINAL_ENABLED=False, SIGNAL_API_URL="", DEMO_SANDBOX=True, FEEDBACK_ENABLED=False):
            self.assertEqual(anchors(), {"demo"})
        with override_settings(TERMINAL_ENABLED=False, SIGNAL_API_URL="", DEMO_SANDBOX=False, FEEDBACK_ENABLED=True):
            self.assertEqual(anchors(), {"feedback"})

    def test_station_output_contains_no_row_contents(self):
        self.station.iban = "DE02120300000000202051"
        self.station.payment_note = "Kaffee-Notiz-XYZ"
        self.station.street = "Musterweg 12"
        self.station.coffee_enabled = True
        self.station.save()
        erika = User.objects.create_user(username="erika.muster", first_name="Erika", last_name="Muster", email="erika@example.invalid")
        Membership.objects.create(user=erika, station=self.station, role=Membership.Role.MEMBER)
        text = dc.station_markdown(self.station)
        for value in ("DE02120300000000202051", "Kaffee-Notiz-XYZ", "Musterweg 12", "Erika", "Muster", "erika.muster", "erika@example.invalid"):
            self.assertNotIn(value, text)


class DataCatalogCommandTests(TestCase):
    def test_check_passes_and_detects_stale_file(self):
        out = io.StringIO()
        call_command("data_catalog", "--check", stdout=out)
        self.assertIn("aktuell", out.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "DATENKATALOG.md"
            stale.write_text("# alt\n", encoding="utf-8")
            with mock.patch.object(dc, "REFERENCE_PATH", stale):
                with self.assertRaisesMessage(CommandError, "python manage.py data_catalog --write"):
                    call_command("data_catalog", "--check", stdout=io.StringIO())
            with mock.patch.object(dc, "REFERENCE_PATH", Path(tmp) / "fehlt.md"):
                with self.assertRaises(CommandError):
                    call_command("data_catalog", "--check", stdout=io.StringIO())
            with mock.patch.object(dc, "REFERENCE_PATH", stale):
                call_command("data_catalog", "--write", stdout=io.StringIO())
                self.assertEqual(stale.read_text(encoding="utf-8"), dc.reference_markdown())

    def test_station_resolution(self):
        with mock.patch.object(Station, "get_default", side_effect=AssertionError("legt keine Wache an")):
            with self.assertRaises(CommandError):
                call_command("data_catalog", "--station", "auto", stdout=io.StringIO())
        self.assertFalse(Station.objects.exists())
        Station.objects.create(name="Wache Eins", slug="wache-eins")
        with self.assertRaises(CommandError):
            call_command("data_catalog", "--station", "unbekannt", stdout=io.StringIO())
        out = io.StringIO()
        call_command("data_catalog", "--station", "auto", stdout=out)
        self.assertIn("# Datenkatalog – Wache Eins", out.getvalue())
        Station.objects.create(name="Wache Zwei", slug="wache-zwei")
        with self.assertRaises(CommandError):
            call_command("data_catalog", "--station", "auto", stdout=io.StringIO())
        out = io.StringIO()
        call_command("data_catalog", "--station", "wache-zwei", stdout=out)
        self.assertIn("# Datenkatalog – Wache Zwei", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("data_catalog", "--write", "--station", "wache-zwei", stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command("data_catalog", "--check", "--station", "wache-zwei", stdout=io.StringIO())

    def test_station_auto_ignores_demo_and_inactive_stations(self):
        from core.demo_models import DemoSandbox

        Station.objects.create(name="Alte Wache", slug="alte-wache", is_active=False)
        demo = Station.objects.create(name="Demo-Wache", slug="demo-wache")
        DemoSandbox.objects.create(station=demo, token="t" * 16)
        Station.objects.create(name="Echte Wache", slug="echte-wache")
        out = io.StringIO()
        call_command("data_catalog", "--station", "auto", stdout=out)
        self.assertIn("# Datenkatalog – Echte Wache", out.getvalue())

    def test_command_writes_nothing_to_db(self):
        Station.objects.create(name="Wache Lesen", slug="wache-lesen")
        with CaptureQueriesContext(connection) as queries:
            call_command("data_catalog", "--station", "auto", stdout=io.StringIO())
            call_command("data_catalog", stdout=io.StringIO())
        writes = [q["sql"] for q in queries.captured_queries if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q["sql"], re.I)]
        self.assertEqual(writes, [])

    def test_output_option_writes_file(self):
        Station.objects.create(name="Wache Datei", slug="wache-datei")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "katalog.md"
            call_command("data_catalog", "--station", "wache-datei", "--output", str(target), stdout=io.StringIO())
            self.assertIn("# Datenkatalog – Wache Datei", target.read_text(encoding="utf-8"))
