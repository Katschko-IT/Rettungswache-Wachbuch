"""0.27 „Pilotfähig“, Paket C1 – Fuhrpark ohne Einsatz- und Erregerbezug.

1. Auswahlwerte von Fahrzeug und Desinfektion (messbares Ziel der Roadmap).
2. Fünf Fahrzeugzustände unter „Fahrzeugzustand“, mit „Eingeschränkt“.
3. Desinfektionsstufen statt Erregerarten; Migration 0069 ordnet verlustfrei zu.
"""
from __future__ import annotations

import importlib
import json
import re
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.disinfection_plan import active_levels, ensure_default_levels
from core.display import display_payload
from core.fleet_forms import DisinfectionProtocolForm
from core.fleet_models import (
    DEFAULT_LEVEL_NAMES,
    PATHOGEN_PATTERN,
    DisinfectantMaster,
    DisinfectionLevel,
    DisinfectionProtocol,
    Vehicle,
    VehicleHandover,
    contains_pathogen_term,
)
from core.models import AuditEvent, Membership, Station
from core.module_overview import module_attention_cards
from core.notification_models import UserNotification
from core.terminal_views import _lock_screen_data

STATES = [
    ("ready", "Einsatzbereit"),
    ("limited", "Eingeschränkt"),
    ("disinfection", "Desinfektion"),
    ("workshop", "Werkstatt"),
    ("out_of_service", "Außer Dienst"),
]
LEVEL_NAMES = [
    "Routine-Wischdesinfektion",
    "Schlussdesinfektion (begrenzt viruzid/bakterizid)",
    "Schlussdesinfektion (viruzid)",
    "Schlussdesinfektion (sporizid)",
    "Grunddesinfektion",
]
MISSION_TERMS = re.compile(r"Anfahrt|Einsatzort|Status [1-6]|FMS|Transportgrund", re.IGNORECASE)
LEGACY_CODES = ("1", "2", "3", "4", "6")


class FleetFixture(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache 0.27", slug="wache-027", fleet_enabled=True)
        self.user = User.objects.create_user("lead-027", first_name="Lea", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.client.force_login(self.user)
        self.vehicle = Vehicle.objects.create(
            station=self.station, slug="rtw-027", call_sign="RTW 027", license_plate="RW-027",
        )
        self.agent = DisinfectantMaster.objects.create(station=self.station, name="Wischtuch", default_exposure_minutes=20)
        ensure_default_levels(self.station)

    def level(self, name=LEVEL_NAMES[0]):
        return DisinfectionLevel.objects.get(station=self.station, name=name)

    def set_state(self, value):
        return self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]), {"status": value})

    def disinfect(self, **overrides):
        data = {"level": self.level().pk, "disinfectant": self.agent.pk, "exposure_minutes": 20,
                "lock_timer_applied": "on", "notes": ""}
        data.update(overrides)
        return self.client.post(reverse("fleet_vehicle_disinfection_create", args=[self.vehicle.slug]),
                                {k: v for k, v in data.items() if v is not None})


