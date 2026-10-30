"""0.27, Entscheidung D1: einmalige Bereinigung der Altdaten (cleanup_legacy_data).

Trockenlauf als Standard; ``--apply --user`` führt aus. Umfang nach
Betreiberentscheid: frühere Einsatzphasen im Audit (2/3/4 → 1, reine
Phasenwechsel gelöscht), IP/Browser alter Lesebestätigungen, Bemerkungen von
Desinfektionen vor Migration 0067. Je Wache ein Protokoll im Audit.
"""
from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock, skipUnless

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import legacy_cleanup
from core.fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle
from core.models import AuditEvent, Membership, Station
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision

ACTION = "fleet.status_changed"


def status_event(station, actor, frm, to, *, object_type="Vehicle", action=ACTION):
    return AuditEvent.objects.create(
        station=station, actor=actor, action=action, object_type=object_type, object_id="7",
        metadata={"fields": ["tactical_status"], "from": frm, "to": to},
    )


class CleanupFixture(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Alt", slug="wache-alt", fleet_enabled=True)
        self.other = Station.objects.create(name="Wache Nachbar", slug="wache-nachbar", fleet_enabled=True)
        self.admin = User.objects.create_user("alt-admin", first_name="Ada", password="pw-123456789")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.root = User.objects.create_superuser("alt-root", password="pw-123456789")
        self.crew = User.objects.create_user("alt-crew", password="pw-123456789")
        Membership.objects.create(user=self.crew, station=self.station, role=Membership.Role.MEMBER)

        # Audit: frühere Einsatzphasen und neutrale Wechsel
        self.events = {
            "3to4": status_event(self.station, self.crew, "3", "4"),        # nur Phasenwechsel → gelöscht
            "1to2": status_event(self.station, self.crew, "1", "2"),        # nur Phasenwechsel → gelöscht
            "2to6": status_event(self.station, self.crew, "2", "6"),        # → 1 → 6
            "6tows": status_event(self.station, self.crew, "6", "workshop"),  # bleibt
            "1todis": status_event(self.station, self.crew, "1", "disinfection"),  # bleibt
            "distoready": status_event(self.station, self.crew, "disinfection", "ready"),  # bleibt
            "4todis": status_event(self.station, self.crew, "4", "disinfection"),  # → 1 → disinfection
        }
        self.untouched = [
            status_event(self.station, self.crew, "3", "6", action="defect.status_changed", object_type="Defect"),
            status_event(self.station, self.crew, "2", "4", action="asset.status_changed", object_type="StationAsset"),
            status_event(self.station, self.crew, "3", "4", action="handover.status_changed",
                         object_type="HandoverEntry"),
            status_event(self.station, self.crew, "3", "4", object_type="Device"),
        ]
        self.neighbour_event = status_event(self.other, None, "3", "4")

        # Lesebestätigung mit Altbestand (IP/Browser) und eine ohne
        sop = SOPDocument.objects.create(station=self.station, slug="sop-alt", doc_number="SOP-1", title="T",
                                         created_by=self.admin)
        revision = SOPRevision.objects.create(sop=sop, version_label="1", content_markdown="x", change_summary="x",
                                              approved_by=self.admin)
        self.legacy_receipt = SOPReceipt.objects.create(station=self.station, sop=sop, revision=revision,
                                                        user=self.crew, ip_address="198.51.100.7",
                                                        user_agent="LegacyBrowser/1.0")
        self.clean_receipt = SOPReceipt.objects.create(station=self.station, sop=sop, revision=revision,
                                                       user=self.admin)
        other_sop = SOPDocument.objects.create(station=self.other, slug="sop-n", doc_number="SOP-N", title="N",
                                               created_by=self.admin)
        other_rev = SOPRevision.objects.create(sop=other_sop, version_label="1", content_markdown="x",
                                               change_summary="x", approved_by=self.admin)
        self.neighbour_receipt = SOPReceipt.objects.create(station=self.other, sop=other_sop, revision=other_rev,
                                                           user=self.crew, user_agent="Nachbar/1.0")

        # Desinfektionsbemerkungen vor und nach dem Einspielen von 0067
        applied = MigrationRecorder.Migration.objects.get(app="core", name="0067_fleet_neutral_status").applied
        vehicle = Vehicle.objects.create(station=self.station, slug="rtw-alt", call_sign="RTW Alt",
                                         license_plate="RW-ALT")
        agent = DisinfectantMaster.objects.create(station=self.station, name="Mittel Alt")
        common = {"station": self.station, "vehicle": vehicle, "performed_by": self.crew, "disinfectant": agent,
                  "lock_timer_applied": False}
        self.old_note = DisinfectionProtocol.objects.create(started_at=applied - timedelta(days=3),
                                                            notes="Transport nach Station 4", **common)
        self.new_note = DisinfectionProtocol.objects.create(started_at=applied + timedelta(minutes=5),
                                                            notes="Trage zusätzlich gewischt", **common)

    def run_command(self, *args):
        out = StringIO()
        call_command("cleanup_legacy_data", *args, stdout=out)
        return out.getvalue()

    def snapshot(self):
        return (
            sorted((e.pk, json.dumps(e.metadata, sort_keys=True)) for e in AuditEvent.objects.all()),
            sorted(SOPReceipt.objects.values_list("pk", "ip_address", "user_agent")),
            sorted(DisinfectionProtocol.objects.values_list("pk", "notes")),
        )


class DryRunTests(CleanupFixture):
    def test_dry_run_reports_and_changes_nothing(self):
        before = self.snapshot()
        output = self.run_command()
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Trockenlauf – es wird nichts geändert.", output)
        self.assertIn("Wache Alt (wache-alt):", output)
        self.assertIn("Audit-Einträge mit früheren Einsatzphasen, werden neutral: 2", output)
        self.assertIn("Audit-Einträge nur mit Wechsel der Einsatzphase, werden gelöscht: 2", output)
        self.assertIn("Lesebestätigungen mit IP-Adresse oder Browser: 1", output)
        self.assertIn("Desinfektionsbemerkungen aus der Zeit vor 0.26.1: 1", output)
        self.assertIn("Wache Nachbar (wache-nachbar):", output)
        self.assertIn("--apply --user", output)
        self.assertFalse(AuditEvent.objects.filter(action=legacy_cleanup.CLEANUP_ACTION).exists())

    def test_survey_counts_per_station(self):
        found = legacy_cleanup.survey([self.station, self.other])
        own, neighbour = found[self.station.pk], found[self.other.pk]
        self.assertEqual((own.vehicle_status_events, own.mission_phase_events, own.sop_receipts,
                          own.disinfection_notes), (2, 2, 1, 1))
        self.assertEqual((neighbour.vehicle_status_events, neighbour.mission_phase_events,
                          neighbour.sop_receipts, neighbour.disinfection_notes), (0, 1, 1, 0))


class ApplyTests(CleanupFixture):
    def apply_as_root(self):
        return self.run_command("--apply", "--user", "alt-root")

    def test_apply_neutralises_mission_phases_and_deletes_pure_phase_changes(self):
        originals = {key: (e.created_at, e.actor_id, e.action, e.object_id) for key, e in self.events.items()}
        self.apply_as_root()
        self.assertFalse(AuditEvent.objects.filter(pk__in=[self.events["3to4"].pk, self.events["1to2"].pk]).exists())
        expected = {
            "2to6": ("1", "6"), "6tows": ("6", "workshop"), "1todis": ("1", "disinfection"),
            "distoready": ("disinfection", "ready"), "4todis": ("1", "disinfection"),
        }
        for key, (frm, to) in expected.items():
            with self.subTest(event=key):
                event = AuditEvent.objects.get(pk=self.events[key].pk)
                self.assertEqual((event.metadata["from"], event.metadata["to"]), (frm, to))
                self.assertEqual(event.metadata["fields"], ["tactical_status"])
                self.assertEqual((event.created_at, event.actor_id, event.action, event.object_id), originals[key])
        for event in AuditEvent.objects.filter(action=ACTION, object_type="Vehicle"):
            self.assertNotIn(event.metadata.get("from"), ("2", "3", "4"))
            self.assertNotIn(event.metadata.get("to"), ("2", "3", "4"))

    def test_apply_leaves_other_actions_untouched(self):
        before = {e.pk: e.metadata for e in self.untouched}
        self.apply_as_root()
        for pk, metadata in before.items():
            self.assertEqual(AuditEvent.objects.get(pk=pk).metadata, metadata)

    def test_apply_clears_sop_receipt_ip_and_user_agent(self):
        before = SOPReceipt.objects.filter(pk=self.legacy_receipt.pk).values(
            "user_id", "revision_id", "acknowledged_at").get()
        count = SOPReceipt.objects.count()
        self.apply_as_root()
        receipt = SOPReceipt.objects.get(pk=self.legacy_receipt.pk)
        self.assertEqual((receipt.ip_address, receipt.user_agent), (None, ""))
        self.assertEqual({"user_id": receipt.user_id, "revision_id": receipt.revision_id,
                          "acknowledged_at": receipt.acknowledged_at}, before)
        self.assertEqual(SOPReceipt.objects.count(), count)

    def test_apply_clears_only_notes_from_before_0067(self):
        self.apply_as_root()
        self.old_note.refresh_from_db()
        self.new_note.refresh_from_db()
        self.assertEqual(self.old_note.notes, "")
        self.assertEqual(self.new_note.notes, "Trage zusätzlich gewischt")
        self.assertEqual(DisinfectionProtocol.objects.count(), 2)

    def test_one_record_per_station_with_counts_and_actor(self):
        self.apply_as_root()
        record = AuditEvent.objects.get(station=self.station, action=legacy_cleanup.CLEANUP_ACTION)
        self.assertEqual((record.actor, record.object_type, record.object_id), (self.root, "Station", str(self.station.pk)))
        self.assertEqual(record.metadata["changes"], {
            "legacy_vehicle_status": {"from": 2, "to": 0},
            "legacy_mission_phases": {"from": 2, "to": 0},
            "legacy_sop_receipts": {"from": 1, "to": 0},
            "legacy_disinfection_notes": {"from": 1, "to": 0},
        })
        text = json.dumps(record.metadata, ensure_ascii=False)
        for secret in ("198.51.100.7", "LegacyBrowser", "Transport", "Wache Alt"):
            self.assertNotIn(secret, text)
        neighbour = AuditEvent.objects.get(station=self.other, action=legacy_cleanup.CLEANUP_ACTION)
        self.assertEqual(neighbour.metadata["changes"]["legacy_mission_phases"], {"from": 1, "to": 0})

        self.client.force_login(self.admin)
        page = self.client.get(reverse("audit_log"))
        self.assertContains(page, "Altdaten einmalig bereinigt")
        self.assertContains(page, "Audit-Einträge mit früheren Einsatzphasen (neutralisiert): 2 → 0")
        self.assertContains(page, "Lesebestätigungen mit IP-Adresse oder Browser: 1 → 0")
        self.assertContains(page, "Fahrzeugzustand: Einsatzbereit → Außer Dienst")
        # Das Protokoll der Nachbarwache bleibt dort (stationsgebunden).
        auditor = User.objects.create_user("alt-auditor", password="pw-123456789")
        Membership.objects.create(user=auditor, station=self.other, role=Membership.Role.AUDITOR)
        self.client.force_login(auditor)
        page = self.client.get(reverse("audit_log")).content.decode()
        self.assertIn("Altdaten einmalig bereinigt", page)
        self.assertNotIn("(neutralisiert): 2 → 0", page)

    def test_second_run_is_idempotent(self):
        self.apply_as_root()
        snapshot = self.snapshot()
        output = self.apply_as_root()
        self.assertEqual(self.snapshot(), snapshot)
        self.assertEqual(AuditEvent.objects.filter(action=legacy_cleanup.CLEANUP_ACTION).count(), 2)
        self.assertIn("werden neutral: 0", output)
        found = legacy_cleanup.survey([self.station, self.other])
        self.assertTrue(all(counts.total == 0 for counts in found.values()))

    def test_station_admin_cleans_only_own_station(self):
        output = self.run_command("--apply", "--user", "alt-admin")
        self.assertIn("Wache Nachbar (wache-nachbar): übersprungen", output)
        self.assertEqual(AuditEvent.objects.get(pk=self.neighbour_event.pk).metadata["from"], "3")
        self.assertEqual(SOPReceipt.objects.get(pk=self.neighbour_receipt.pk).user_agent, "Nachbar/1.0")
        self.assertFalse(AuditEvent.objects.filter(station=self.other, action=legacy_cleanup.CLEANUP_ACTION).exists())
        record = AuditEvent.objects.get(station=self.station, action=legacy_cleanup.CLEANUP_ACTION)
        self.assertEqual(record.actor, self.admin)

    def test_station_option_limits_the_scope(self):
        self.run_command("--apply", "--user", "alt-root", "--station", "wache-nachbar")
        self.assertFalse(AuditEvent.objects.filter(pk=self.neighbour_event.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(pk=self.events["3to4"].pk).exists())
        with self.assertRaises(CommandError):
            self.run_command("--station", "gibt-es-nicht")

    def test_demo_sandbox_stations_are_skipped(self):
        from core.demo_models import DemoSandbox

        sandbox_station = Station.objects.create(name="Demo-Besuch", slug="demo-besuch")
        DemoSandbox.objects.create(station=sandbox_station, token="t" * 16)
        event = status_event(sandbox_station, None, "3", "4")
        self.apply_as_root()
        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())

    def test_apply_requires_valid_admin_user(self):
        inactive = User.objects.create_user("alt-inactive", password="pw-123456789", is_active=False)
        Membership.objects.create(user=inactive, station=self.station, role=Membership.Role.ADMIN)
        before = self.snapshot()
        for args in (("--apply",), ("--apply", "--user", "gibt-es-nicht"), ("--apply", "--user", "alt-inactive"),
                     ("--apply", "--user", "alt-crew")):
            with self.subTest(args=args):
                with self.assertRaises(CommandError):
                    self.run_command(*args)
                self.assertEqual(self.snapshot(), before)
        self.assertFalse(AuditEvent.objects.filter(action=legacy_cleanup.CLEANUP_ACTION).exists())

    def test_apply_refused_without_update_privilege(self):
        before = self.snapshot()
        missing = ["UPDATE core_auditevent", "DELETE core_auditevent", "UPDATE core_sopreceipt"]
        with mock.patch.object(legacy_cleanup, "missing_privileges", return_value=missing):
            with self.assertRaises(CommandError) as caught:
                self.apply_as_root()
        message = str(caught.exception)
        self.assertIn("docker compose run --rm migrate python manage.py cleanup_legacy_data --apply", message)
        self.assertIn("UPDATE core_sopreceipt", message)
        self.assertEqual(self.snapshot(), before)

    @skipUnless(connection.vendor == "postgresql", "nur PostgreSQL prüft Tabellenrechte")
    def test_missing_privileges_detects_the_app_role_on_postgresql(self):
        # Wie die App-Rolle: Audit nur lesen und anlegen (REVOKE UPDATE, DELETE).
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("CREATE ROLE ww_cleanup_probe NOLOGIN")
        except DatabaseError:
            self.skipTest("Datenbank-Benutzer darf keine Rollen anlegen")
        with connection.cursor() as cursor:
            cursor.execute("GRANT SELECT, INSERT ON core_auditevent, core_sopreceipt TO ww_cleanup_probe")
            cursor.execute("GRANT UPDATE ON core_sopreceipt, core_disinfectionprotocol TO ww_cleanup_probe")
            cursor.execute("SET ROLE ww_cleanup_probe")
            try:
                missing = legacy_cleanup.missing_privileges()
            finally:
                cursor.execute("RESET ROLE")
        self.assertEqual(missing, ["UPDATE core_auditevent", "DELETE core_auditevent"])
        self.assertEqual(legacy_cleanup.missing_privileges(), [])

    def test_required_privileges_cover_all_touched_tables(self):
        self.assertEqual(set(legacy_cleanup._required_privileges()), {
            ("core_auditevent", "UPDATE"), ("core_auditevent", "DELETE"),
            ("core_sopreceipt", "UPDATE"), ("core_disinfectionprotocol", "UPDATE"),
        })

    def test_failure_rolls_back_everything(self):
        before = self.snapshot()
        with mock.patch("core.services.audit", side_effect=RuntimeError("Abbruch")):
            with self.assertRaises(RuntimeError):
                legacy_cleanup.apply(self.root, [self.station])
        self.assertEqual(self.snapshot(), before)


class NeutralMetadataTests(TestCase):
    def test_only_top_level_mission_phases_are_rewritten(self):
        self.assertEqual(legacy_cleanup.neutral_vehicle_metadata({"from": "1", "to": "6"}), (None, False))
        self.assertEqual(legacy_cleanup.neutral_vehicle_metadata({"from": "4", "to": "6"}),
                         ({"from": "1", "to": "6"}, False))
        self.assertEqual(legacy_cleanup.neutral_vehicle_metadata({"from": "2", "to": "3"}),
                         ({"from": "1", "to": "1"}, True))
        self.assertEqual(legacy_cleanup.neutral_vehicle_metadata({"from": 3, "to": "x"}), (None, False))
        self.assertEqual(legacy_cleanup.neutral_vehicle_metadata(["3"]), (None, False))
        nested = {"from": "1", "to": "ready", "changes": {"x": {"from": "3"}}}
        self.assertEqual(legacy_cleanup.neutral_vehicle_metadata(nested), (None, False))
