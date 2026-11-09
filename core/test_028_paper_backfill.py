"""0.28 P4: Nachtrag vom Papierbogen für Übergabe, Fahrzeugübernahme, Desinfektion und Funktionskontrolle.

Abgedeckte Prüfpunkte (Audit 0.28, Paket P4):

- defects-display-paper-1: Nachtrag für die Nachweise, die ``/papier/`` druckt
  (Fahrzeugübernahme, Desinfektion, Funktionskontrolle) mit Ereigniszeit und
  ohne Live-Nebenwirkungen ab der Erfassung.
- defects-display-paper-13: Grenzen der Ereigniszeit, keine Ereigniszeit ohne
  Häkchen, Korrektur über die Versionen einer Übergabe.
- defects-display-paper-14 / client:G8: Kennzeichnung in API, Übersicht,
  Listen, Detail, Druckblättern und am Wachenterminal.
- defects-display-paper-15: Das Wachenterminal trägt nichts nach.
- defects-display-paper-16: Audit nennt Häkchen und Ereigniszeit nur beim Nachtrag.
- Prüfer-Nachtrag: Kein Web-Push und kein Gong für nachgetragene dringende Übergaben.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.api.views import hash_api_token
from core.audit_labels import ACTION_LABELS, annotate
from core.crew_notifications import crew_for_vehicle
from core.disinfection_plan import ensure_default_levels
from core.display import display_payload
from core.fleet_forms import DisinfectionProtocolForm, VehicleHandoverForm
from core.fleet_models import (
    DisinfectantMaster,
    DisinfectionLevel,
    DisinfectionProtocol,
    Vehicle,
    VehicleHandover,
)
from core.forms import HandoverEditForm, HandoverForm
from core.models import (
    ApiToken,
    AuditEvent,
    HandoverEntry,
    HandoverRevision,
    Membership,
    PushOutbox,
    PushSubscription,
    Station,
)
from core.mpg_forms import DeviceRoutineCheckForm
from core.mpg_models import DeviceRoutineCheck, MedicalDevice
from core.paper_backfill import (
    BACKFILL_MAX_DAYS,
    TERMINAL_REFUSAL,
    backfill_time_errors,
    can_backfill,
    paper_backfill_label,
)
from core.terminal import COOKIE_NAME, hash_secret, set_station_code
from core.terminal_models import StationTerminal
from core.wachalltag_models import Defect

WEB_PUSH_SETTINGS = {
    "WEB_PUSH_ENABLED": True,
    "VAPID_PUBLIC_KEY": "BPtest",
    "VAPID_PRIVATE_KEY": "private-key",
    "VAPID_ADMIN_EMAIL": "ops@test.local",
}
CHECKS_YES = {"btm_seal_intact": "yes", "medical_devices_checked": "yes", "vehicle_clean": "yes"}
LABEL_START = "Nachtrag vom Papierbogen · Ereignis "


def local_input(value) -> str:
    """Wert für ``<input type="datetime-local">`` (Ortszeit, Minuten)."""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def minute(value):
    return value.replace(second=0, microsecond=0)


class BackfillBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Nachtrag", slug="wache-nachtrag", fleet_enabled=True, mpg_enabled=True,
        )
        self.member = User.objects.create_user("nfs-p4", first_name="Nora", password="x-test-pass-123")
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.lead = User.objects.create_user("sl-p4", first_name="Sam", password="x-test-pass-123")
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.admin = User.objects.create_user("admin-p4", first_name="Ada", password="x-test-pass-123")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.service_user = set_station_code(self.station, "4827", set_by=self.admin).service_user
        self.now = timezone.now()

    def handover_data(self, **extra):
        data = {
            "category": HandoverEntry.Category.STATION,
            "priority": HandoverEntry.Priority.NORMAL,
            "title": "Bogen Nachtschicht",
            "details": "Wache sauber übergeben laut Papierbogen.",
        }
        data.update(extra)
        return data


# ---- Gemeinsame Regeln -------------------------------------------------------


class BackfillRuleTests(BackfillBase):
    def test_event_time_bounds(self):
        self.assertTrue(backfill_time_errors(None))
        self.assertTrue(backfill_time_errors(self.now + timedelta(minutes=5)))
        self.assertTrue(backfill_time_errors(self.now - timedelta(days=BACKFILL_MAX_DAYS, minutes=1)))
        self.assertEqual(backfill_time_errors(self.now - timedelta(days=BACKFILL_MAX_DAYS - 1)), [])
        self.assertEqual(backfill_time_errors(self.now - timedelta(hours=3)), [])

    def test_correction_bounds_are_relative_to_the_entry(self):
        entry = self.now - timedelta(days=200)
        self.assertEqual(backfill_time_errors(entry - timedelta(days=1), reference=entry), [])
        self.assertTrue(backfill_time_errors(entry + timedelta(hours=1), reference=entry))
        self.assertTrue(backfill_time_errors(entry - timedelta(days=BACKFILL_MAX_DAYS + 1), reference=entry))

    def test_terminal_service_account_cannot_backfill(self):
        self.assertTrue(can_backfill(self.member))
        self.assertFalse(can_backfill(self.service_user))

    def test_event_time_is_only_stored_with_the_flag(self):
        form = HandoverForm(self.handover_data(occurred_at=local_input(self.now - timedelta(hours=2))))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["occurred_at"])
        handover = form.save(commit=False)
        self.assertFalse(handover.is_paper_backfill)
        self.assertIsNone(handover.occurred_at)

    def test_handover_older_than_365_days_is_rejected(self):
        old = self.now - timedelta(days=BACKFILL_MAX_DAYS + 2)
        form = HandoverForm(self.handover_data(is_paper_backfill="on", occurred_at=local_input(old)))
        self.assertFalse(form.is_valid())
        self.assertIn("höchstens 365 Tage", str(form.errors["occurred_at"]))

    def test_database_constraint_requires_consistent_pair(self):
        vehicle = Vehicle.objects.create(station=self.station, slug="rtw-c", call_sign="RTW C", license_plate="C-1")
        device = MedicalDevice.objects.create(station=self.station, slug="defi-c", name="Defi C")
        agent = DisinfectantMaster.objects.create(station=self.station, name="Mittel C")
        cases = (
            lambda **kw: VehicleHandover.objects.create(
                station=self.station, vehicle=vehicle, crew_member=self.member, mileage=1, **kw),
            lambda **kw: DisinfectionProtocol.objects.create(
                station=self.station, vehicle=vehicle, performed_by=self.member, disinfectant=agent, **kw),
            lambda **kw: DeviceRoutineCheck.objects.create(
                station=self.station, device=device, performed_by=self.member, **kw),
        )
        for make in cases:
            for kwargs in ({"is_paper_backfill": True}, {"occurred_at": self.now}):
                with self.subTest(kwargs=kwargs), self.assertRaises(IntegrityError), transaction.atomic():
                    make(**kwargs)
        # Übergaben vor 0.28 kennen keine Ereigniszeit: dort nur „keine Zeit ohne Häkchen“.
        with self.assertRaises(IntegrityError), transaction.atomic():
            HandoverEntry.objects.create(
                station=self.station, category="station", title="x", details="y", author=self.member,
                occurred_at=self.now,
            )

    def test_label_wording(self):
        event = timezone.make_aware(timezone.datetime(2026, 11, 1, 8, 10))
        recorded = timezone.make_aware(timezone.datetime(2026, 11, 2, 9, 0))
        self.assertEqual(
            paper_backfill_label(event, recorded),
            "Nachtrag vom Papierbogen · Ereignis 01.11.2026 08:10 · erfasst 02.11.2026 09:00",
        )


# ---- Übergaben ---------------------------------------------------------------


class HandoverBackfillTests(BackfillBase):
    def create_backfill(self, user=None, **extra):
        self.client.force_login(user or self.member)
        occurred = extra.pop("occurred", self.now - timedelta(hours=5))
        response = self.client.post(reverse("handover_create"), self.handover_data(
            is_paper_backfill="on", occurred_at=local_input(occurred), **extra,
        ))
        return response, HandoverEntry.objects.filter(is_paper_backfill=True).order_by("-pk").first()

    def test_audit_records_flag_and_event_time_only_for_backfills(self):
        _response, backfill = self.create_backfill()
        event = AuditEvent.objects.get(action="handover.created", object_id=str(backfill.pk))
        self.assertIs(event.metadata["paper_backfill"], True)
        self.assertEqual(event.metadata["occurred_at"], backfill.occurred_at.isoformat())
        self.assertIn("occurred_at", event.metadata["fields"])
        self.assertNotIn("details", json.dumps(event.metadata).replace('"details"', ""))

        self.client.post(reverse("handover_create"), self.handover_data(title="Live"))
        live = HandoverEntry.objects.get(title="Live")
        live_event = AuditEvent.objects.get(action="handover.created", object_id=str(live.pk))
        self.assertNotIn("paper_backfill", live_event.metadata)
        self.assertNotIn("occurred_at", live_event.metadata)
        self.assertEqual(live_event.metadata["fields"], ["category", "priority", "title", "details"])

    def test_audit_log_shows_backfill_note(self):
        self.create_backfill()
        event = annotate(AuditEvent.objects.filter(action="handover.created"))[0]
        self.assertTrue(event.backfill_note.startswith(LABEL_START))
        self.client.force_login(self.admin)
        page = self.client.get(reverse("audit_log"))
        self.assertContains(page, LABEL_START)

    @override_settings(**WEB_PUSH_SETTINGS)
    def test_urgent_backfill_sends_no_push_and_no_display_gong(self):
        PushSubscription.objects.create(
            user=self.lead, station=self.station, endpoint="https://push.example/lead/1", p256dh="p", auth="a",
        )
        self.create_backfill(priority=HandoverEntry.Priority.URGENT, title="Alt dringend")
        self.assertEqual(PushOutbox.objects.count(), 0)
        self.assertEqual(display_payload(self.station)["urgent_handovers"], 0)
        # Gegenprobe: live und dringend sendet und zählt.
        self.client.post(reverse("handover_create"), self.handover_data(
            priority=HandoverEntry.Priority.URGENT, title="Jetzt dringend",
        ))
        self.assertEqual(PushOutbox.objects.count(), 1)
        self.assertEqual(display_payload(self.station)["urgent_handovers"], 1)

    @override_settings(**WEB_PUSH_SETTINGS)
    def test_correcting_backfill_to_urgent_sends_no_push(self):
        PushSubscription.objects.create(
            user=self.member, station=self.station, endpoint="https://push.example/member/1", p256dh="p", auth="a",
        )
        _response, backfill = self.create_backfill()
        self.client.force_login(self.lead)
        response = self.client.post(reverse("handover_edit", args=[backfill.pk]), {
            **self.handover_data(priority=HandoverEntry.Priority.URGENT),
            "is_paper_backfill": "on", "occurred_at": local_input(backfill.occurred_at),
        })
        self.assertRedirects(response, reverse("handover_detail", args=[backfill.pk]))
        backfill.refresh_from_db()
        self.assertEqual(backfill.priority, HandoverEntry.Priority.URGENT)
        self.assertEqual(PushOutbox.objects.count(), 0)

    def test_marking_on_list_detail_dashboard(self):
        _response, backfill = self.create_backfill()
        self.client.force_login(self.member)
        for name, args in (("handover_list", []), ("handover_detail", [backfill.pk]), ("dashboard", [])):
            with self.subTest(name=name):
                page = self.client.get(reverse(name, args=args))
                self.assertContains(page, LABEL_START)
                self.assertContains(page, " · erfasst ")

    def test_shift_lead_corrects_event_time_with_revision_and_audit(self):
        _response, backfill = self.create_backfill()
        corrected = minute(backfill.created_at - timedelta(days=2))
        self.client.force_login(self.lead)
        response = self.client.post(reverse("handover_edit", args=[backfill.pk]), {
            **self.handover_data(), "is_paper_backfill": "on", "occurred_at": local_input(corrected),
        })
        self.assertRedirects(response, reverse("handover_detail", args=[backfill.pk]))
        backfill.refresh_from_db()
        self.assertEqual(backfill.occurred_at, corrected)
        self.assertEqual(backfill.version, 2)
        self.assertEqual(HandoverRevision.objects.get(handover=backfill, version=2).snapshot["occurred_at"],
                         corrected.isoformat())
        event = AuditEvent.objects.get(action="handover.content_updated")
        self.assertEqual(event.metadata["fields"], ["occurred_at"])
        self.assertEqual(event.metadata["changes"]["occurred_at"]["to"], corrected.isoformat())

    def test_correction_cannot_move_event_after_the_entry(self):
        _response, backfill = self.create_backfill()
        form = HandoverEditForm({
            **self.handover_data(), "is_paper_backfill": "on",
            "occurred_at": local_input(backfill.created_at + timedelta(hours=2)),
        }, instance=backfill)
        self.assertFalse(form.is_valid())
        self.assertIn("nach der Erfassung", str(form.errors["occurred_at"]))

    def test_removing_the_flag_clears_the_event_time(self):
        _response, backfill = self.create_backfill()
        self.client.force_login(self.lead)
        self.client.post(reverse("handover_edit", args=[backfill.pk]), {
            **self.handover_data(), "occurred_at": local_input(backfill.occurred_at),
        })
        backfill.refresh_from_db()
        self.assertFalse(backfill.is_paper_backfill)
        self.assertIsNone(backfill.occurred_at)
        event = AuditEvent.objects.get(action="handover.content_updated")
        self.assertEqual(event.metadata["changes"]["is_paper_backfill"], {"from": True, "to": False})

    def test_members_cannot_correct(self):
        _response, backfill = self.create_backfill()
        self.client.force_login(self.member)
        response = self.client.post(reverse("handover_edit", args=[backfill.pk]), {
            **self.handover_data(), "is_paper_backfill": "on",
            "occurred_at": local_input(backfill.occurred_at - timedelta(hours=1)),
        })
        self.assertEqual(response.status_code, 403)

    def test_form_without_backfill_permission_rejects_flag(self):
        form = HandoverForm(
            self.handover_data(is_paper_backfill="on", occurred_at=local_input(self.now)), allow_backfill=False,
        )
        self.assertNotIn("is_paper_backfill", form.fields)
        self.assertFalse(form.is_valid())
        self.assertIn(str(TERMINAL_REFUSAL), form.non_field_errors())


class HandoverApiBackfillTests(BackfillBase):
    def token(self, user, raw):
        ApiToken.objects.create(
            user=user, label="t", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:handovers", "write:handovers", "read:me"], expires_at=timezone.now() + timedelta(days=1),
        )
        return {"HTTP_AUTHORIZATION": f"Token {raw}"}

    def post(self, headers, **extra):
        return self.client.post(
            reverse("api_v1_handovers"), data=json.dumps(self.handover_data(**extra)),
            content_type="application/json", **headers,
        )

    def test_api_creates_and_returns_backfill_fields(self):
        headers = self.token(self.member, "wb_test_p4_member_token_123456")
        occurred = minute(self.now - timedelta(hours=6))
        response = self.post(headers, is_paper_backfill=True, occurred_at=occurred.isoformat())
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIs(body["is_paper_backfill"], True)
        self.assertEqual(body["occurred_at"], occurred.isoformat())
        live = self.post(headers, title="Live").json()
        self.assertIs(live["is_paper_backfill"], False)
        self.assertIsNone(live["occurred_at"])
        results = self.client.get(reverse("api_v1_handovers"), **headers).json()["results"]
        self.assertEqual({item["is_paper_backfill"] for item in results}, {True, False})
        detail = self.client.get(reverse("api_v1_handover_detail", args=[body["id"]]), **headers).json()
        self.assertEqual(detail["occurred_at"], occurred.isoformat())

    def test_api_rejects_future_and_flag_only_events(self):
        headers = self.token(self.member, "wb_test_p4_member_token_654321")
        future = self.post(headers, is_paper_backfill=True, occurred_at=(self.now + timedelta(days=1)).isoformat())
        self.assertEqual(future.status_code, 422)
        self.assertIn("occurred_at", future.json()["fields"])
        stray = self.post(headers, title="Ohne Haken", occurred_at=(self.now - timedelta(hours=1)).isoformat())
        self.assertEqual(stray.status_code, 201)
        self.assertIsNone(HandoverEntry.objects.get(title="Ohne Haken").occurred_at)

    def test_terminal_service_account_cannot_backfill_over_api(self):
        headers = self.token(self.service_user, "wb_test_p4_terminal_token_12345")
        response = self.post(headers, is_paper_backfill=True, occurred_at=(self.now - timedelta(hours=1)).isoformat())
        self.assertEqual(response.status_code, 422)
        self.assertFalse(HandoverEntry.objects.exists())


@override_settings(TERMINAL_ENABLED=True, TERMINAL_IDLE_SECONDS=120)
class TerminalBackfillTests(BackfillBase):
    def setUp(self):
        super().setUp()
        raw = "terminal-secret-p4"
        StationTerminal.objects.create(station=self.station, label="Halle", token_hash=hash_secret(raw),
                                       created_by=self.admin)
        self.client.cookies[COOKIE_NAME] = raw
        self.client.post(reverse("terminal_home"), data={"code": "4827"})

    def test_terminal_form_has_no_backfill_and_rejects_posted_flag(self):
        page = self.client.get(reverse("handover_create"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'name="is_paper_backfill"')
        self.assertNotContains(page, 'name="occurred_at"')
        response = self.client.post(reverse("handover_create"), self.handover_data(
            is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(hours=1)),
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "am Wachenterminal nicht möglich")
        self.assertFalse(HandoverEntry.objects.exists())
        # Ohne Häkchen bleibt das Schreiben einer Übergabe am Terminal möglich.
        self.client.post(reverse("handover_create"), self.handover_data(title="Am Terminal"))
        self.assertTrue(HandoverEntry.objects.filter(title="Am Terminal", is_paper_backfill=False).exists())

    def test_terminal_menu_marks_backfills(self):
        HandoverEntry.objects.create(
            station=self.station, category="station", title="Vom Bogen", details="d", author=self.member,
            is_paper_backfill=True, occurred_at=self.now - timedelta(hours=3),
        )
        page = self.client.get(reverse("terminal_menu"))
        self.assertContains(page, LABEL_START)


# ---- Fahrzeugübernahme und Desinfektion -------------------------------------------


class FleetBackfillBase(BackfillBase):
    def setUp(self):
        super().setUp()
        self.vehicle = Vehicle.objects.create(
            station=self.station, slug="rtw-p4", call_sign="RTW P4", license_plate="P4-1",
            current_mileage=50000, fuel_level_percent=90, adblue_level_percent=80, o2_pressure_bar=180,
        )
        self.agent = DisinfectantMaster.objects.create(station=self.station, name="Wischmittel P4",
                                                       default_exposure_minutes=15)
        ensure_default_levels(self.station)
        self.level = DisinfectionLevel.objects.filter(station=self.station).order_by("pk").last()

    def handover_post(self, user=None, **extra):
        self.client.force_login(user or self.member)
        data = {"mileage": 50100, "fuel_percent": "75", "adblue_percent": "50", "o2_pressure_bar": 190,
                **CHECKS_YES, "notes": ""}
        data.update(extra)
        return self.client.post(reverse("fleet_vehicle_handover_create", args=[self.vehicle.slug]), data)

    def disinfection_post(self, user=None, **extra):
        self.client.force_login(user or self.member)
        data = {"level": self.level.pk, "disinfectant": self.agent.pk, "exposure_minutes": 30,
                "lock_timer_applied": "on", "notes": "Griffe zusätzlich gewischt"}
        data.update(extra)
        return self.client.post(reverse("fleet_vehicle_disinfection_create", args=[self.vehicle.slug]), data)


class VehicleHandoverBackfillTests(FleetBackfillBase):
    def test_older_backfill_keeps_vehicle_values_and_skips_mileage_check(self):
        self.assertRedirects(self.handover_post(), reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        occurred = self.now - timedelta(days=2)
        response = self.handover_post(mileage=48000, fuel_percent="25", o2_pressure_bar=80,
                                      is_paper_backfill="on", occurred_at=local_input(occurred))
        self.assertRedirects(response, reverse("fleet_vehicle_detail", args=[self.vehicle.slug]),
                             fetch_redirect_response=False)
        backfill = VehicleHandover.objects.get(is_paper_backfill=True)
        self.assertEqual(backfill.occurred_at, minute(occurred))
        self.vehicle.refresh_from_db()
        self.assertEqual((self.vehicle.current_mileage, self.vehicle.fuel_level_percent), (50100, 75))
        event = AuditEvent.objects.get(action="fleet.vehicle_handover_backfilled")
        self.assertEqual(event.metadata, {
            "vehicle_handover_id": backfill.pk, "paper_backfill": True, "occurred_at": backfill.occurred_at.isoformat(),
        })
        self.assertIn("fleet.vehicle_handover_backfilled", ACTION_LABELS)
        # Kein Warnhinweis zu Sauerstoff/Kraftstoff aus der Vergangenheit.
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.assertNotContains(page, "Sauerstoffvorrat niedrig")
        self.assertContains(page, LABEL_START)
        # Reihenfolge nach Ereigniszeit: die Live-Übernahme zuerst.
        html = page.content.decode()
        history = html.split("Letzte Schichtübernahmen", 1)[1]
        self.assertLess(history.index("50100 km"), history.index("48000 km"))

    def test_newest_backfill_updates_vehicle(self):
        occurred = self.now - timedelta(hours=4)
        self.handover_post(mileage=49000, is_paper_backfill="on", occurred_at=local_input(occurred))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.current_mileage, 49000)

    def test_live_handover_still_rejects_lower_mileage(self):
        self.handover_post()
        response = self.handover_post(mileage=40000)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nicht unter dem letzten Stand")
        self.assertEqual(VehicleHandover.objects.count(), 1)

    def test_backfill_time_bounds(self):
        for occurred in (self.now + timedelta(hours=2), self.now - timedelta(days=BACKFILL_MAX_DAYS + 3)):
            with self.subTest(occurred=occurred):
                response = self.handover_post(is_paper_backfill="on", occurred_at=local_input(occurred))
                self.assertEqual(response.status_code, 200)
        response = self.handover_post(is_paper_backfill="on", occurred_at="")
        self.assertContains(response, "Ereigniszeitpunkt angegeben werden")
        self.assertFalse(VehicleHandover.objects.exists())

    def test_form_without_backfill_permission(self):
        form = VehicleHandoverForm(
            {"mileage": 1, "fuel_percent": "75", "adblue_percent": "50", "o2_pressure_bar": 190, **CHECKS_YES,
             "is_paper_backfill": "on", "occurred_at": local_input(self.now)},
            vehicle=self.vehicle, allow_backfill=False,
        )
        self.assertNotIn("occurred_at", form.fields)
        self.assertFalse(form.is_valid())
        self.assertIn(str(TERMINAL_REFUSAL), form.non_field_errors())

    def test_backfilled_crew_older_than_window_is_not_current_crew(self):
        self.handover_post(user=self.lead, is_paper_backfill="on",
                           occurred_at=local_input(self.now - timedelta(days=3)))
        self.assertNotIn(self.lead, crew_for_vehicle(self.vehicle))
        self.handover_post(user=self.member)
        self.assertIn(self.member, crew_for_vehicle(self.vehicle))


class DisinfectionBackfillTests(FleetBackfillBase):
    def test_finished_backfill_does_not_lock_vehicle(self):
        occurred = self.now - timedelta(hours=6)
        response = self.disinfection_post(is_paper_backfill="on", occurred_at=local_input(occurred))
        self.assertRedirects(response, reverse("fleet_vehicle_detail", args=[self.vehicle.slug]),
                             fetch_redirect_response=False)
        self.vehicle.refresh_from_db()
        self.assertFalse(self.vehicle.is_disinfection_locked)
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.READY)
        self.assertEqual(self.vehicle.last_disinfection, minute(occurred))
        protocol = DisinfectionProtocol.objects.get()
        self.assertEqual(protocol.event_at, minute(occurred))
        event = AuditEvent.objects.get(action="fleet.disinfection_backfilled")
        # Entscheidung D2: keine Stufe, Einwirkzeit oder Bemerkung im Audit.
        self.assertEqual(set(event.metadata), {"disinfection_id", "paper_backfill", "occurred_at"})

    def test_backfill_with_running_exposure_locks_until_event_plus_exposure(self):
        occurred = minute(self.now - timedelta(minutes=10))
        self.disinfection_post(is_paper_backfill="on", occurred_at=local_input(occurred), exposure_minutes=30)
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.is_disinfection_locked)
        self.assertEqual(self.vehicle.disinfection_locked_until, occurred + timedelta(minutes=30))
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)

    def test_older_backfill_does_not_move_last_disinfection_back(self):
        self.disinfection_post(lock_timer_applied="")
        self.vehicle.refresh_from_db()
        latest = self.vehicle.last_disinfection
        self.disinfection_post(is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(days=1)),
                               lock_timer_applied="")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.last_disinfection, latest)

    def test_d2_visibility_unchanged_for_backfills(self):
        self.disinfection_post(user=self.lead, is_paper_backfill="on",
                               occurred_at=local_input(self.now - timedelta(hours=6)))
        self.client.force_login(self.member)
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        history = page.content.decode().split("Desinfektionsbuch-Historie", 1)[1]
        self.assertIn(LABEL_START, history)
        self.assertNotIn(self.level.name, history)
        self.assertNotIn("Einwirkzeit 30", history)
        self.assertNotIn("Griffe zusätzlich gewischt", history)
        self.client.force_login(self.lead)
        history = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        self.assertIn("Einwirkzeit 30", history.split("Desinfektionsbuch-Historie", 1)[1])

    def test_fleet_dashboard_marks_backfill(self):
        self.disinfection_post(is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(hours=6)))
        page = self.client.get(reverse("fleet_dashboard"))
        self.assertContains(page, LABEL_START)

    def test_form_without_backfill_permission(self):
        form = DisinfectionProtocolForm(
            {"level": self.level.pk, "disinfectant": self.agent.pk, "exposure_minutes": 15,
             "is_paper_backfill": "on", "occurred_at": local_input(self.now)},
            station=self.station, allow_backfill=False,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(str(TERMINAL_REFUSAL), form.non_field_errors())


# ---- Funktionskontrolle ------------------------------------------------------


class RoutineCheckBackfillTests(BackfillBase):
    def setUp(self):
        super().setUp()
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi-p4", name="Defi P4")

    def post(self, **extra):
        self.client.force_login(self.member)
        data = {"battery_ok": "yes", "visual_ok": "yes", "function_ok": "yes", "notes": ""}
        data.update(extra)
        return self.client.post(reverse("mpg_routine_check", args=[self.device.slug]), data, follow=True)

    def test_backfill_sets_last_check_by_event_time_and_audits(self):
        occurred = minute(self.now - timedelta(hours=8))
        response = self.post(is_paper_backfill="on", occurred_at=local_input(occurred))
        self.assertContains(response, "Nachtrag vom Papierbogen gespeichert")
        check = DeviceRoutineCheck.objects.get()
        self.assertEqual(check.event_at, occurred)
        self.device.refresh_from_db()
        self.assertEqual(self.device.last_routine_check, occurred)
        event = AuditEvent.objects.get(action="mpg.routine_check")
        self.assertEqual(event.metadata, {"passed": True, "paper_backfill": True, "occurred_at": occurred.isoformat()})
        self.assertContains(response, LABEL_START)

    def test_older_backfill_keeps_newer_last_check(self):
        self.post()
        self.device.refresh_from_db()
        latest = self.device.last_routine_check
        self.post(is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(days=2)))
        self.device.refresh_from_db()
        self.assertEqual(self.device.last_routine_check, latest)
        self.assertNotIn("paper_backfill", AuditEvent.objects.filter(action="mpg.routine_check").earliest("pk").metadata)

    def test_failed_backfill_locks_device_with_marked_defect(self):
        self.post(function_ok="no", is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(hours=8)))
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        defect = Defect.objects.get(medical_device=self.device)
        self.assertTrue(defect.description.startswith(LABEL_START))

    def test_storno_window_counts_from_entry(self):
        self.post(is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(days=3)))
        check = DeviceRoutineCheck.objects.get()
        self.assertTrue(check.is_within_storno_window)
        response = self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk]))
        self.assertRedirects(response, reverse("mpg_device_detail", args=[self.device.slug]))
        self.assertTrue(check.is_cancelled)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.last_routine_check)

    def test_future_event_time_is_rejected_with_reason(self):
        response = self.post(is_paper_backfill="on", occurred_at=local_input(self.now + timedelta(days=1)))
        self.assertContains(response, "nicht in der Zukunft")
        self.assertFalse(DeviceRoutineCheck.objects.exists())

    def test_detail_form_offers_backfill_and_dashboard_marks_it(self):
        self.client.force_login(self.member)
        detail = self.client.get(reverse("mpg_device_detail", args=[self.device.slug]))
        self.assertContains(detail, 'name="is_paper_backfill"')
        self.assertContains(detail, 'type="datetime-local"')
        self.post(is_paper_backfill="on", occurred_at=local_input(self.now - timedelta(hours=8)))
        self.assertContains(self.client.get(reverse("mpg_dashboard")), LABEL_START)

    def test_form_without_backfill_permission(self):
        form = DeviceRoutineCheckForm(
            {"battery_ok": "yes", "visual_ok": "yes", "function_ok": "yes",
             "is_paper_backfill": "on", "occurred_at": local_input(self.now)},
            allow_backfill=False,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(str(TERMINAL_REFUSAL), form.non_field_errors())


# ---- Papierblätter -----------------------------------------------------------


class PaperSheetLineTests(BackfillBase):
    def test_each_record_sheet_asks_for_a_later_backfill(self):
        Station.objects.filter(pk=self.station.pk).update(checklists_enabled=True)
        Vehicle.objects.create(station=self.station, slug="rtw-s", call_sign="RTW S", license_plate="S-1")
        MedicalDevice.objects.create(station=self.station, slug="defi-s", name="Defi S")
        from core.models import Checklist

        Checklist.objects.create(station=self.station, title="Wachenrundgang")
        self.client.force_login(self.member)
        for name in ("paper_vehicle_handover", "paper_disinfection", "paper_device_checks", "paper_checklists"):
            with self.subTest(name=name):
                self.assertContains(self.client.get(reverse(name)),
                                    "Später im Wachbuch als Nachtrag vom Papierbogen erfassen.")