class BoundaryChoicesTests(FleetFixture):
    """Messbares Ziel 0.27: Kein Feld, kein Status, keine Anzeige mit Einsatz- oder Erregerbezug."""

    def test_vehicle_and_disinfection_choice_values(self):
        self.assertEqual([(value, str(label)) for value, label in Vehicle.TacticalStatus.choices], STATES)
        self.assertEqual(
            [(value, str(label)) for value, label in DisinfectionLevel.ReleaseRule.choices],
            [("dry", "Nach Antrocknen"), ("exposure", "Nach Einwirkzeit")],
        )
        self.assertEqual(str(Vehicle._meta.get_field("tactical_status").verbose_name), "Fahrzeugzustand")
        self.assertEqual(Vehicle._meta.get_field("tactical_status").default, "ready")
        self.assertFalse(hasattr(DisinfectionProtocol, "Kind"))
        self.assertNotIn("kind", {field.name for field in DisinfectionProtocol._meta.get_fields()})
        self.assertEqual(Vehicle.SELECTABLE_STATUSES, ("ready", "limited", "workshop", "out_of_service"))
        self.assertEqual(Vehicle.AVAILABLE_STATUSES, ("ready", "limited"))
        self.assertEqual(Vehicle.READY_STATUSES, ("ready",))
        self.assertFalse(hasattr(Vehicle, "LEGACY_STATUSES"))
        self.assertEqual([str(name) for name in DEFAULT_LEVEL_NAMES], LEVEL_NAMES)
        for name in LEVEL_NAMES:
            self.assertFalse(contains_pathogen_term(name), name)

        for model in (Vehicle, DisinfectantMaster, DisinfectionLevel, DisinfectionProtocol, VehicleHandover):
            for field in model._meta.get_fields():
                texts = [str(getattr(field, "verbose_name", "")), str(getattr(field, "help_text", ""))]
                for value, label in getattr(field, "flatchoices", None) or []:
                    with self.subTest(model=model.__name__, field=field.name, value=value):
                        self.assertIsNone(re.fullmatch(r"\d+", str(value)), "Ziffern-Code als Auswahlwert")
                    texts.append(str(label))
                for text in texts:
                    with self.subTest(model=model.__name__, field=field.name, text=text):
                        self.assertIsNone(PATHOGEN_PATTERN.search(text))
                        if field.name != "notes":  # der Hinweis nennt, was nicht hineingehört
                            self.assertIsNone(MISSION_TERMS.search(text))

    def test_pages_offer_only_neutral_values(self):
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        self.assertEqual(set(re.findall(r'name="status" value="([^"]+)"', page)),
                         {"ready", "limited", "workshop", "out_of_service"})
        self.assertIn("<h2>Fahrzeugzustand</h2>", page)
        form = DisinfectionProtocolForm(station=self.station)
        self.assertEqual([str(level) for level in form.fields["level"].queryset], LEVEL_NAMES)
        level_select = str(form["level"])
        self.assertNotIn("selected", level_select.split("</option>", 1)[1])  # nur die leere Auswahl
        self.assertIn("Bitte Stufe wählen", level_select)
        for name in ("fleet_dashboard", "fleet_export_csv"):
            content = self.client.get(reverse(name)).content.decode("utf-8-sig")
            with self.subTest(page=name):
                self.assertIsNone(re.search(r"Status [1-6]", content))
                self.assertNotIn('value="1"', content)
                self.assertNotIn('value="6"', content)
        csv = self.client.get(reverse("fleet_export_csv")).content.decode("utf-8-sig")
        self.assertIn("Fahrzeugzustand", csv.splitlines()[0])
        self.assertIn("Einsatzbereit", csv)

    def test_pathogen_guard_rejects_pathogens_but_not_ordinary_words(self):
        for name in ("MRSA-Schluss", "noro", "C. diff", "Norovirus-Desinfektion", "3MRGN", "Rota", "COVID-19"):
            with self.subTest(name=name):
                level = DisinfectionLevel(station=self.station, name=name)
                with self.assertRaises(ValidationError) as caught:
                    level.full_clean()
                self.assertIn("nicht nach Erregern", str(caught.exception))
                with self.assertRaises(ValidationError):
                    level.save()
        for name in ("Volldesinfektion", "Rotationsplan Fahrzeughalle", "Schlussdesinfektion (sporizid)", "Hivo"):
            with self.subTest(name=name):
                self.assertFalse(contains_pathogen_term(name))
        DisinfectionLevel.objects.create(station=self.station, name="Volldesinfektion")

    def test_level_is_station_bound(self):
        other = Station.objects.create(name="Andere", slug="andere-027", fleet_enabled=True)
        foreign_agent = DisinfectantMaster.objects.create(station=other, name="Fremd")
        ensure_default_levels(other)
        foreign = DisinfectionLevel.objects.filter(station=other).first()
        response = self.disinfect(level=foreign.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DisinfectionProtocol.objects.exists())
        with self.assertRaises(ValidationError):
            DisinfectionProtocol(station=self.station, vehicle=self.vehicle, performed_by=self.user,
                                 disinfectant=self.agent, level=foreign).save()
        with self.assertRaises(ValidationError):
            DisinfectionLevel(station=self.station, name="Volldesinfektion", disinfectant=foreign_agent).save()
        # Ohne Wache bietet das Formular nichts an.
        empty = DisinfectionProtocolForm()
        self.assertFalse(empty.fields["level"].queryset.exists())
        self.assertFalse(empty.fields["disinfectant"].queryset.exists())

    def test_default_levels_follow_previous_behaviour(self):
        levels = list(DisinfectionLevel.objects.filter(station=self.station))
        self.assertEqual([level.name for level in levels], LEVEL_NAMES)
        for level in levels:
            self.assertEqual((level.disinfectant, level.release_rule, level.exposure_minutes), (self.agent, "exposure", 20))
            self.assertFalse(level.is_confirmed)
        ensure_default_levels(self.station)  # idempotent
        self.assertEqual(DisinfectionLevel.objects.filter(station=self.station).count(), 5)
        # Eine Wache ohne Mittel erhält Stufen ohne Mittel und ohne Minuten (keine Vorgabe).
        bare = Station.objects.create(name="Leer", slug="leer-027")
        ensure_default_levels(bare)
        self.assertEqual(set(DisinfectionLevel.objects.filter(station=bare).values_list("disinfectant", "exposure_minutes")),
                         {(None, None)})

    def test_confirmed_level_must_be_complete(self):
        from django.db import IntegrityError, transaction

        bare = Station.objects.create(name="Leer", slug="leer-027b")
        level = DisinfectionLevel.objects.create(station=bare, name="Volldesinfektion")
        with self.assertRaises(IntegrityError), transaction.atomic():
            DisinfectionLevel.objects.filter(pk=level.pk).update(rule_confirmed_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            DisinfectionLevel.objects.filter(pk=level.pk).update(exposure_minutes=0)


class FleetStateTests(FleetFixture):
    def test_limited_selectable_and_counted(self):
        response = self.set_state("limited")
        self.assertEqual(response["Location"], reverse("fleet_vehicle_detail", args=[self.vehicle.slug]) + "#fleet-defect")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, "limited")
        event = AuditEvent.objects.get(action="fleet.status_changed")
        self.assertEqual((event.metadata["from"], event.metadata["to"]), ("ready", "limited"))
        page = self.client.get(response["Location"])
        self.assertContains(page, "Bitte den Grund der Einschränkung als Mangel melden.")
        self.assertContains(page, "steht jetzt auf „Eingeschränkt“.")

        Vehicle.objects.create(station=self.station, slug="ktw-027", call_sign="KTW 027", license_plate="KW-027")
        dashboard = self.client.get(reverse("fleet_dashboard"))
        self.assertEqual(dashboard.context["kpis"]["limited"], 1)
        self.assertEqual(dashboard.context["kpis"]["ready"], 1)
        limited = self.client.get(reverse("fleet_dashboard"), {"filter": "limited"})
        self.assertEqual([v.slug for v in limited.context["vehicles"]], ["rtw-027"])
        ready = self.client.get(reverse("fleet_dashboard"), {"filter": "ready"})
        self.assertEqual([v.slug for v in ready.context["vehicles"]], ["ktw-027"])

        card = next(card for card in module_attention_cards(self.station, self.user) if card["key"] == "fleet")
        self.assertEqual((card["subtitle"], card["tone"], card["value"]), ("eingeschränkt einsatzbereit", "warning", 1))
        self.assertTrue(card["href"].endswith("?filter=limited"))

    def test_limited_card_keeps_due_deadlines_and_not_ready_wins(self):
        self.set_state("limited")
        Vehicle.objects.filter(pk=self.vehicle.pk).update(next_hu_date=timezone.localdate() + timedelta(days=3))
        card = next(card for card in module_attention_cards(self.station, self.user) if card["key"] == "fleet")
        self.assertEqual(card["subtitle"], "eingeschränkt einsatzbereit · 1 Frist fällig")
        Vehicle.objects.create(station=self.station, slug="ktw-ws", call_sign="KTW WS", license_plate="KW-WS",
                               tactical_status="workshop")
        card = next(card for card in module_attention_cards(self.station, self.user) if card["key"] == "fleet")
        self.assertEqual((card["subtitle"], card["value"], card["tone"]),
                         ("nicht einsatzbereit · 1 Frist fällig", 1, "danger"))

    def test_limited_and_ready_refused_during_lock(self):
        self.disinfect()
        for value in ("ready", "limited"):
            with self.subTest(value=value):
                response = self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
                                            {"status": value}, follow=True)
                self.assertContains(response, "noch in der Einwirkzeit")
                self.vehicle.refresh_from_db()
                self.assertEqual(self.vehicle.tactical_status, "disinfection")
        self.assertFalse(AuditEvent.objects.filter(action="fleet.status_changed").exists())
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        for value in ("ready", "limited"):
            self.assertRegex(page, rf'value="{value}" class="button secondary" disabled')
        for value in ("workshop", "out_of_service"):
            with self.subTest(value=value):
                self.set_state(value)
                self.vehicle.refresh_from_db()
                self.assertEqual(self.vehicle.tactical_status, value)

    def test_legacy_codes_rejected(self):
        for value in (*LEGACY_CODES, "disinfection", "", "Einsatzbereit"):
            with self.subTest(value=value):
                response = self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
                                            {"status": value}, follow=True)
                self.assertEqual(response.status_code, 200)
                self.vehicle.refresh_from_db()
                self.assertEqual(self.vehicle.tactical_status, "ready")
        self.assertFalse(AuditEvent.objects.filter(action="fleet.status_changed").exists())

    def test_crew_release_button_sets_ready(self):
        from core.crew_notifications import notify_vehicle_ready

        # Desinfektion vor 20 Minuten mit 15 Minuten Einwirkzeit: wartet auf Freigabe.
        DisinfectionProtocol.objects.create(
            station=self.station, vehicle=self.vehicle, performed_by=self.user, disinfectant=self.agent,
            level=self.level(), started_at=timezone.now() - timedelta(minutes=20), exposure_minutes=15,
        )
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.awaiting_crew_release)
        notify_vehicle_ready(self.vehicle)
        self.assertTrue(UserNotification.objects.filter(read_at__isnull=True).exists())
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        banner = page.split("Freigabe durch die Besatzung", 1)[1].split("</form>", 1)[0]
        self.assertIn('name="status" value="ready"', banner)
        self.set_state("ready")
        self.vehicle.refresh_from_db()
        self.assertEqual((self.vehicle.tactical_status, self.vehicle.status_note), ("ready", ""))
        self.assertFalse(UserNotification.objects.filter(read_at__isnull=True).exists())

    def test_display_lockscreen_show_five_labels(self):
        for value, label in STATES:
            Vehicle.objects.filter(pk=self.vehicle.pk).update(tactical_status=value)
            vehicle = display_payload(self.station)["fleet_vehicles"][0]
            lock = _lock_screen_data(self.station)["fleet_vehicles"][0]
            with self.subTest(value=value):
                self.assertEqual((vehicle["status"], vehicle["status_label"], vehicle["status_short"]),
                                 (value, label, label))
                self.assertEqual(lock["status_short"], label)
                self.assertIsNone(re.search(r"\d", vehicle["status"] + label))

    @override_settings(TERMINAL_ENABLED=True)
    def test_terminal_lock_screen_uses_neutral_classes(self):
        from core.terminal import COOKIE_NAME, hash_secret
        from core.terminal_models import StationTerminal

        Vehicle.objects.filter(pk=self.vehicle.pk).update(tactical_status="limited")
        StationTerminal.objects.create(station=self.station, label="Halle", token_hash=hash_secret("t-027-secret"),
                                       created_by=self.user)
        self.client.logout()
        self.client.cookies[COOKIE_NAME] = "t-027-secret"
        page = self.client.get(reverse("terminal_home")).content.decode()
        self.assertIn("lock-status-limited", page)
        self.assertNotRegex(page, r"lock-status-\d")
        static = Path(settings.BASE_DIR) / "core" / "static" / "core"
        css = (static / "lockscreen.css").read_text(encoding="utf-8")
        self.assertIn(".lock-status-limited", css)
        self.assertNotRegex(css, r"lock-status-\d")
        display_css = (static / "display.css").read_text(encoding="utf-8")
        self.assertIn(".display-status-limited", display_css)
        self.assertNotRegex(display_css, r"display-status-\d")

    def test_audit_view_renders_legacy_codes_without_digits(self):
        Membership.objects.filter(user=self.user).update(role=Membership.Role.ADMIN)
        AuditEvent.objects.create(
            actor=self.user, station=self.station, action="fleet.status_changed", object_type="Vehicle",
            object_id=str(self.vehicle.pk), metadata={"fields": ["tactical_status"], "from": "2", "to": "6"},
        )
        self.set_state("limited")
        page = self.client.get(reverse("audit_log"))
        self.assertContains(page, "Fahrzeugzustand geändert")
        self.assertContains(page, "Fahrzeugzustand: Einsatzbereit → Außer Dienst")
        self.assertContains(page, "Fahrzeugzustand: Einsatzbereit → Eingeschränkt")
        self.assertNotContains(page, "→ 6")

    def test_protocol_without_level_is_rerendered_with_field_error(self):
        response = self.disinfect(level=None, notes="Trage zusätzlich gewischt")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitte eine Stufe wählen.")
        self.assertContains(response, "Desinfektionsprotokoll nicht gespeichert.")
        self.assertContains(response, 'value="Trage zusätzlich gewischt"')
        self.assertFalse(DisinfectionProtocol.objects.exists())
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, "ready")
        self.assertIsNone(self.vehicle.disinfection_locked_until)

    def test_protocol_records_level_and_keeps_lock_behaviour(self):
        final = self.level(LEVEL_NAMES[2])
        self.assertRedirects(self.disinfect(level=final.pk), reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        protocol = DisinfectionProtocol.objects.get()
        self.assertEqual((protocol.level, protocol.exposure_minutes, protocol.lock_timer_applied), (final, 20, True))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, "disinfection")
        self.assertNotIn("viruzid", self.vehicle.status_note)
        # Ohne Häkchen keine Sperre (bisheriges Verhalten, bis der Plan bestätigt ist).
        other = Vehicle.objects.create(station=self.station, slug="nef-027", call_sign="NEF 027", license_plate="NE-027")
        self.client.post(reverse("fleet_vehicle_disinfection_create", args=[other.slug]), {
            "level": final.pk, "disinfectant": self.agent.pk, "exposure_minutes": 20, "notes": "",
        })
        other.refresh_from_db()
        self.assertEqual(other.tactical_status, "ready")
        self.assertIsNotNone(other.last_disinfection)

    def test_inactive_level_not_offered_but_history_kept(self):
        level = self.level(LEVEL_NAMES[4])
        self.disinfect(level=level.pk)
        DisinfectionLevel.objects.filter(pk=level.pk).update(is_active=False)
        self.assertNotIn(level, list(active_levels(self.station)))
        response = self.disinfect(level=level.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DisinfectionProtocol.objects.count(), 1)
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        form, history = page.split('id="fleet-disinfection"', 1)[1].split("Desinfektionsbuch-Historie", 1)
        self.assertNotIn(LEVEL_NAMES[4], form.split('id="fleet-defect"', 1)[0])
        self.assertIn(LEVEL_NAMES[4], history)

    def test_legacy_vehicle_asset_sync_uses_neutral_states(self):
        from core.wachalltag_models import StationAsset

        for asset_id, status, expected in (("a-ready", "ready", "ready"), ("a-limited", "limited", "limited"),
                                           ("a-ws", "workshop", "workshop"), ("a-oob", "oob", "out_of_service")):
            with self.subTest(status=status):
                asset = StationAsset.objects.create(station=self.station, asset_id=asset_id, label=asset_id,
                                                    kind=StationAsset.Kind.VEHICLE, status=status)
                self.client.get(reverse("fleet_dashboard"))
                vehicle = Vehicle.objects.get(station=self.station, slug=asset_id)
                self.assertEqual(vehicle.tactical_status, expected)
                # Übernommene Fahrzeuge haben kein Kennzeichen; je Durchlauf eins.
                vehicle.delete()
                asset.delete()


