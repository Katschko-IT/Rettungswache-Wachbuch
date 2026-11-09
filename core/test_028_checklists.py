"""Tests für 0.28: Checklisten mit Ergebnis je Punkt, Zwischenstand, Nachweis und Auswertung.

Abgedeckt (Paket P1 der 0.28-Prüfung):

- Zwischenstände liegen in ``ChecklistDraft``; ``core_checklistcompletion``
  bekommt nur INSERTs (CaptureQueriesContext, Web und App; auf PostgreSQL
  zusätzlich unter der echten App-Rolle nach ``grant_database_access``).
- Fortsetzen stellt Ergebnis, Messwert, Begründung und Notiz wieder her; ein
  abgelehnter Abschluss zeigt die Eingaben erneut.
- Ein gemeinsamer Prüfdienst für Web und App: Pflichtpunkte, fehlende
  Ergebnisse, Messwerte (fehlend, NaN/Infinity/Überlauf, Grenzwert 0),
  strenge Eingaben der App (400 statt 500).
- Kopie des Prüfpunkts im Ergebnis, Rückverweis Mangel → Lauf, keine doppelten
  Mängel, Verlauf, Einzellauf, CSV-Export, Kennzahl, Nachtrag vom Papierbogen,
  Sperre am Wachenterminal, housekeeping und Datenmigration 0077.
"""
from __future__ import annotations

import csv
import importlib
import io
import json
import re
import shutil
import subprocess
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .api.views import hash_api_token
from .checklists_models import ChecklistRun, ChecklistTemplate
from .checklists_service import has_result_per_item, latest_runs, per_item_quota
from .management.commands.housekeeping import run_housekeeping
from .models import (
    ApiToken,
    AuditEvent,
    Checklist,
    ChecklistCompletion,
    ChecklistDraft,
    ChecklistItem,
    Membership,
    Station,
)
from .terminal import COOKIE_NAME, hash_secret, set_station_code
from .terminal_models import StationTerminal
from .test_review_final_core import (
    PostgresLockAssertions,
    app_role_read_only_tables,
    record_row_locks,
)
from .wachalltag_models import ChecklistSchedule, Defect, DefectEvent

User = get_user_model()
TERMINAL_CODE = "4827"
COMPLETION_TABLE = "core_checklistcompletion"


def completion_writes(queries) -> list[str]:
    """UPDATE/DELETE/FOR UPDATE auf der append-only Tabelle in mitgeschnittenen Abfragen."""
    table = COMPLETION_TABLE.upper()
    patterns = (
        rf'UPDATE\s+"?{table}"?\s',
        rf'DELETE\s+FROM\s+"?{table}"?',
        rf'FROM\s+"?{table}"?.*FOR\s+UPDATE',
    )
    return [
        query["sql"] for query in queries
        if any(re.search(pattern, query["sql"].upper(), re.S) for pattern in patterns)
    ]


def completion_inserts(queries) -> int:
    return sum(
        1 for query in queries if re.search(rf'INSERT\s+INTO\s+"?{COMPLETION_TABLE.upper()}"?', query["sql"].upper())
    )


class ChecklistBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Rettungswache Nord", slug="rw-nord", checklists_enabled=True)
        self.user = User.objects.create_user(username="wachschicht1", password="test-password-123!", first_name="Alex")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.client.force_login(self.user)

        # Fremde Checkliste zuerst: Kennungen der eigenen Prüfpunkte beginnen nicht bei 1.
        self.other_station = Station.objects.create(name="Wache Süd", slug="rw-sued", checklists_enabled=True)
        other_list = Checklist.objects.create(station=self.other_station, title="Fremde Liste")
        self.foreign_item = ChecklistItem.objects.create(checklist=other_list, text="Fremder Punkt")

        self.checklist = Checklist.objects.create(
            station=self.station, title="Tägliche Kühlschrank- & Geräteprüfung", description="Morgendlicher Rundgang",
        )
        self.item_temp = ChecklistItem.objects.create(
            checklist=self.checklist, text="Medikamentenkühlschrank Temperatur", position=1, is_required=True,
            measurement_unit="°C", min_value=Decimal("2.00"), max_value=Decimal("8.00"),
        )
        self.item_seal = ChecklistItem.objects.create(
            checklist=self.checklist, text="Notfallrucksack Plombe intakt", position=2, is_required=True,
        )
        self.item_opt = ChecklistItem.objects.create(
            checklist=self.checklist, text="Sonderfahrzeug Zusatzheizung", position=3, is_required=False,
        )
        self.url = reverse("checklist_complete", args=[self.checklist.id])

    def post_run(self, **fields):
        data = {
            f"result_{self.item_temp.id}": "ok",
            f"value_{self.item_temp.id}": "5,2",
            f"result_{self.item_seal.id}": "ok",
            f"reason_{self.item_temp.id}": "",
            f"reason_{self.item_seal.id}": "",
            f"reason_{self.item_opt.id}": "",
            "action": "complete",
        }
        data.update(fields)
        return self.client.post(self.url, {key: value for key, value in data.items() if value is not None})

    def token(self, user=None, raw="wb_test_028_checklist_token_1234567890", scopes=("read:checklists", "write:checklists")):
        ApiToken.objects.create(
            user=user or self.user, label="Test 028", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=list(scopes), expires_at=timezone.now() + timedelta(days=1),
        )
        return {"HTTP_AUTHORIZATION": f"Token {raw}"}

    def api_post(self, url, payload, auth, *, raw_body=None):
        body = raw_body if raw_body is not None else json.dumps(payload)
        return self.client.post(url, data=body, content_type="application/json", **auth)

    def make_run(self, *, user=None, when=None, item_results=None, backfill_at=None):
        run = ChecklistCompletion.objects.create(
            station=self.station, checklist=self.checklist, completed_by=user or self.user,
            item_results=item_results if item_results is not None else {},
            is_paper_backfill=backfill_at is not None, occurred_at=backfill_at,
        )
        if when is not None:
            # Testdaten: Zeitpunkt in der Vergangenheit (nur hier, als Eigentümer der Testdatenbank).
            ChecklistCompletion.objects.filter(pk=run.pk).update(created_at=when)
            run.refresh_from_db()
        return run


