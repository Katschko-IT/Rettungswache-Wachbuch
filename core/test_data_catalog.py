"""Datenkatalog (core/data_catalog.py, docs/DATENKATALOG.md).

Die Tests halten den Katalog ehrlich: Jedes Modell steht genau einmal darin,
der committete Referenzkatalog ist aktuell, und die Angaben zu Terminal,
Display, Auditor, Django-Admin, Auswertungen und append-only stimmen mit dem
Code überein. Neue Modelle, Felder, Modulschalter oder Auswertungs-URLs
anderer Pakete machen diese Tests rot, bis sie im Katalog eingetragen sind
und ``python manage.py data_catalog --write`` gelaufen ist.
"""
from __future__ import annotations

import importlib.util
import io
import re
import tempfile
import logging
from contextlib import contextmanager
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
from django.urls import NoReverseMatch, get_resolver, reverse
from django.utils import timezone

from core import data_catalog as dc
from core.admin import ReadOnlyAdmin
from core.api.views import DEFAULT_MOBILE_SCOPES, hash_api_token
from core.fleet_models import Vehicle
from core.models import (
    ApiToken,
    AuditEvent,
    CalendarEvent,
    Checklist,
    ChecklistCompletion,
    CoffeeEntry,
    HandoverEntry,
    Membership,
    PinboardNote,
    Station,
    StationTask,
    StationTaskCompletion,
)
from core.mpg_models import DeviceTrainingRecord, MedicalDevice
from core.orga_models import SOPDocument
from core.terminal import OPEN_MODE_BLOCKED, OPEN_MODE_PATHS
from core.wachalltag_models import Defect, DefectAttachment, DefectEvent, HandoverAck, InventoryItem, StationAsset
from core.warehouse_models import MedicalItem

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


# Verzeichnis der Nachweise aus Paket B1 (core/evidence.py). Solange B1 nicht
# integriert ist, vergleicht der Test mit dieser Kopie, danach mit dem Original.
B1_EVIDENCE_MODELS = (
    "core.AuditEvent", "core.HandoverEntry", "core.HandoverRevision", "core.HandoverAck", "core.HandoverAttachment",
    "core.NewsAttachment", "core.PinboardAttachment", "core.ChecklistCompletion", "core.CoffeeEntry",
    "core.CoffeeCashMovement", "core.Defect", "core.DefectEvent", "core.DefectAttachment", "core.AssetEvent",
    "core.InventoryEvent", "core.StockMovement", "core.WikiRevision", "core.VehicleHandover",
    "core.DisinfectionProtocol", "core.MaintenanceLog", "core.DeviceRoutineCheck", "core.DeviceTrainingRecord",
    "core.SOPRevision", "core.SOPReceipt",
)
B1_NOT_EVIDENCE = (
    "core.CalendarEvent", "core.ErrorEvent", "core.NewsAcknowledgement", "core.QrTotpUse", "core.StationTaskCompletion",
)


def _evidence_registry():
    if importlib.util.find_spec("core.evidence") is None:
        return set(B1_EVIDENCE_MODELS), set(B1_NOT_EVIDENCE)
    from core import evidence

    return set(evidence.EVIDENCE_MODELS), set(evidence.NOT_EVIDENCE)


def _code_strings(function) -> list[str]:
    return [c for c in getattr(getattr(function, "__code__", None), "co_consts", ()) if isinstance(c, str)]