@override_settings(DEMO_MODE=True, DEMO_SANDBOX=False)
class DemoLevelsTests(TestCase):
    def test_demo_seeds_levels_and_reset_keeps_them_usable(self):
        call_command("load_demo_data", stdout=StringIO())
        station = Station.get_default()
        levels = list(DisinfectionLevel.objects.filter(station=station))
        self.assertEqual([level.name for level in levels], LEVEL_NAMES)
        demo_agent = DisinfectantMaster.objects.get(station=station, name__startswith="[Demo]")
        self.assertTrue(all(level.disinfectant_id == demo_agent.pk for level in levels))
        running = DisinfectionProtocol.objects.get(station=station, vehicle__slug="demo-rtw-832")
        self.assertEqual(running.level.name, LEVEL_NAMES[0])
        self.assertEqual(Vehicle.objects.get(station=station, slug="demo-ktw-851").tactical_status, "limited")
        self.assertEqual(Vehicle.objects.get(station=station, slug="demo-rtw-833").tactical_status, "out_of_service")

        call_command("load_demo_data", "--reset", stdout=StringIO())
        connection.check_constraints()
        levels = list(DisinfectionLevel.objects.filter(station=station))
        self.assertEqual([level.name for level in levels], LEVEL_NAMES)  # keine doppelten Stufen
        demo_agent = DisinfectantMaster.objects.get(station=station, name__startswith="[Demo]")
        self.assertTrue(all(level.disinfectant_id == demo_agent.pk for level in levels))