class Checklist028Tests(ChecklistBase):
    def test_aliases_exposed(self):
        self.assertIs(ChecklistTemplate, Checklist)
        self.assertIs(ChecklistRun, ChecklistCompletion)

    def test_per_item_results_ok_and_na_requires_reason(self):
        # „entfällt“ ohne Grund: abgelehnt, die Seite zeigt die Eingaben erneut (früher: Umleitung, Eingaben weg).
        resp = self.post_run(**{
            f"result_{self.item_temp.id}": "ok", f"value_{self.item_temp.id}": "5.2",
            f"result_{self.item_seal.id}": "na", f"reason_{self.item_seal.id}": "",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)
        self.assertContains(resp, "Für entfallenen Punkt „Notfallrucksack Plombe intakt“", status_code=400)

        resp = self.post_run(**{
            f"result_{self.item_temp.id}": "ok", f"value_{self.item_temp.id}": "5.2",
            f"result_{self.item_seal.id}": "na",
            f"reason_{self.item_seal.id}": "Rucksack aktuell im Desinfektionsraum",
        })
        self.assertEqual(resp.status_code, 302)
        run = ChecklistCompletion.objects.get()
        self.assertEqual(run.item_results[str(self.item_temp.id)]["status"], "ok")
        self.assertAlmostEqual(run.item_results[str(self.item_temp.id)]["value"], 5.2)
        self.assertEqual(run.item_results[str(self.item_seal.id)]["status"], "na")
        self.assertEqual(run.item_results[str(self.item_seal.id)]["reason"], "Rucksack aktuell im Desinfektionsraum")
        self.assertEqual(Defect.objects.count(), 0)

    def test_measurement_out_of_bounds_marks_not_ok_and_creates_defect(self):
        resp = self.post_run(**{f"value_{self.item_temp.id}": "9,5"})
        self.assertEqual(resp.status_code, 302)
        run = ChecklistCompletion.objects.get()
        temp_res = run.item_results[str(self.item_temp.id)]
        self.assertEqual(temp_res["status"], "not_ok")
        self.assertAlmostEqual(temp_res["value"], 9.5)
        self.assertIn("außerhalb Grenzwert [2.00..8.00]", temp_res["reason"])
        defect = Defect.objects.get(pk=temp_res["defect_id"])
        self.assertEqual(defect.station, self.station)
        self.assertIn("Medikamentenkühlschrank Temperatur", defect.title)
        self.assertIn("9.5 °C", defect.description)
        self.assertIn("2.00..8.00", defect.description)
        # Rückverweis und Kopie des Prüfpunkts; der Name der prüfenden Person steht nur im Personenfeld.
        self.assertEqual(defect.source_checklist_run, run)
        self.assertEqual(defect.source_item_id, self.item_temp.id)
        self.assertEqual(defect.source_item_text, "Medikamentenkühlschrank Temperatur")
        self.assertEqual(defect.created_by, self.user)
        self.assertNotIn("Alex", defect.description)
        self.assertNotIn("wachschicht1", defect.description)
        self.assertIn("Aus dem Checklisten-Lauf vom", defect.description)
        audit = AuditEvent.objects.get(action="defect.created", object_id=str(defect.pk))
        self.assertEqual(audit.metadata["checklist_run_id"], run.pk)

    def test_explicit_not_ok_creates_defect_with_back_reference_via_api(self):
        auth = self.token()
        payload = {
            "note": "Plombe gerissen",
            "is_draft": False,
            "item_results": {
                str(self.item_temp.id): {"status": "ok", "value": 4.8},
                str(self.item_seal.id): {"status": "not_ok", "reason": "Plombe fehlt nach Einsatz"},
            },
        }
        resp = self.api_post(reverse("api_v1_checkliste_erledigt", args=[self.checklist.id]), payload, auth)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertFalse(data["is_draft"])
        self.assertEqual(len(data["defects_created"]), 1)
        defect = Defect.objects.get(pk=data["defects_created"][0])
        self.assertIn("Notfallrucksack Plombe intakt", defect.title)
        self.assertIn("Plombe fehlt nach Einsatz", defect.description)
        run = ChecklistCompletion.objects.get(pk=data["id"])
        self.assertEqual(run.item_results[str(self.item_seal.id)]["defect_id"], defect.id)
        self.assertEqual(defect.source_checklist_run, run)

    def test_draft_save_resume_and_completion_inserts_a_new_run(self):
        resp = self.client.post(self.url, {
            f"result_{self.item_temp.id}": "not_ok",
            f"value_{self.item_temp.id}": "1,2",
            f"result_{self.item_seal.id}": "na",
            f"reason_{self.item_seal.id}": "Rucksack in der Aufbereitung",
            "note": "Unterbrochen durch Einsatz",
            "action": "draft",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)
        draft = ChecklistDraft.objects.get(checklist=self.checklist)
        self.assertEqual((draft.created_by, draft.updated_by), (self.user, self.user))
        self.assertEqual(Defect.objects.count(), 0)

        # Fortsetzen: Ergebnis, Messwert, Begründung und Notiz stehen wieder im Formular.
        page = self.client.get(reverse("checklists"))
        self.assertContains(page, f'name="result_{self.item_temp.id}" value="not_ok" checked')
        self.assertContains(page, f'name="result_{self.item_seal.id}" value="na" checked')
        self.assertNotContains(page, f'name="result_{self.item_opt.id}" value="ok" checked')
        self.assertContains(page, f'name="value_{self.item_temp.id}" value="1,2"')
        self.assertContains(page, f'name="reason_{self.item_seal.id}" value="Rucksack in der Aufbereitung"')
        self.assertContains(page, 'value="Unterbrochen durch Einsatz"')
        self.assertContains(page, "Zwischenstand vorhanden")

        # Jemand anderes aus der Besatzung macht weiter und schließt ab.
        colleague = User.objects.create_user(username="kollegin", password="test-password-123!", first_name="Kim")
        Membership.objects.create(user=colleague, station=self.station, role=Membership.Role.MEMBER)
        self.client.force_login(colleague)
        started = timezone.now()
        resp = self.client.post(self.url, {
            f"result_{self.item_temp.id}": "not_ok",
            f"value_{self.item_temp.id}": "1,2",
            f"result_{self.item_seal.id}": "ok",
            "note": "Nach Einsatz abgeschlossen",
            "action": "complete",
        })
        self.assertEqual(resp.status_code, 302)
        run = ChecklistCompletion.objects.get()
        self.assertEqual(run.completed_by, colleague)
        self.assertEqual(run.note, "Nach Einsatz abgeschlossen")
        self.assertGreaterEqual(run.created_at, started)
        self.assertFalse(ChecklistDraft.objects.exists())
        self.assertEqual(Defect.objects.count(), 1)

        run.note = "Manipulationsversuch"
        with self.assertRaises(ValidationError):
            run.save()
        with self.assertRaises(ValidationError):
            run.delete()

    def test_draft_keeps_own_status_and_finalize_rechecks_the_limits(self):
        # Zwischenstand mit Messwert außerhalb der Grenzen: gespeichert wird die eigene Wahl.
        self.client.post(self.url, {
            f"result_{self.item_temp.id}": "ok", f"value_{self.item_temp.id}": "9,5",
            f"result_{self.item_seal.id}": "ok", "action": "draft",
        })
        entry = ChecklistDraft.objects.get().item_results[str(self.item_temp.id)]
        self.assertEqual((entry["status"], entry["reason"]), ("ok", ""))
        page = self.client.get(reverse("checklists"))
        self.assertContains(page, f'name="result_{self.item_temp.id}" value="ok" checked')
        self.assertContains(page, f'name="reason_{self.item_temp.id}" value=""')
        self.assertNotContains(page, "außerhalb Grenzwert")
        # Neu gemessen und im Rahmen: kein Mangel, keine veraltete Begründung.
        self.post_run(**{f"value_{self.item_temp.id}": "5,0"})
        run = ChecklistCompletion.objects.get()
        entry = run.item_results[str(self.item_temp.id)]
        self.assertEqual((entry["status"], entry["value"], entry["reason"]), ("ok", 5.0, ""))
        self.assertFalse(Defect.objects.exists())

    def test_resumed_draft_still_out_of_limits_becomes_not_ok_on_finalize(self):
        self.client.post(self.url, {
            f"result_{self.item_temp.id}": "ok", f"value_{self.item_temp.id}": "9,5",
            f"result_{self.item_seal.id}": "ok", "action": "draft",
        })
        self.post_run(**{f"value_{self.item_temp.id}": "9,5"})
        entry = ChecklistCompletion.objects.get().item_results[str(self.item_temp.id)]
        self.assertEqual(entry["status"], "not_ok")
        self.assertIn("Messwert 9.5 °C außerhalb Grenzwert [2.00..8.00]", entry["reason"])
        self.assertEqual(Defect.objects.count(), 1)

    def test_validation_error_keeps_every_entered_value(self):
        resp = self.post_run(**{
            f"result_{self.item_temp.id}": "ok", f"value_{self.item_temp.id}": "",
            f"result_{self.item_seal.id}": "not_ok", f"reason_{self.item_seal.id}": "Plombe gerissen",
            f"result_{self.item_opt.id}": "na", f"reason_{self.item_opt.id}": "Nicht verbaut",
            "note": "Bitte nachsehen",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Messwert für „Medikamentenkühlschrank Temperatur“ fehlt.", status_code=400)
        self.assertContains(resp, f'name="result_{self.item_seal.id}" value="not_ok" checked', status_code=400)
        self.assertContains(resp, f'name="reason_{self.item_seal.id}" value="Plombe gerissen"', status_code=400)
        self.assertContains(resp, f'name="result_{self.item_opt.id}" value="na" checked', status_code=400)
        self.assertContains(resp, 'value="Bitte nachsehen"', status_code=400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)
        self.assertEqual(Defect.objects.count(), 0)

    def test_final_run_without_any_result_is_rejected(self):
        for data in ({"action": "complete"}, {"note": "x"}, {f"result_{self.foreign_item.id}": "ok"}):
            with self.subTest(data=data):
                resp = self.client.post(self.url, data)
                self.assertEqual(resp.status_code, 400)
                self.assertContains(resp, "Für diesen Abschluss fehlen die Ergebnisse je Prüfpunkt", status_code=400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

    def test_required_items_are_enforced_server_side(self):
        resp = self.post_run(**{f"result_{self.item_seal.id}": None})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Pflichtpunkt „Notfallrucksack Plombe intakt“ ist nicht ausgefüllt.", status_code=400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

    def test_measurement_ok_or_not_ok_needs_a_value_but_na_does_not(self):
        for status in ("ok", "not_ok"):
            with self.subTest(status=status):
                resp = self.post_run(**{f"result_{self.item_temp.id}": status, f"value_{self.item_temp.id}": ""})
                self.assertEqual(resp.status_code, 400)
        resp = self.post_run(**{
            f"result_{self.item_temp.id}": "na", f"value_{self.item_temp.id}": "abc",
            f"reason_{self.item_temp.id}": "Thermometer defekt",
        })
        self.assertEqual(resp.status_code, 302)
        entry = ChecklistCompletion.objects.get().item_results[str(self.item_temp.id)]
        self.assertEqual((entry["status"], entry["value"]), ("na", None))

    def test_non_finite_and_oversized_values_are_rejected_not_500(self):
        for value in ("nan", "NaN", "inf", "-Infinity", "1e999", "1e400", "12345678", "abc"):
            with self.subTest(value=value):
                resp = self.post_run(**{f"value_{self.item_temp.id}": value})
                self.assertEqual(resp.status_code, 400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)
        self.assertEqual(ChecklistDraft.objects.count(), 0)

    def test_limits_of_zero_are_real_limits(self):
        freezer = ChecklistItem.objects.create(
            checklist=self.checklist, text="Gefrierfach", position=4, is_required=False, max_value=Decimal(0),
        )
        page = self.client.get(reverse("checklists"))
        self.assertContains(page, f'name="value_{freezer.id}"')
        self.assertContains(page, "≤ 0,00")
        resp = self.post_run(**{f"result_{freezer.id}": "ok", f"value_{freezer.id}": "0,5"})
        self.assertEqual(resp.status_code, 302)
        entry = ChecklistCompletion.objects.get().item_results[str(freezer.id)]
        self.assertEqual(entry["status"], "not_ok")
        self.assertIn("[—..0.00]", entry["reason"])
        self.assertEqual(entry["max"], "0.00")
        # Untergrenze 0, Obergrenze 8: Anzeige mit beiden Werten.
        self.item_temp.min_value = Decimal(0)
        self.item_temp.save()
        self.assertContains(self.client.get(reverse("checklists")), "0,00–8,00")

    def test_results_keep_a_snapshot_of_the_item(self):
        self.post_run(**{f"value_{self.item_temp.id}": "5"})
        run = ChecklistCompletion.objects.get()
        entry = run.item_results[str(self.item_temp.id)]
        self.assertEqual(
            {key: entry[key] for key in ("text", "unit", "min", "max", "required")},
            {"text": "Medikamentenkühlschrank Temperatur", "unit": "°C", "min": "2.00", "max": "8.00", "required": True},
        )
        # Spätere Änderung am Prüfpunkt ändert den alten Lauf nicht.
        self.item_temp.text = "Kühlschrank (neu)"
        self.item_temp.max_value = Decimal(10)
        self.item_temp.save()
        self.item_opt.delete()
        page = self.client.get(reverse("checklist_run_detail", args=[run.pk]))
        self.assertContains(page, "Medikamentenkühlschrank Temperatur")
        self.assertContains(page, "2.00..8.00")
        self.assertContains(page, "Sonderfahrzeug Zusatzheizung")
        self.assertNotContains(page, "Kühlschrank (neu)")

    def test_unknown_status_is_rejected_for_drafts_too(self):
        resp = self.client.post(self.url, {f"result_{self.item_seal.id}": "bogus", "action": "draft"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(ChecklistDraft.objects.exists())

    def test_legacy_draft_id_parameter_is_ignored_safely(self):
        resp = self.post_run(draft_id="abc")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 1)


class DefectLinkTests(ChecklistBase):
    def not_ok_seal(self, reason="Plombe gerissen"):
        return self.post_run(**{f"result_{self.item_seal.id}": "not_ok", f"reason_{self.item_seal.id}": reason})

    def test_open_defect_is_linked_instead_of_duplicated(self):
        self.not_ok_seal()
        first_run = ChecklistCompletion.objects.get()
        defect = Defect.objects.get()
        response = self.not_ok_seal("immer noch gerissen")
        self.assertEqual(Defect.objects.count(), 1)
        second_run = ChecklistCompletion.objects.exclude(pk=first_run.pk).get()
        entry = second_run.item_results[str(self.item_seal.id)]
        self.assertEqual((entry["defect_id"], entry["defect_linked"]), (defect.pk, True))
        self.assertTrue(DefectEvent.objects.filter(defect=defect, kind=DefectEvent.Kind.UPDATED).exists())
        page = self.client.get(response["Location"])
        self.assertContains(page, "bereits als offener Mangel erfasst")
        # Erledigt: Der nächste Befund ist ein neuer Mangel.
        Defect.objects.filter(pk=defect.pk).update(status=Defect.Status.DONE)
        self.not_ok_seal()
        self.assertEqual(Defect.objects.count(), 2)

    def test_open_defect_of_another_checklist_or_station_is_not_reused(self):
        other_list = Checklist.objects.create(station=self.station, title="Andere Liste")
        other_run = ChecklistCompletion.objects.create(station=self.station, checklist=other_list, completed_by=self.user)
        Defect.objects.create(
            station=self.station, title="Fremd", created_by=self.user, source_checklist_run=other_run,
            source_item_id=self.item_seal.id,
        )
        self.not_ok_seal()
        self.assertEqual(Defect.objects.filter(source_checklist_run__checklist=self.checklist).count(), 1)

    def test_overview_links_new_defects_and_defect_links_back_to_run(self):
        response = self.not_ok_seal()
        defect = Defect.objects.get()
        run = ChecklistCompletion.objects.get()
        page = self.client.get(response["Location"])
        self.assertContains(page, reverse("defect_detail_web", args=[defect.pk]))
        self.assertContains(page, "Mängel aus dem Lauf")
        # Nur einmal: Beim nächsten Aufruf ist der Hinweis weg.
        self.assertNotContains(self.client.get(reverse("checklists")), "Mängel aus dem Lauf")
        detail = self.client.get(reverse("defect_detail_web", args=[defect.pk]))
        self.assertContains(detail, "Aus Checkliste Tägliche Kühlschrank- &amp; Geräteprüfung vom")
        self.assertContains(detail, reverse("checklist_run_detail", args=[run.pk]))

    def test_defect_back_reference_must_stay_in_the_station(self):
        foreign_list = Checklist.objects.get(station=self.other_station)
        foreign_run = ChecklistCompletion.objects.create(station=self.other_station, checklist=foreign_list, completed_by=self.user)
        with self.assertRaises(ValidationError):
            Defect.objects.create(station=self.station, title="x", created_by=self.user, source_checklist_run=foreign_run)


class HistoryExportTests(ChecklistBase):
    def setUp(self):
        super().setUp()
        self.lead = User.objects.create_user(username="leitung", password="test-password-123!", first_name="Lea", last_name="Leitung")
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)

    def test_history_lists_runs_with_summary_and_paper_marker(self):
        self.post_run()
        self.make_run(backfill_at=timezone.now() - timedelta(days=3))
        page = self.client.get(reverse("checklist_history", args=[self.checklist.pk]))
        self.assertContains(page, "2 in Ordnung · 0 nicht in Ordnung · 0 entfällt · 1 ohne Ergebnis")
        self.assertContains(page, "Nachtrag von Papier (Ereignis:")
        self.assertContains(page, "ohne Ergebnis je Punkt")
        self.assertNotContains(page, "Export als CSV")  # Mitglied: kein Export

    def test_history_detail_and_export_are_station_bound(self):
        foreign_list = Checklist.objects.get(station=self.other_station)
        foreign_run = ChecklistCompletion.objects.create(station=self.other_station, checklist=foreign_list, completed_by=self.user)
        self.client.force_login(self.lead)
        self.assertEqual(self.client.get(reverse("checklist_history", args=[foreign_list.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("checklist_run_detail", args=[foreign_run.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("checklist_runs_export", args=[foreign_list.pk])).status_code, 404)

    def test_run_detail_shows_values_limits_and_defect_links(self):
        self.post_run(**{f"value_{self.item_temp.id}": "9,5"})
        run = ChecklistCompletion.objects.get()
        defect = Defect.objects.get()
        page = self.client.get(reverse("checklist_run_detail", args=[run.pk]))
        self.assertContains(page, "9.5 °C")
        self.assertContains(page, "2.00..8.00 °C")
        self.assertContains(page, reverse("defect_detail_web", args=[defect.pk]))

    def export(self, **params):
        return self.client.get(reverse("checklist_runs_export", args=[self.checklist.pk]), params)

    def rows(self, response):
        text = response.content.decode("utf-8").lstrip("﻿")
        return list(csv.reader(io.StringIO(text), delimiter=";"))

    def test_export_for_leads_with_formula_hardening_and_date_range(self):
        self.item_seal.text = "=HYPERLINK(\"x\")"
        self.item_seal.save()
        self.post_run(**{f"result_{self.item_seal.id}": "na", f"reason_{self.item_seal.id}": "+SUM(A1)", "note": "@note"})
        old = self.make_run(when=timezone.now() - timedelta(days=60))
        backfill = self.make_run(backfill_at=timezone.now() - timedelta(days=2), item_results={})
        self.client.force_login(self.lead)
        response = self.export()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = self.rows(response)
        header, body = rows[0], rows[1:]
        self.assertEqual(header[:3], ["Checkliste", "Lauf", "Zeitpunkt"])
        self.assertNotIn(str(old.pk), [row[1] for row in body])
        seal = next(row for row in body if row[6].endswith('HYPERLINK("x")'))
        self.assertEqual(seal[6], "'=HYPERLINK(\"x\")")
        self.assertEqual(seal[13], "'+SUM(A1)")
        self.assertEqual(seal[15], "'@note")
        self.assertEqual(seal[5], "Alex")
        temp = next(row for row in body if row[6] == "Medikamentenkühlschrank Temperatur")
        self.assertEqual((temp[8], temp[9], temp[10], temp[11], temp[12]), ("in Ordnung", "5,2", "°C", "2", "8"))
        paper = [row for row in body if row[1] == str(backfill.pk)]
        self.assertEqual(len(paper), 1)
        self.assertEqual(paper[0][4], "ja")
        self.assertTrue(AuditEvent.objects.filter(action="checklist.exported", object_id=str(self.checklist.pk)).exists())
        # Zeitraum mit dem alten Lauf.
        start = (timezone.localdate() - timedelta(days=61)).isoformat()
        end = (timezone.localdate() - timedelta(days=59)).isoformat()
        ids = [row[1] for row in self.rows(self.export(von=start, bis=end))[1:]]
        self.assertEqual(ids, [str(old.pk)])

    def test_export_refused_for_members_auditors_and_bad_ranges(self):
        self.assertRedirects(self.export(), reverse("checklist_history", args=[self.checklist.pk]), fetch_redirect_response=False)
        auditor = User.objects.create_user(username="pruefer", password="test-password-123!")
        Membership.objects.create(user=auditor, station=self.station, role=Membership.Role.AUDITOR)
        self.client.force_login(auditor)
        self.assertEqual(self.export().status_code, 403)
        self.assertEqual(self.client.get(reverse("checklist_history", args=[self.checklist.pk])).status_code, 403)
        self.client.force_login(self.lead)
        for params in ({"von": "kaputt"}, {"von": "2026-05-02", "bis": "2026-05-01"}):
            with self.subTest(params=params):
                self.assertEqual(self.export(**params).status_code, 302)

    def test_quota_is_a_station_sum_for_leads_only(self):
        self.post_run(**{f"result_{self.item_opt.id}": "ok"})
        self.make_run(item_results={})
        self.assertEqual(per_item_quota(self.station), {"total": 2, "complete": 1, "percent": 50})
        self.assertNotContains(self.client.get(reverse("checklists")), "Läufe mit Ergebnis je Punkt")
        self.client.force_login(self.lead)
        self.assertContains(self.client.get(reverse("checklists")), "Läufe mit Ergebnis je Punkt (30 Tage): 50 %")
        # Läufe älter als 30 Tage zählen nicht mit.
        self.make_run(item_results={}, when=timezone.now() - timedelta(days=40))
        self.assertEqual(per_item_quota(self.station)["total"], 2)
        self.assertFalse(has_result_per_item({}))


class PaperBackfillTests(ChecklistBase):
    def test_backfill_stores_event_time_only_when_ticked(self):
        when = timezone.localtime() - timedelta(days=2)
        resp = self.post_run(is_paper_backfill="1", occurred_at=when.strftime("%Y-%m-%dT%H:%M"))
        self.assertEqual(resp.status_code, 302)
        run = ChecklistCompletion.objects.get()
        self.assertTrue(run.is_paper_backfill)
        self.assertEqual(run.occurred_at, when.replace(second=0, microsecond=0))
        self.assertIn("occurred_at", AuditEvent.objects.get(action="checklist.completed").metadata["fields"])
        self.post_run(occurred_at=when.strftime("%Y-%m-%dT%H:%M"))
        plain = ChecklistCompletion.objects.exclude(pk=run.pk).get()
        self.assertEqual((plain.is_paper_backfill, plain.occurred_at), (False, None))

    def test_backfill_rejects_future_too_old_missing_and_broken_times(self):
        now = timezone.localtime()
        for value, message in (
            ((now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"), "darf nicht in der Zukunft liegen"),
            ((now - timedelta(days=366)).strftime("%Y-%m-%dT%H:%M"), "höchstens 365 Tage"),
            ("", "Für Nachträge von Papier muss ein Ereigniszeitpunkt angegeben werden."),
            ("gestern", "gültigen Ereigniszeitpunkt"),
        ):
            with self.subTest(value=value):
                resp = self.post_run(is_paper_backfill="1", occurred_at=value)
                self.assertContains(resp, message, status_code=400)
                self.assertContains(resp, 'name="is_paper_backfill" value="1" checked', status_code=400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

    def test_last_done_and_schedule_use_the_event_time(self):
        schedule = ChecklistSchedule.objects.create(
            checklist=self.checklist, station=self.station, interval=ChecklistSchedule.Interval.DAILY,
            due_next=timezone.now() + timedelta(hours=6),
        )
        self.post_run()
        schedule.refresh_from_db()
        due_after_run = schedule.due_next
        self.assertGreater(due_after_run, timezone.now() + timedelta(hours=24))
        recent = ChecklistCompletion.objects.get()
        # Nachtrag eines Bogens von vor vier Tagen: früherer Zyklus, Fälligkeit bleibt.
        old = (timezone.localtime() - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M")
        self.post_run(is_paper_backfill="1", occurred_at=old)
        schedule.refresh_from_db()
        self.assertEqual(schedule.due_next, due_after_run)
        # „Zuletzt erledigt“ bleibt der jüngere Lauf, obwohl der Nachtrag später erfasst wurde.
        self.assertEqual(latest_runs([self.checklist])[self.checklist.pk], recent)
        page = self.client.get(reverse("checklists"))
        self.assertNotContains(page, "Nachtrag von Papier (erfasst:")

    def test_backfill_of_an_overdue_schedule_keeps_the_later_backlog_overdue(self):
        # Täglich, seit fünf Tagen überfällig; nachgetragen wird nur der Bogen des ersten Tages.
        due = timezone.now() - timedelta(days=5)
        schedule = ChecklistSchedule.objects.create(
            checklist=self.checklist, station=self.station, interval=ChecklistSchedule.Interval.DAILY, due_next=due,
        )
        sheet = timezone.localtime(due - timedelta(hours=1))
        self.assertEqual(self.post_run(is_paper_backfill="1", occurred_at=sheet.strftime("%Y-%m-%dT%H:%M")).status_code, 302)
        schedule.refresh_from_db()
        # Ein Zyklus weiter, von der Ereigniszeit aus; die vier Tage danach bleiben offen.
        self.assertEqual(schedule.due_next, due + timedelta(days=1))
        self.assertLess(schedule.due_next, timezone.now())
        # Ein Bogen aus einem späteren Zyklus schaltet bis hinter seine Ereigniszeit, nicht bis morgen.
        later = timezone.localtime(due + timedelta(days=2, hours=1))
        self.post_run(is_paper_backfill="1", occurred_at=later.strftime("%Y-%m-%dT%H:%M"))
        schedule.refresh_from_db()
        self.assertEqual(schedule.due_next, due + timedelta(days=3))
        self.assertLess(schedule.due_next, timezone.now())
        # Ein normaler Lauf jetzt beendet den Rückstand.
        self.post_run()
        schedule.refresh_from_db()
        self.assertGreater(schedule.due_next, timezone.now())

    def test_backfill_inside_the_current_cycle_advances_once(self):
        due = timezone.now() + timedelta(hours=10)
        schedule = ChecklistSchedule.objects.create(
            checklist=self.checklist, station=self.station, interval=ChecklistSchedule.Interval.DAILY, due_next=due,
        )
        sheet = timezone.localtime(timezone.now() - timedelta(hours=2))
        self.post_run(is_paper_backfill="1", occurred_at=sheet.strftime("%Y-%m-%dT%H:%M"))
        schedule.refresh_from_db()
        self.assertEqual(schedule.due_next, due + timedelta(days=1))

    def test_api_backfill_of_an_overdue_schedule_reports_overdue(self):
        due = timezone.now() - timedelta(days=5)
        ChecklistSchedule.objects.create(
            checklist=self.checklist, station=self.station, interval=ChecklistSchedule.Interval.DAILY, due_next=due,
        )
        response = self.api_post(reverse("api_v1_checkliste_erledigt", args=[self.checklist.id]), {
            "item_results": {
                str(self.item_temp.id): {"status": "ok", "value": "4,5"},
                str(self.item_seal.id): {"status": "ok"},
            },
            "is_paper_backfill": True,
            "occurred_at": (due - timedelta(hours=1)).isoformat(),
        }, self.token())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["overdue"])
        self.assertEqual(response.json()["due_next"], (due + timedelta(days=1)).isoformat())

    def test_backfill_shown_in_overview_with_event_and_entry_time(self):
        when = timezone.localtime() - timedelta(hours=5)
        self.post_run(is_paper_backfill="1", occurred_at=when.strftime("%Y-%m-%dT%H:%M"))
        page = self.client.get(reverse("checklists"))
        self.assertContains(page, when.strftime("%d.%m.%Y %H:%M"))
        self.assertContains(page, "Nachtrag von Papier (erfasst:")
        run = ChecklistCompletion.objects.get()
        detail = self.client.get(reverse("checklist_run_detail", args=[run.pk]))
        self.assertContains(detail, "Ereignis (Papier)")
        self.assertContains(detail, "Erfasst im Wachbuch")


class ApiTests(ChecklistBase):
    def setUp(self):
        super().setUp()
        self.auth = self.token()
        self.list_url = reverse("api_v1_checklisten")
        self.done_url = reverse("api_v1_checkliste_erledigt", args=[self.checklist.id])
        self.draft_url = reverse("api_v1_checkliste_zwischenstand", args=[self.checklist.id])
        self.full = {
            str(self.item_temp.id): {"status": "ok", "value": "4,5"},
            str(self.item_seal.id): {"status": "ok"},
        }

    def entry(self):
        return next(row for row in self.client.get(self.list_url, **self.auth).json()["results"] if row["id"] == self.checklist.id)

    def test_list_exposes_item_details_and_ignores_drafts_as_last_completion(self):
        self.checklist.requires_personal_login = True
        self.checklist.save()
        self.api_post(self.draft_url, {"item_results": {str(self.item_seal.id): {"status": "na", "reason": "x"}}}, self.auth)
        entry = self.entry()
        self.assertIsNone(entry["last_completed_at"])
        self.assertEqual(entry["items"], [self.item_temp.text, self.item_seal.text, self.item_opt.text])
        self.assertEqual(entry["item_details"][0], {
            "id": self.item_temp.id, "text": "Medikamentenkühlschrank Temperatur", "position": 1, "required": True,
            "unit": "°C", "min": "2.00", "max": "8.00", "measurement": True,
        })
        self.assertFalse(entry["item_details"][1]["measurement"])
        self.assertTrue(entry["requires_personal_login"])
        self.assertEqual(entry["draft"]["item_results"][str(self.item_seal.id)]["status"], "na")
        self.assertEqual(entry["draft"]["updated_by"], "Alex")

    def test_draft_save_resume_and_finalize_via_api(self):
        partial = {str(self.item_temp.id): {"status": "ok", "value": 5}}
        saved = self.api_post(self.draft_url, {"item_results": partial, "note": "Halbzeit"}, self.auth)
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["is_draft"])
        again = self.api_post(self.done_url, {"is_draft": True, "item_results": self.full, "note": "fast fertig"}, self.auth)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(ChecklistDraft.objects.count(), 1)
        resumed = self.client.get(self.draft_url, **self.auth).json()["draft"]
        self.assertEqual(resumed["note"], "fast fertig")
        self.assertEqual(resumed["item_results"][str(self.item_seal.id)]["status"], "ok")
        self.assertEqual(ChecklistCompletion.objects.count(), 0)
        done = self.api_post(self.done_url, {"item_results": self.full}, self.auth)
        self.assertEqual(done.status_code, 201)
        self.assertFalse(ChecklistDraft.objects.exists())
        self.assertIsNone(self.client.get(self.draft_url, **self.auth).json()["draft"])
        self.assertIsNotNone(self.entry()["last_completed_at"])

    def test_api_draft_out_of_limits_keeps_own_status_until_finalize(self):
        out = {str(self.item_temp.id): {"status": "ok", "value": 9.5}, str(self.item_seal.id): {"status": "ok"}}
        self.assertEqual(self.api_post(self.draft_url, {"item_results": out}, self.auth).status_code, 200)
        resumed = self.client.get(self.draft_url, **self.auth).json()["draft"]["item_results"][str(self.item_temp.id)]
        self.assertEqual((resumed["status"], resumed["reason"]), ("ok", ""))
        done = self.api_post(self.done_url, {"item_results": self.full}, self.auth)
        self.assertEqual(done.status_code, 201)
        entry = ChecklistCompletion.objects.get().item_results[str(self.item_temp.id)]
        self.assertEqual((entry["status"], entry["reason"]), ("ok", ""))
        self.assertFalse(Defect.objects.exists())

    def test_final_run_without_results_is_a_400(self):
        for payload in ({}, {"note": "x"}, {"item_results": {}}, {"item_results": None},
                        {"item_results": {str(self.item_opt.id): {"status": ""}}}):
            with self.subTest(payload=payload):
                response = self.api_post(self.done_url, payload, self.auth)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "validation_error")
                self.assertTrue(response.json()["errors"])
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

    def test_malformed_input_is_a_400_never_a_500(self):
        cases = [
            {"item_results": [1, 2]},
            {"item_results": "ok"},
            {"item_results": {str(self.item_temp.id): "ok"}},
            {"item_results": {str(self.item_temp.id): ["ok"]}},
            {"item_results": {str(self.foreign_item.id): {"status": "ok"}}},
            {"item_results": {"abc": {"status": "ok"}}},
            {"item_results": {**self.full, str(self.item_seal.id): {"status": 1}}},
            {"item_results": {**self.full, str(self.item_seal.id): {"status": "ok", "reason": ["x"]}}},
            {"item_results": {**self.full, str(self.item_seal.id): {"status": "bogus"}}},
            {"item_results": {**self.full, str(self.item_temp.id): {"status": "ok", "value": True}}},
            {"item_results": {**self.full, str(self.item_temp.id): {"status": "ok", "value": "nan"}}},
            {"item_results": {**self.full, str(self.item_temp.id): {"status": "ok", "value": 10 ** 400}}},
            {"item_results": self.full, "is_draft": "maybe"},
            {"item_results": self.full, "is_draft": 2},
            {"item_results": self.full, "is_draft": ""},
            {"item_results": self.full, "note": ["x"]},
            {"item_results": self.full, "is_paper_backfill": "yes"},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.api_post(self.done_url, payload, self.auth).status_code, 400)
        for raw in ('{"item_results": {"%d": {"status": "ok", "value": NaN}}}' % self.item_temp.id,
                    '{"item_results": {"%d": {"status": "ok", "value": 1e999}}}' % self.item_temp.id,
                    '{"item_results": {"%d": {"status": "ok", "value": -Infinity}}}' % self.item_temp.id,
                    "[1, 2]", "kaputt"):
            with self.subTest(raw=raw):
                self.assertEqual(self.api_post(self.done_url, None, self.auth, raw_body=raw).status_code, 400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)
        self.assertEqual(ChecklistDraft.objects.count(), 0)

    def test_is_draft_is_parsed_strictly(self):
        # „false“ als Text ist kein Zwischenstand mehr (früher: bool("false") == True).
        response = self.api_post(self.done_url, {"item_results": self.full, "is_draft": "false"}, self.auth)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["is_draft"])
        for value in (True, "true", 1, "1"):
            with self.subTest(value=value):
                response = self.api_post(self.done_url, {"item_results": self.full, "is_draft": value}, self.auth)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["is_draft"])
        self.assertEqual(ChecklistCompletion.objects.count(), 1)

    def test_api_paper_backfill(self):
        when = timezone.now() - timedelta(days=1)
        response = self.api_post(self.done_url, {
            "item_results": self.full, "is_paper_backfill": True, "occurred_at": when.isoformat(),
        }, self.auth)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["is_paper_backfill"])
        run = ChecklistCompletion.objects.get()
        self.assertEqual(run.occurred_at.replace(microsecond=0), when.replace(microsecond=0))
        future = self.api_post(self.done_url, {
            "item_results": self.full, "is_paper_backfill": True, "occurred_at": (timezone.now() + timedelta(days=1)).isoformat(),
        }, self.auth)
        self.assertEqual(future.status_code, 400)

    def test_schedule_is_advanced_once_in_the_same_transaction(self):
        schedule = ChecklistSchedule.objects.create(
            checklist=self.checklist, station=self.station, interval=ChecklistSchedule.Interval.WEEKLY,
            due_next=timezone.now() + timedelta(days=1),
        )
        expected = schedule.due_next + timedelta(days=7)
        response = self.api_post(self.done_url, {"item_results": self.full}, self.auth)
        self.assertEqual(response.status_code, 201)
        schedule.refresh_from_db()
        self.assertEqual(schedule.due_next, expected)
        self.assertEqual(response.json()["due_next"], expected.isoformat())
        self.assertFalse(response.json()["overdue"])

    def test_draft_endpoint_is_station_bound_and_needs_scopes(self):
        foreign_list = Checklist.objects.get(station=self.other_station)
        url = reverse("api_v1_checkliste_zwischenstand", args=[foreign_list.pk])
        self.assertEqual(self.client.get(url, **self.auth).status_code, 404)
        self.assertEqual(self.api_post(url, {"item_results": {}}, self.auth).status_code, 404)
        read_only = self.token(raw="wb_test_028_checklist_readonly_12345678", scopes=("read:checklists",))
        self.assertEqual(self.client.get(self.draft_url, **read_only).status_code, 200)
        self.assertEqual(self.api_post(self.draft_url, {"item_results": {}}, read_only).status_code, 403)


class AppendOnlyQueryTests(PostgresLockAssertions, ChecklistBase):
    """Kein Pfad ändert oder löscht Zeilen in core_checklistcompletion (Entscheidung 1)."""

    def test_web_and_api_draft_resume_and_finalize_only_insert(self):
        auth = self.token()
        draft_form = {
            f"result_{self.item_seal.id}": "not_ok", f"reason_{self.item_seal.id}": "gerissen",
            f"value_{self.item_temp.id}": "4", "action": "draft",
        }
        self.post_run()  # ein endgültiger Lauf existiert schon
        with CaptureQueriesContext(connection) as web, record_row_locks() as locks:
            self.assertEqual(self.client.post(self.url, draft_form).status_code, 302)
            self.assertEqual(self.client.post(self.url, {**draft_form, "note": "zweimal"}).status_code, 302)
            self.assertEqual(self.client.get(reverse("checklists")).status_code, 200)
            self.assertEqual(self.post_run(**{f"result_{self.item_seal.id}": "not_ok", f"reason_{self.item_seal.id}": "gerissen"}).status_code, 302)
            self.assertEqual(self.client.get(reverse("checklists")).status_code, 200)
        self.assertEqual(completion_writes(web.captured_queries), [])
        self.assertEqual(completion_inserts(web.captured_queries), 1)
        self.assert_postgres_safe(locks)

        done_url = reverse("api_v1_checkliste_erledigt", args=[self.checklist.id])
        draft_url = reverse("api_v1_checkliste_zwischenstand", args=[self.checklist.id])
        full = {str(self.item_temp.id): {"status": "ok", "value": 5}, str(self.item_seal.id): {"status": "not_ok", "reason": "x"}}
        with CaptureQueriesContext(connection) as api, record_row_locks() as locks:
            self.assertEqual(self.api_post(draft_url, {"item_results": full}, auth).status_code, 200)
            self.assertEqual(self.api_post(done_url, {"item_results": full, "is_draft": True}, auth).status_code, 200)
            self.assertEqual(self.client.get(draft_url, **auth).status_code, 200)
            self.assertEqual(self.client.get(reverse("api_v1_checklisten"), **auth).status_code, 200)
            self.assertEqual(self.api_post(done_url, {"item_results": full}, auth).status_code, 201)
        self.assertEqual(completion_writes(api.captured_queries), [])
        self.assertEqual(completion_inserts(api.captured_queries), 1)
        self.assert_postgres_safe(locks)
        self.assertEqual(ChecklistCompletion.objects.count(), 3)
        self.assertEqual(Defect.objects.count(), 1)  # zweiter und dritter Befund verweisen auf den offenen Mangel

    def test_app_role_revokes_writes_on_runs_but_not_on_drafts(self):
        tables = app_role_read_only_tables()
        self.assertIn(COMPLETION_TABLE, tables)
        self.assertNotIn("core_checklistdraft", tables)

    def test_query_check_recognises_writes(self):
        for sql in ('UPDATE "core_checklistcompletion" SET "note" = %s WHERE "id" = %s',
                    'DELETE FROM "core_checklistcompletion" WHERE "id" IN (%s)',
                    'SELECT "id" FROM "core_checklistcompletion" WHERE "id" = %s FOR UPDATE'):
            with self.subTest(sql=sql):
                self.assertEqual(completion_writes([{"sql": sql}]), [sql])
        harmless = ('UPDATE "core_checklistdraft" SET "note" = %s', 'SELECT 1 FROM "core_checklist" FOR UPDATE',
                    'INSERT INTO "core_checklistcompletion" ("note") VALUES (%s)')
        self.assertEqual(completion_writes([{"sql": sql} for sql in harmless]), [])


@skipUnless(connection.vendor == "postgresql", "nur PostgreSQL prüft Tabellenrechte")
class AppRolePostgresTests(ChecklistBase):
    """Zwischenstand → Abschluss unter der echten App-Rolle nach ``grant_database_access``."""

    ROLES = {
        "APP_DB_USER": "ww_p1_probe_app",
        "FEED_DB_USER": "ww_p1_probe_feed",
        "BACKUP_DB_USER": "ww_p1_probe_backup",
        "PUSH_DB_USER": "ww_p1_probe_push",
    }

    def grant(self):
        import os
        from unittest import mock

        from django.core.management import call_command

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user, current_database()")
            owner, database = cursor.fetchone()
        env = {**self.ROLES, "POSTGRES_USER": owner, "POSTGRES_DB": database}
        try:
            with transaction.atomic(), mock.patch.dict(os.environ, env):
                call_command("grant_database_access", stdout=io.StringIO())
        except DatabaseError as exc:
            self.skipTest(f"Rollen lassen sich hier nicht anlegen: {exc}")

    def test_draft_then_final_run_as_app_role(self):
        self.grant()
        auth = self.token()
        done_url = reverse("api_v1_checkliste_erledigt", args=[self.checklist.id])
        full = {str(self.item_temp.id): {"status": "ok", "value": 5}, str(self.item_seal.id): {"status": "not_ok", "reason": "x"}}
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {self.ROLES['APP_DB_USER']}")
            try:
                draft = {f"result_{self.item_seal.id}": "ok", "action": "draft"}
                self.assertEqual(self.client.post(self.url, draft).status_code, 302)
                self.assertEqual(self.client.post(self.url, {**draft, "note": "zweiter Stand"}).status_code, 302)
                self.assertEqual(self.client.get(reverse("checklists")).status_code, 200)
                self.assertEqual(self.post_run().status_code, 302)
                self.assertEqual(self.api_post(done_url, {"item_results": full, "is_draft": True}, auth).status_code, 200)
                self.assertEqual(self.api_post(done_url, {"item_results": full}, auth).status_code, 201)
                # Die Rolle darf Läufe wirklich nicht ändern oder löschen.
                with self.assertRaises(DatabaseError), transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"UPDATE {COMPLETION_TABLE} SET note = 'x'")
                with self.assertRaises(DatabaseError), transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"DELETE FROM {COMPLETION_TABLE}")
            finally:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("RESET ROLE")
                except DatabaseError:
                    pass  # abgebrochene Transaktion: das Zurückrollen hebt SET ROLE auf
        self.assertEqual(ChecklistCompletion.objects.count(), 2)
        self.assertFalse(ChecklistDraft.objects.exists())


@override_settings(TERMINAL_ENABLED=True, TERMINAL_IDLE_SECONDS=120)
class TerminalTests(ChecklistBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="chefin", password="x-test-pass-123", first_name="Chefin")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.raw = "terminal-secret-token-value"
        StationTerminal.objects.create(
            station=self.station, label="Fahrzeughalle", token_hash=hash_secret(self.raw), created_by=self.admin,
        )
        self.code_record = set_station_code(self.station, TERMINAL_CODE, set_by=self.admin)
        self.checklist.requires_personal_login = True
        self.checklist.save()
        self.client.logout()
        self.client.cookies[COOKIE_NAME] = self.raw
        self.client.post(reverse("terminal_home"), data={"code": TERMINAL_CODE})

    def test_evidence_checklist_is_blocked_on_the_terminal_web(self):
        page = self.client.get(reverse("checklists"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "kann am gemeinsamen Wachenterminal nicht abgeschlossen werden")
        self.assertContains(page, 'value="complete" disabled')
        for action in ("complete", "draft"):
            with self.subTest(action=action):
                self.assertEqual(self.post_run(action=action).status_code, 403)
        self.assertFalse(ChecklistCompletion.objects.exists())
        self.assertFalse(ChecklistDraft.objects.exists())

    def test_evidence_checklist_is_blocked_for_the_service_account_via_api(self):
        # Das Dienstkonto hat kein App-Token; falls doch eins entstünde, sperrt auch die App.
        self.client.logout()
        self.client.cookies.pop(COOKIE_NAME, None)
        service = self.code_record.service_user
        auth = self.token(user=service, raw="wb_test_028_terminal_service_1234567890")
        full = {str(self.item_temp.id): {"status": "ok", "value": 5}, str(self.item_seal.id): {"status": "ok"}}
        done = reverse("api_v1_checkliste_erledigt", args=[self.checklist.id])
        draft = reverse("api_v1_checkliste_zwischenstand", args=[self.checklist.id])
        self.assertEqual(self.api_post(done, {"item_results": full}, auth).status_code, 403)
        self.assertEqual(self.api_post(draft, {"item_results": full}, auth).status_code, 403)
        self.checklist.requires_personal_login = False
        self.checklist.save()
        backfill = {"item_results": full, "is_paper_backfill": True, "occurred_at": (timezone.now() - timedelta(days=1)).isoformat()}
        self.assertEqual(self.api_post(done, backfill, auth).status_code, 403)
        self.assertFalse(ChecklistCompletion.objects.exists())

    def test_terminal_can_run_normal_checklists_but_not_backfill_or_history(self):
        self.checklist.requires_personal_login = False
        self.checklist.save()
        page = self.client.get(reverse("checklists"))
        self.assertNotContains(page, 'name="is_paper_backfill"')
        self.assertNotContains(page, reverse("checklist_history", args=[self.checklist.pk]))
        when = (timezone.localtime() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.assertEqual(self.post_run(is_paper_backfill="1", occurred_at=when).status_code, 403)
        self.assertEqual(self.post_run().status_code, 302)
        run = ChecklistCompletion.objects.get()
        self.assertFalse(run.is_paper_backfill)
        for url in (reverse("checklist_history", args=[self.checklist.pk]),
                    reverse("checklist_run_detail", args=[run.pk]),
                    reverse("checklist_runs_export", args=[self.checklist.pk])):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), reverse("terminal_menu"), fetch_redirect_response=False)


class HousekeepingTests(ChecklistBase):
    def test_drafts_untouched_for_30_days_are_deleted(self):
        other = Checklist.objects.create(station=self.station, title="Zweite")
        stale = ChecklistDraft.objects.create(station=self.station, checklist=self.checklist, created_by=self.user, updated_by=self.user)
        fresh = ChecklistDraft.objects.create(station=self.station, checklist=other, created_by=self.user, updated_by=self.user)
        ChecklistDraft.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=31))
        ChecklistDraft.objects.filter(pk=fresh.pk).update(updated_at=timezone.now() - timedelta(days=29))
        counts, failed = run_housekeeping()
        self.assertEqual(failed, [])
        self.assertEqual(counts["Checklisten-Zwischenstände"], 1)
        self.assertEqual(list(ChecklistDraft.objects.values_list("pk", flat=True)), [fresh.pk])

    def test_one_draft_per_checklist_and_station(self):
        from django.db import IntegrityError

        ChecklistDraft.objects.create(station=self.station, checklist=self.checklist, created_by=self.user, updated_by=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChecklistDraft.objects.create(station=self.station, checklist=self.checklist, created_by=self.user, updated_by=self.user)


class QuickActionScriptTests(ChecklistBase):
    """„Alle übrigen Punkte in Ordnung“: Schaltfläche nur mit JavaScript, Messpunkte bleiben unberührt."""

    HARNESS = r"""
const fs = require("fs");
function radio(value, checked) { return { type: "radio", value: value, checked: checked, disabled: false }; }
function row(measurement, chosen) {
  const radios = ["ok", "not_ok", "na"].map(v => radio(v, v === chosen));
  return {
    radios: radios,
    hasAttribute: name => name === "data-measurement" ? measurement : name === "data-item-id",
    querySelectorAll: () => radios,
    querySelector: selector => radios.find(r => selector.indexOf('value="' + r.value + '"') !== -1) || null,
  };
}
const rows = [row(false, ""), row(true, ""), row(false, "na"), row(false, "")];
let handler = null;
const button = { hidden: true, addEventListener: (name, fn) => { handler = fn; } };
const status = { textContent: "" };
const form = {
  getAttribute: name => name === "data-all-ok-done" ? "DONE" : "NONE",
  querySelector: selector => selector === "[data-checklist-all-ok]" ? button
    : selector === "[data-checklist-all-ok-status]" ? status : null,
  querySelectorAll: () => rows,
};
global.document = { querySelectorAll: () => [form] };
eval(fs.readFileSync(process.argv[1], "utf8"));
handler();
const state = rows.map(r => (r.radios.find(x => x.checked) || { value: "" }).value);
handler();
console.log(JSON.stringify({ hidden: button.hidden, state: state, status: status.textContent }));
"""

    def test_button_is_progressive_and_template_marks_measurement_rows(self):
        page = self.client.get(reverse("checklists"))
        self.assertContains(page, "data-checklist-all-ok hidden")
        self.assertContains(page, "core/checklists.js")
        self.assertContains(page, f'data-item-id="{self.item_temp.id}" data-measurement')
        self.assertContains(page, f'data-item-id="{self.item_seal.id}">')

    def test_script_sets_only_open_items_without_measurement(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht installiert")
        script = Path(settings.BASE_DIR) / "core" / "static" / "core" / "checklists.js"
        result = subprocess.run([node, "-e", self.HARNESS, str(script)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        data = json.loads(result.stdout)
        self.assertFalse(data["hidden"])
        self.assertEqual(data["state"], ["ok", "", "na", "ok"])
        self.assertEqual(data["status"], "NONE")  # zweiter Klick: nichts mehr offen


class DraftMigrationTests(TransactionTestCase):
    """0077: bisherige Zwischenstände wandern in ChecklistDraft, Rückweg stellt sie wieder her."""

    migration = importlib.import_module("core.migrations.0077_checklist_drafts_paper_backfill")
    before = [dep for dep in migration.Migration.dependencies if dep[0] == "core"]
    after = [("core", "0077_checklist_drafts_paper_backfill")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def test_legacy_drafts_move_and_come_back(self):
        old = self._migrate(self.before)
        OldStation = old.get_model("core", "Station")
        OldUser = old.get_model("auth", "User")
        OldChecklist = old.get_model("core", "Checklist")
        OldCompletion = old.get_model("core", "ChecklistCompletion")
        station = OldStation.objects.create(name="Mig", slug="mig-checklisten")
        anna = OldUser.objects.create(username="mig-anna")
        ben = OldUser.objects.create(username="mig-ben")
        first = OldChecklist.objects.create(station=station, title="Kühlschrank")
        second = OldChecklist.objects.create(station=station, title="Rundgang")
        now = timezone.now()

        def row(checklist, user, is_draft, age, note):
            obj = OldCompletion.objects.create(station=station, checklist=checklist, completed_by=user, note=note,
                                               is_draft=is_draft, item_results={"1": {"status": "ok"}})
            OldCompletion.objects.filter(pk=obj.pk).update(created_at=now - timedelta(days=age))
            return obj

        final = row(first, anna, False, 5, "fertig")
        row(first, anna, True, 3, "alter Stand")
        row(first, ben, True, 1, "neuer Stand")
        row(second, ben, True, 2, "Rundgang halb")

        new = self._migrate(self.after)
        Draft = new.get_model("core", "ChecklistDraft")
        Completion = new.get_model("core", "ChecklistCompletion")
        self.assertEqual(list(Completion.objects.values_list("pk", flat=True)), [final.pk])
        drafts = {d.checklist_id: d for d in Draft.objects.all()}
        self.assertEqual(set(drafts), {first.pk, second.pk})
        self.assertEqual((drafts[first.pk].note, drafts[first.pk].updated_by_id), ("neuer Stand", ben.pk))
        self.assertEqual(drafts[first.pk].item_results, {"1": {"status": "ok"}})
        self.assertLess(drafts[second.pk].updated_at, now - timedelta(days=1))
        self.assertEqual(Completion.objects.get().is_paper_backfill, False)

        back = self._migrate(self.before)
        Completion = back.get_model("core", "ChecklistCompletion")
        self.assertEqual(Completion.objects.filter(is_draft=False).count(), 1)
        self.assertEqual(
            sorted(Completion.objects.filter(is_draft=True).values_list("note", flat=True)),
            ["Rundgang halb", "neuer Stand"],
        )