def _row_guarded(model) -> bool:
    """Eigene save()/delete() verweigern Ändern und Löschen (wie core/test_append_only_guards.py)."""
    save, delete = vars(model).get("save"), vars(model).get("delete")
    return any("nicht gelöscht" in text for text in _code_strings(delete)) and any(
        "nicht verändert" in text for text in _code_strings(save)
    )


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

    def test_evidence_flags_match_evidence_registry(self):
        evidence_models, not_evidence = _evidence_registry()
        flagged = {spec.label for _module, spec in dc.iter_model_specs() if spec.evidence}
        self.assertEqual(sorted(flagged - evidence_models), [], "Katalog nennt Nachweise, die das Nachweisverzeichnis (B1) nicht führt")
        self.assertEqual(sorted(evidence_models - flagged), [], f"Nachweise aus dem Nachweisverzeichnis (B1) mit evidence=True eintragen – {ADD_HINT}")
        self.assertEqual(sorted(flagged & not_evidence), [])
        # Stammdaten sind keine Nachweise: Sie werden bearbeitet, die Nachweise hängen an ihnen.
        for label in ("core.Vehicle", "core.MedicalDevice", "core.SOPDocument", "core.ItemBatch"):
            self.assertFalse(dc.spec_for_label(label)[1].evidence, label)

    def test_append_only_claims_match_model_guards(self):
        guarded = {model._meta.label for model in dc.catalog_models() if _row_guarded(model)}
        self.assertIn("core.StockMovement", guarded)
        self.assertEqual(sorted(guarded ^ set(dc.ROW_APPEND_ONLY)), [], "ROW_APPEND_ONLY an den Zeilenschutz der Modelle anpassen")
        self.assertTrue(set(dc.DB_APPEND_ONLY) <= set(dc.ROW_APPEND_ONLY))
        text = dc.reference_markdown()
        for _module, spec in dc.iter_model_specs():
            with self.subTest(label=spec.label):
                section = text.split(f"\n### {spec.label}\n", 1)[1].split("\n### ", 1)[0]
                nachweis = next(line for line in section.splitlines() if line.startswith("- Nachweis: "))
                self.assertEqual("append-only" in nachweis, spec.label in dc.ROW_APPEND_ONLY)
                self.assertEqual("Datenbankrechte" in nachweis, spec.label in dc.DB_APPEND_ONLY)
                if spec.label in dc.ROW_APPEND_ONLY:
                    self.assertTrue(spec.evidence)
                self.assertEqual("- Löschschutz: " in section, spec.evidence)
        for rule in dc.RETENTION_RULES.values():
            self.assertNotIn("Korrektur nur als neuer Eintrag", rule.default_text)

    def test_deletion_guard_follows_on_delete(self):
        for _module, spec in dc.iter_model_specs():
            if not spec.evidence:
                continue
            model = apps.get_model(spec.label)
            with self.subTest(label=spec.label):
                cascades = [f.name for f in model._meta.concrete_fields if f.is_relation and f.remote_field.on_delete is models.CASCADE]
                guard = dc.deletion_guard_text(model)
                self.assertEqual("mitgelöscht" in guard, bool(cascades))
                for name in cascades:
                    self.assertIn(f"`{name}`", guard)

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


class _ReachedForm(Exception):
    """Die Ansicht hat die Rollenprüfung passiert und baut das Formular."""


@contextmanager
def _quiet_error_logs():
    """Ein erreichtes Formular endet als Fehler 500; dessen Protokoll gehört nicht in die Testausgabe."""
    loggers = [logging.getLogger(name) for name in ("django.request", "wachbuch.errors")]
    previous = [logger.disabled for logger in loggers]
    for logger in loggers:
        logger.disabled = True
    try:
        yield
    finally:
        for logger, disabled in zip(loggers, previous):
            logger.disabled = disabled


# Schreibende Ansichten und ihr Formular. Die Rollen im Katalog („Schreiben“)
# müssen mit den Prüfungen in der Ansicht übereinstimmen, nicht nur mit dem
# äußeren Decorator.
WRITE_VIEWS = (
    ("core.MedicalDevice", "mpg_device_create", None, "core.mpg_views.MedicalDeviceForm"),
    ("core.MaintenanceLog", "mpg_maintenance_create", "device", "core.mpg_views.MaintenanceLogForm"),
    ("core.DeviceTrainingRecord", "mpg_training_create", "device", "core.mpg_views.DeviceTrainingRecordForm"),
    ("core.DeviceRoutineCheck", "mpg_routine_check", "device", "core.mpg_views.DeviceRoutineCheckForm"),
    ("core.SOPDocument", "sop_create", None, "core.orga_views.SOPDocumentForm"),
    ("core.SOPRevision", "sop_revision_create", "sop", "core.orga_views.SOPRevisionForm"),
    ("core.StationContact", "contact_create", None, "core.orga_views.StationContactForm"),
    ("core.MedicalItem", "warehouse_item_create", None, "core.warehouse_views.MedicalItemForm"),
    ("core.ItemBatch", "warehouse_batch_create", "item", "core.warehouse_views.ItemBatchForm"),
    ("core.Vehicle", "fleet_vehicle_create", None, "core.fleet_views.VehicleForm"),
    ("core.DisinfectionProtocol", "fleet_vehicle_disinfection_create", "vehicle", "core.fleet_views.DisinfectionProtocolForm"),
    ("core.VehicleHandover", "fleet_vehicle_handover_create", "vehicle", "core.fleet_views.VehicleHandoverForm"),
)