class LevelMigrationTests(TransactionTestCase):
    """0069: Zustände und Stufen verlustfrei, auch rückwärts."""

    migration = importlib.import_module("core.migrations.0069_fleet_states_disinfection_levels")
    before = [dep for dep in migration.Migration.dependencies if dep[0] == "core"]
    after = [("core", "0069_fleet_states_disinfection_levels")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def test_states_and_kinds_are_mapped_without_loss_and_back(self):
        old = self._migrate(self.before)
        Station = old.get_model("core", "Station")
        User = old.get_model("auth", "User")
        OldVehicle = old.get_model("core", "Vehicle")
        Agent = old.get_model("core", "DisinfectantMaster")
        OldProtocol = old.get_model("core", "DisinfectionProtocol")
        Audit = old.get_model("core", "AuditEvent")
        first = Station.objects.create(name="Mig A", slug="mig-a")
        second = Station.objects.create(name="Mig B", slug="mig-b")
        user = User.objects.create(username="mig-user")
        Agent.objects.create(station=first, name="Zweitmittel", default_exposure_minutes=45)
        agent = Agent.objects.create(station=first, name="A-Mittel", default_exposure_minutes=20)
        codes = ("1", "2", "3", "4", "6", "workshop", "disinfection")
        vehicles = {code: OldVehicle.objects.create(station=first, slug=f"v-{code}", call_sign=f"V {code}",
                                                     license_plate=f"P-{code}", tactical_status=code)
                    for code in codes}
        kinds = ("routine", "mrsa", "noro", "c_diff", "base", "unbekannt")
        protocols = [OldProtocol.objects.create(station=first, vehicle=vehicles["1"], performed_by=user,
                                                disinfectant=agent, kind=kind, started_at=timezone.now(),
                                                exposure_minutes=15, lock_timer_applied=False)
                     for kind in kinds]
        event = Audit.objects.create(station=first, action="fleet.status_changed", object_type="Vehicle",
                                     object_id="1", metadata={"fields": ["tactical_status"], "from": "3", "to": "4"})

        new = self._migrate(self.after)
        Vehicle = new.get_model("core", "Vehicle")
        Protocol = new.get_model("core", "DisinfectionProtocol")
        Level = new.get_model("core", "DisinfectionLevel")
        self.assertEqual(
            {code: Vehicle.objects.get(pk=vehicle.pk).tactical_status for code, vehicle in vehicles.items()},
            {"1": "ready", "2": "ready", "3": "ready", "4": "ready", "6": "out_of_service",
             "workshop": "workshop", "disinfection": "disinfection"},
        )
        names = [Protocol.objects.get(pk=protocol.pk).level.name for protocol in protocols]
        self.assertEqual(names, LEVEL_NAMES + [LEVEL_NAMES[0]])
        level_ids = [Protocol.objects.get(pk=protocol.pk).level_id for protocol in protocols[:5]]
        self.assertEqual(len(set(level_ids)), 5)  # jede frühere Art behält ihre eigene Stufe
        for station, agent_id, minutes in ((first, agent.pk, 20), (second, None, None)):
            levels = Level.objects.filter(station_id=station.pk).order_by("pk")
            self.assertEqual([level.name for level in levels], LEVEL_NAMES)
            self.assertEqual({(lv.disinfectant_id, lv.release_rule, lv.exposure_minutes, lv.is_active,
                               lv.rule_confirmed_at) for lv in levels},
                             {(agent_id, "exposure", minutes, True, None)})
            for level in levels:
                self.assertIsNone(PATHOGEN_PATTERN.search(level.name))
        with connection.cursor() as cursor:
            columns = [c.name for c in connection.introspection.get_table_description(cursor, "core_disinfectionprotocol")]
        self.assertNotIn("kind", columns)
        self.assertIn("level_id", columns)
        # Audit bleibt unberührt; das erledigt cleanup_legacy_data mit Trockenlauf.
        self.assertEqual(new.get_model("core", "AuditEvent").objects.get(pk=event.pk).metadata["from"], "3")

        # Rückweg: frühere Arten und Codes aus den Standardnamen.
        back = self._migrate(self.before)
        BackProtocol = back.get_model("core", "DisinfectionProtocol")
        BackVehicle = back.get_model("core", "Vehicle")
        self.assertEqual([BackProtocol.objects.get(pk=p.pk).kind for p in protocols],
                         ["routine", "mrsa", "noro", "c_diff", "base", "routine"])
        self.assertEqual(BackVehicle.objects.get(pk=vehicles["6"].pk).tactical_status, "6")
        self.assertEqual(BackVehicle.objects.get(pk=vehicles["3"].pk).tactical_status, "1")
        self.assertFalse(any(isinstance(f, models.ForeignKey) and f.name == "level"
                             for f in BackProtocol._meta.get_fields()))


class LockOutputsNeverNameLevelTests(FleetFixture):
    """Desinfektion läuft: Display, Sperrbildschirm und Übersicht nennen keine Stufe."""

    def test_running_lock_outputs_are_neutral(self):
        self.disinfect(level=self.level(LEVEL_NAMES[3]).pk)
        texts = [
            json.dumps(display_payload(self.station), ensure_ascii=False),
            json.dumps(_lock_screen_data(self.station), ensure_ascii=False),
            self.client.get(reverse("dashboard")).content.decode(),
            self.client.get(reverse("fleet_export_csv")).content.decode("utf-8-sig"),
        ]
        for text in texts:
            for name in LEVEL_NAMES:
                self.assertNotIn(name, text)
            self.assertNotIn("sporizid", text)