@override_settings(MFA_REQUIRED=False)
class CatalogMatchesBehaviourTests(TestCase):
    """Was der Katalog über Schreibrechte und Löschen sagt, tut der Code auch."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Verhalten", slug="wache-verhalten", **ALL_MODULE_FLAGS)
        self.users = {}
        for role in (Membership.Role.MEMBER, Membership.Role.SHIFT_LEAD):
            user = User.objects.create_user(username=f"verhalten-{role}", password="verhalten-passwort-123")
            self.users[role] = Membership.objects.create(user=user, station=self.station, role=role)
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi", name="Defi")
        self.targets = {
            "device": self.device,
            "sop": SOPDocument.objects.create(
                station=self.station, slug="sop-1", doc_number="SOP-1", title="Dienstanweisung",
                created_by=self.users[Membership.Role.SHIFT_LEAD].user,
            ),
            "item": MedicalItem.objects.create(station=self.station, slug="kanuele", name="Venenkanüle"),
            "vehicle": Vehicle.objects.create(station=self.station, slug="rtw-1", call_sign="RTW 1", license_plate="RW-1"),
        }

    def test_write_roles_match_role_checks_in_views(self):
        for label, url_name, target, form_path in WRITE_VIEWS:
            spec = dc.spec_for_label(label)[1]
            args = [self.targets[target].slug] if target else []
            for role, membership in self.users.items():
                allowed = role in spec.write
                with self.subTest(model=label, role=role):
                    self.client.force_login(membership.user)
                    with mock.patch(form_path, side_effect=_ReachedForm), _quiet_error_logs():
                        try:
                            self.client.post(reverse(url_name, args=args), {})
                        except _ReachedForm:
                            reached = True
                        else:
                            reached = False
                    self.assertEqual(reached, allowed, f"Schreibrollen von {label} im Katalog anpassen – {ADD_HINT}")

    def test_reopening_a_task_deletes_the_completion(self):
        from core.task_board import toggle_task_completion

        task = StationTask.objects.create(station=self.station, title="Wache fegen", band=StationTask.Band.DAILY)
        member = self.users[Membership.Role.MEMBER]
        today = timezone.localdate()
        toggle_task_completion(task=task, membership=member, work_date=today, mark_done=True)
        self.assertTrue(StationTaskCompletion.objects.filter(task=task).exists())
        toggle_task_completion(task=task, membership=member, work_date=today, mark_done=False)
        self.assertFalse(StationTaskCompletion.objects.filter(task=task).exists())
        self.assertTrue(AuditEvent.objects.filter(action="station_task.reopened").exists())
        spec = dc.spec_for_label("core.StationTaskCompletion")[1]
        self.assertFalse(spec.evidence)
        self.assertIn("löscht den Vermerk", dc.RETENTION_RULES[spec.retention].text())

    def test_new_training_replaces_the_previous_one(self):
        trainee = self.users[Membership.Role.MEMBER].user
        self.client.force_login(self.users[Membership.Role.SHIFT_LEAD].user)
        url = reverse("mpg_training_create", args=[self.device.slug])
        for days_ago in (30, 0):
            self.client.post(url, {
                "trainee": trainee.pk,
                "instructor": "Herstellerschulung",
                "trained_at": (timezone.localdate() - timedelta(days=days_ago)).isoformat(),
                "notes": "",
            })
        records = DeviceTrainingRecord.objects.filter(device=self.device, trainee=trainee)
        self.assertEqual(records.count(), 1, "Einweisungen werden nicht mehr ersetzt: Frist für core.DeviceTrainingRecord im Katalog anpassen")
        self.assertEqual(records.get().trained_at, timezone.localdate())
        spec = dc.spec_for_label("core.DeviceTrainingRecord")[1]
        self.assertEqual(spec.retention, "training_replace")
        self.assertNotIn("append-only", dc.evidence_text(spec))


# App-Schnittstellen mit Pfadparametern, die der folgende Test nicht aufruft.
API_NOT_CALLED = {
    "api_v1_attachment_download": "liefert die Datei selbst",
    "api_v1_chat_private_thread": "eigene Unterhaltung, Inhalt verschlüsselt",
    "api_v1_post_detail": "eigene Post, Inhalt verschlüsselt",
    "api_v1_chat_group_detail": "eigene Gruppe, Inhalt verschlüsselt",
    "api_v1_chat_group_members": "Mitglieder einer eigenen Gruppe",
}


@override_settings(MFA_REQUIRED=False)
class ApiPersonListTests(TestCase):
    """Jede App-Schnittstelle, die andere Personen namentlich zeigt, steht im Katalog."""

    NAMES = ("erika.zeugin", "Erika", "Zeugin")

    def setUp(self):
        station = Station.objects.create(name="Wache App", slug="wache-app", **ALL_MODULE_FLAGS)
        viewer = User.objects.create_user(username="kasse.app", first_name="Karl", last_name="Kasse")
        Membership.objects.create(user=viewer, station=station, role=Membership.Role.CASHIER)
        erika = User.objects.create_user(username="erika.zeugin", first_name="Erika", last_name="Zeugin")
        Membership.objects.create(user=erika, station=station, role=Membership.Role.MEMBER)
        now = timezone.now()
        handover = HandoverEntry.objects.create(station=station, category="info", title="Übergabe", details="Text", author=erika)
        HandoverAck.objects.create(station=station, handover=handover, user=erika)
        defect = Defect.objects.create(station=station, title="Mangel", created_by=erika, owner=erika)
        DefectEvent.objects.create(defect=defect, station=station, kind=DefectEvent.Kind.CREATED, actor=erika)
        png = _png_bytes()
        DefectAttachment.objects.create(
            station=station, defect=defect, filename="bild.png", content_type="image/png", data=png, size=len(png),
            uploaded_by=erika,
        )
        InventoryItem.objects.create(station=station, item_id="funk-1", label="Funkgerät", holder=erika, checked_out_at=now)
        StationAsset.objects.create(station=station, asset_id="geraet-1", label="Gerät", updated_by=erika)
        CoffeeEntry.objects.create(station=station, member=erika, amount_cents=500, reason="Einzahlung", created_by=erika)
        checklist = Checklist.objects.create(station=station, title="Fahrzeugcheck")
        ChecklistCompletion.objects.create(station=station, checklist=checklist, completed_by=erika)
        PinboardNote.objects.create(station=station, title="Aushang", body="Text", author=erika)
        CalendarEvent.objects.create(
            station=station, title="Termin", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=1, hours=1),
            created_by=erika,
        )
        raw = "wb_test_catalog_person_token_1234567890"
        ApiToken.objects.create(
            user=viewer, label="Katalog", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=list(DEFAULT_MOBILE_SCOPES), expires_at=now + timedelta(days=1),
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Token {raw}"}
        self.args = {
            "api_v1_handover_detail": [handover.pk],
            "api_v1_uebergabe_detail": [handover.pk],
            "api_v1_handover_acks": [handover.pk],
            "api_v1_defect_detail": [defect.pk],
            "api_v1_defect_attachments": [defect.pk],
            "api_v1_checkliste_schedule": [checklist.pk],
        }

    def _shows_other_person(self, name) -> bool | None:
        try:
            path = reverse(name, args=self.args.get(name, []))
        except NoReverseMatch:
            return None
        response = self.client.get(path, **self.auth)
        if response.status_code != 200:
            return False
        body = response.content.decode("utf-8", "replace")
        return any(value in body for value in self.NAMES)

    def test_api_person_lists_are_catalogued(self):
        names = sorted(name for name in _url_names() if name.startswith("api_v1_"))
        shown, not_called = set(), set()
        for name in names:
            if name in API_NOT_CALLED:
                continue
            result = self._shows_other_person(name)
            if result is None:
                not_called.add(name)
            elif result:
                shown.add(name)
        # Nicht aufrufbar sind nur Schreib-Endpunkte (ohne GET) mit Pfadparametern.
        for name in sorted(not_called):
            with self.subTest(not_called=name):
                self.assertRegex(name, r"_(status|ack|checkout|checkin|erledigt|abschluss|read)$",
                                 "neuer lesender App-Endpunkt mit Parametern: in ApiPersonListTests.args oder API_NOT_CALLED eintragen")
        unlisted = sorted(shown - set(dc.PERSON_LIST_VIEWS) - set(dc.API_NAMES_WITHOUT_EVALUATION))
        self.assertEqual(unlisted, [], f"App-Schnittstellen zeigen andere Personen namentlich: als Auswertung mit Personenbezug – {ADD_HINT}")
        for name in dc.PERSON_LIST_VIEWS:
            if name.startswith("api_v1_"):
                self.assertIn(name, shown, f"{name} zeigt im Test keine andere Person")
        for name, reason in dc.API_NAMES_WITHOUT_EVALUATION.items():
            with self.subTest(without_evaluation=name):
                self.assertTrue(reason)
                self.assertIn(name, shown)
                self.assertNotIn(name, dc.PERSON_LIST_VIEWS)
        self.assertGreaterEqual(len(shown), 9)


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()
