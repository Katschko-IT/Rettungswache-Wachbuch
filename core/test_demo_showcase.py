"""Demo-Schaufenster (Paket B2): Sperrbildschirm-Vorschau, Wachen-Display,
Startseite, Seite „Für IT und Datenschutz“, lesbares Audit, Fehlerseiten,
Umlaute in Auswahllisten und anonyme Demo-Kennzahlen."""
from __future__ import annotations

import re
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.demo_models import DemoDailyStat, DemoSandbox
from core.models import AuditEvent, HandoverEntry, Membership, NewsPost, Station

DEMO = {"username": "Demo", "password": "Demo"}
SANDBOX_ON = dict(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False, FEEDBACK_ENABLED=True)
STATIC = Path(settings.BASE_DIR) / "core" / "static" / "core"


def start_demo(client):
    client.post(reverse("login"), DEMO)
    user = User.objects.get(pk=client.session["_auth_user_id"])
    return user, Membership.objects.get(user=user).station


@override_settings(**SANDBOX_ON)
class LockScreenPreviewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_preview_shows_lock_screen_of_own_demo_station_without_terminal(self):
        from core.terminal_models import StationTerminal, StationTerminalCode

        user, station = start_demo(self.client)
        response = self.client.get(reverse("demo_lock_screen"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(station.name, html)
        self.assertIn("Vorschau aus der Demo", html)
        self.assertIn("data-lock-screen", html)
        self.assertIn("RTW 1", html)
        # Kein Terminal: keine Abfrage von /terminal/daten/, keine QR-Bilder,
        # kein Absenden des Wachen-Codes.
        self.assertIn('data-data-url=""', html)
        self.assertNotIn(reverse("terminal_data"), html)
        self.assertNotIn(reverse("terminal_connect_qr"), html)
        self.assertNotIn("data-pin-autosubmit", html)
        self.assertNotIn('method="post"', html)
        self.assertFalse(StationTerminal.objects.exists())
        self.assertFalse(StationTerminalCode.objects.exists())
        # Die Anmeldung bleibt die des Demo-Kontos.
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_preview_is_linked_from_more_page_only_in_demo(self):
        start_demo(self.client)
        self.assertContains(self.client.get(reverse("more")), reverse("demo_lock_screen"))

    def test_preview_needs_a_demo_station(self):
        self.assertEqual(self.client.get(reverse("demo_lock_screen")).status_code, 404)
        station = Station.objects.create(name="Echte Wache", slug="echt")
        user = User.objects.create_user("echt", password="x" * 16)
        Membership.objects.create(user=user, station=station, role=Membership.Role.ADMIN)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("demo_lock_screen")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("more")), reverse("demo_lock_screen"))

    def test_auditor_role_gets_no_preview(self):
        start_demo(self.client)
        self.client.post(reverse("demo_switch_role"), {"role": "audit"})
        self.assertEqual(self.client.get(reverse("demo_lock_screen")).status_code, 404)


class LockScreenAssetTests(TestCase):
    def test_unlock_hint_icon_is_sized_without_app_css(self):
        # Der Sperrbildschirm lädt app.css nicht; ohne eigene Regel war das
        # Schloss-Symbol auf jedem Terminal 300 × 150 px groß.
        css = (STATIC / "terminal.css").read_text(encoding="utf-8")
        rule = re.search(r"\.terminal-unlock-hint \.icon \{([^}]*)\}", css)
        self.assertIsNotNone(rule)
        self.assertIn("width: 1.25rem", rule.group(1))
        self.assertIn("fill: none", rule.group(1))

    def test_terminal_script_does_not_poll_without_data_url(self):
        js = (STATIC / "terminal.js").read_text(encoding="utf-8")
        poll = js[js.index("function poll()"):]
        self.assertLess(poll.index("if (!url)"), poll.index("fetch(url"))


class DisplayShowcaseTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Display", slug="wache-display")
        self.user = User.objects.create_user("display-admin", password="x" * 16)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)

    def test_news_reach_the_display_although_there_is_no_news_switch(self):
        from core.display import display_payload

        NewsPost.objects.create(station=self.station, title="Neue Dienstanweisung Hygiene", body="x", created_by=self.user)
        NewsPost.objects.create(
            station=self.station, title="Archiviert", body="x", created_by=self.user, archived_at=timezone.now(),
        )
        self.assertEqual(display_payload(self.station)["news"], [{"title": "Neue Dienstanweisung Hygiene"}])

    def test_stock_alerts_cover_low_stock_expiry_and_recall(self):
        from core.display import display_payload
        from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StorageLocation

        today = timezone.localdate()
        location = StorageLocation.objects.create(station=self.station, slug="lager", name="Lager")

        def stock(slug, name, quantity, minimum, days, recalled=False):
            item = MedicalItem.objects.create(station=self.station, slug=slug, name=name, min_stock=minimum)
            batch = ItemBatch.objects.create(
                item=item, station=self.station, batch_number=f"L-{slug}",
                manufacturer_exp_date=today + timedelta(days=days), is_recalled=recalled,
            )
            StockItem.objects.create(station=self.station, item=item, batch=batch, location=location, quantity=quantity)

        stock("handschuhe", "Handschuhe M", 2, 10, 400)
        stock("nacl", "NaCl 500 ml", 20, 5, 10)
        stock("ampulle", "Ampulle", 8, 2, 300, recalled=True)
        stock("verband", "Verband", 30, 5, 400)
        alerts = {alert["name"]: alert for alert in display_payload(self.station)["warehouse_alerts"]}
        self.assertEqual(set(alerts), {"Handschuhe M", "NaCl 500 ml", "Ampulle"})
        self.assertEqual(alerts["Handschuhe M"]["level"], "low")
        self.assertIn("2 von 10", alerts["Handschuhe M"]["label"])
        self.assertEqual(alerts["NaCl 500 ml"]["level"], "critical")
        self.assertEqual(alerts["Ampulle"]["level"], "recalled")

    def test_display_has_containers_and_renderers_for_fleet_devices_and_material(self):
        from core.display_models import DEFAULT_DISPLAY_CONFIG
        from core.display_views import AVAILABLE_MODULES

        self.client.force_login(self.user)
        html = self.client.get(reverse("display_home")).content.decode()
        for marker in ('data-module-container="fleet"', "data-display-fleet", "data-display-mpg", "data-display-warehouse"):
            self.assertIn(marker, html)
        js = (STATIC / "display.js").read_text(encoding="utf-8")
        apply = js[js.index("function apply(payload)"):]
        for call in ("renderFleet(root, payload.fleet_vehicles)", "payload.mpg_alerts", "payload.warehouse_alerts"):
            self.assertIn(call, apply)
        self.assertNotIn(".innerHTML", js)
        for module_id in ("fleet", "mpg_alerts", "warehouse_alerts"):
            self.assertIn(module_id, {module["id"] for module in AVAILABLE_MODULES})
            self.assertIn(module_id, {module["id"] for module in DEFAULT_DISPLAY_CONFIG["modules"]})

    def test_display_hides_modules_the_station_does_not_use(self):
        Station.objects.filter(pk=self.station.pk).update(fleet_enabled=False, mpg_enabled=False, warehouse_enabled=False)
        self.client.force_login(self.user)
        html = self.client.get(reverse("display_home")).content.decode()
        self.assertNotIn("data-display-fleet", html)
        self.assertNotIn("data-display-mpg", html)
        self.assertNotIn("data-display-warehouse", html)


class LandingTests(TestCase):
    def setUp(self):
        cache.clear()

    def _hero(self, html):
        return html[html.index('class="pub-hero"'):html.index("</section>", html.index('class="pub-hero"'))]

    @override_settings(**SANDBOX_ON)
    def test_public_demo_makes_demo_the_primary_action(self):
        html = self.client.get(reverse("landing")).content.decode()
        hero = self._hero(html)
        first_primary = hero.index("pub-button primary")
        self.assertLess(hero.index(reverse("demo_login")), first_primary)
        self.assertIn("Demo starten – ohne Konto", hero)
        self.assertNotIn(f'class="pub-button primary" href="{reverse("login")}"', hero)
        # Kopfzeile: „Demo starten“ statt „Anmelden“; die Anmeldung bleibt im Hero erreichbar.
        header = html[html.index('class="app-header"'):html.index("</header>")]
        self.assertIn(reverse("demo_login"), header)
        self.assertNotIn("header-login", header)
        self.assertIn(reverse("login"), hero)

    def test_regular_instance_keeps_login_as_primary_action(self):
        html = self.client.get(reverse("landing")).content.decode()
        hero = self._hero(html)
        self.assertIn(f'class="pub-button primary" href="{reverse("login")}"', hero)
        self.assertNotIn(reverse("demo_login"), html)
        self.assertIn("header-login", html)

    @override_settings(**SANDBOX_ON)
    def test_trust_signals_and_it_page_link(self):
        response = self.client.get(reverse("landing"))
        for text in ("Open Source (AGPL-3.0)", "auch ohne Internet", "Eigener Server statt Cloud",
                     "DSGVO-Vorlagen inklusive", "Keine Patientendaten", "Touch-Terminal in der Fahrzeughalle",
                     "Kaffeekasse ohne Zettel", "core/screens/lockscreen-tablet"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("it_privacy"))
        self.assertTrue((STATIC / "screens" / "lockscreen-tablet.webp").exists())

    @override_settings(**SANDBOX_ON)
    def test_active_demos_shown_only_from_three_on(self):
        from core import demo_stats

        for index in range(2):
            station = Station.objects.create(name=f"Demo {index}", slug=f"demo-x{index}")
            DemoSandbox.objects.create(station=station, token=f"tok{index}")
        self.assertNotContains(self.client.get(reverse("landing")), "Gerade aktiv")
        station = Station.objects.create(name="Demo 3", slug="demo-x3")
        DemoSandbox.objects.create(station=station, token="tok3")
        cache.delete(demo_stats.ACTIVE_CACHE_KEY)
        self.assertContains(self.client.get(reverse("landing")), "Gerade aktiv: 3 Demo-Wachen")


class ItPrivacyPageTests(TestCase):
    def test_public_page_names_architecture_data_and_trust_model(self):
        response = self.client.get(reverse("it_privacy"))
        self.assertEqual(response.status_code, 200)
        for text in ("Welche Daten gespeichert werden", "Keine Patienten-", "Argon2id",
                     "Teil des Vertrauensmodells", "Art. 28 DSGVO", "VVT-TEMPLATE.md", "<svg"):
            self.assertContains(response, text)
        self.assertContains(self.client.get(reverse("landing")), reverse("it_privacy"))


class AuditLogLabelTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Audit", slug="wache-audit")
        self.user = User.objects.create_user("auditor", password="x" * 16, first_name="Andi")
        self.membership = Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.AUDITOR)
        self.client.force_login(self.user)

    def test_status_change_is_shown_in_plain_language(self):
        from core.services import change_handover_status

        author = User.objects.create_user("lead", password="x" * 16)
        lead = Membership.objects.create(user=author, station=self.station, role=Membership.Role.SHIFT_LEAD)
        handover = HandoverEntry.objects.create(
            station=self.station, category="station", title="Geheimer Freitext", details="x", author=author,
        )
        change_handover_status(handover, HandoverEntry.Status.IN_PROGRESS, lead)
        page = self.client.get(reverse("audit_log"))
        self.assertContains(page, "Status einer Übergabe geändert")
        self.assertContains(page, "handover.status_changed")
        self.assertContains(page, f"Übergabe #{handover.pk}")
        self.assertContains(page, "Status: Offen → In Bearbeitung")
        self.assertNotContains(page, "Geheimer Freitext")

    def test_older_events_and_unknown_codes_stay_readable(self):
        AuditEvent.objects.create(
            actor=self.user, station=self.station, action="fleet.status_changed", object_type="Vehicle",
            object_id="3", metadata={"fields": ["tactical_status"], "from": "1", "to": "disinfection"},
        )
        AuditEvent.objects.create(
            actor=self.user, station=self.station, action="station.settings_updated", object_type="Station",
            object_id=str(self.station.pk), metadata={"changes": {"iban": {"changed": True}}},
        )
        AuditEvent.objects.create(actor=self.user, station=self.station, action="test.unbekannt", object_type="Test")
        page = self.client.get(reverse("audit_log"))
        self.assertContains(page, "Fahrzeugstatus geändert")
        self.assertContains(page, "Einsatzbereit → Desinfektion (gesperrt)")
        self.assertContains(page, "IBAN: geändert")
        self.assertContains(page, "test.unbekannt")


class ErrorPageSupportTests(TestCase):
    def test_error_pages_point_to_the_own_station_not_a_vendor_support(self):
        response = self.client.get("/gibt-es-nicht/")
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Wachbuch-Support", status_code=404)
        self.assertContains(response, "Leitung oder Administration deiner Wache", status_code=404)
        for name in ("400", "403", "404", "429", "500"):
            source = (Path(settings.BASE_DIR) / "templates" / "errors" / f"{name}.html").read_text(encoding="utf-8")
            self.assertNotIn("Wachbuch-Support", source)
            self.assertIn('{% include "errors/_support.html" %}', source)

    @override_settings(**SANDBOX_ON)
    def test_public_demo_error_page_offers_feedback(self):
        response = self.client.get("/gibt-es-nicht/")
        self.assertContains(response, "Etwas klappt in der Demo nicht?", status_code=404)
        self.assertContains(response, reverse("feedback"), status_code=404)


class ChoiceLabelTests(TestCase):
    def test_wachalltag_labels_use_real_umlauts(self):
        from core.wachalltag_models import ChecklistSchedule, Defect, InventoryEvent, InventoryItem, StationAsset

        labels = [
            Defect.Category.FACILITY.label, Defect.Category.KEY.label, Defect.Category.DEVICE.label,
            StationAsset.Kind.DEVICE.label, StationAsset.Status.LIMITED.label, StationAsset.Status.OOB.label,
            InventoryItem.Kind.KEY.label, InventoryEvent.Action.CHECKIN.label,
            ChecklistSchedule.Interval.DAILY.label, ChecklistSchedule.Interval.WEEKLY.label,
        ]
        self.assertEqual(labels, [
            "Gebäude", "Schlüssel", "Gerät", "Gerät", "Eingeschränkt", "Außer Betrieb",
            "Schlüssel", "Rückgabe", "Täglich", "Wöchentlich",
        ])
        # Die gespeicherten Werte bleiben gleich.
        self.assertEqual(Defect.Category.FACILITY.value, "facility")


@override_settings(**SANDBOX_ON)
class DemoStatsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_only_anonymous_daily_counters_are_stored(self):
        fields = {field.name for field in DemoDailyStat._meta.get_fields()}
        self.assertEqual(fields, {"id", "day", "started", "tour_completed", "feedback"})

    def test_demo_start_counts_for_today(self):
        start_demo(self.client)
        start_demo(self.client_class())
        stat = DemoDailyStat.objects.get(day=timezone.localdate())
        self.assertEqual((stat.started, stat.tour_completed, stat.feedback), (2, 0, 0))

    def test_completed_tour_counts_on_the_start_day_when_the_demo_is_deleted(self):
        start_demo(self.client)
        started_day = timezone.localdate(DemoSandbox.objects.get().created_at)
        from core.demo_sandbox import TOUR_FLAGS

        # Nur die Datenabfrage ist ersetzt; record_purge läuft wie beim echten Löschen.
        with mock.patch("core.demo_sandbox._tour_flags", return_value=dict.fromkeys(TOUR_FLAGS, True)):
            with self.assertNoLogs("core.demo_stats", "WARNING"):
                self.client.post(reverse("logout"))
        self.assertFalse(DemoSandbox.objects.exists())
        self.assertEqual(DemoDailyStat.objects.get(day=started_day).tour_completed, 1)

    def test_unfinished_tour_does_not_count(self):
        start_demo(self.client)
        self.client.post(reverse("logout"))
        self.assertFalse(DemoSandbox.objects.exists())
        self.assertEqual(DemoDailyStat.objects.get().tour_completed, 0)

    def test_feedback_counts_without_storing_anything_else(self):
        self.client.post(reverse("feedback"), {"kind": "praise", "message": "Klasse Demo", "consent": "on"})
        self.assertEqual(DemoDailyStat.objects.get().feedback, 1)

    @override_settings(DEMO_SANDBOX=False)
    def test_feedback_is_not_counted_without_public_demo(self):
        self.client.post(reverse("feedback"), {"kind": "praise", "message": "Klasse", "consent": "on"})
        self.assertFalse(DemoDailyStat.objects.exists())

    def test_counting_errors_never_block_a_demo(self):
        with mock.patch.object(DemoDailyStat.objects, "get_or_create", side_effect=DatabaseError("weg")):
            response = self.client.post(reverse("login"), DEMO)
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(DemoSandbox.objects.count(), 1)

    def test_operator_sees_figures_in_feedback_inbox(self):
        today = timezone.localdate()
        DemoDailyStat.objects.create(day=today, started=8, tour_completed=2, feedback=1)
        DemoDailyStat.objects.create(day=today - timedelta(days=10), started=4, tour_completed=1)
        station = Station.objects.create(name="Betrieb", slug="betrieb")
        admin = User.objects.create_user("betreiber", password="x" * 16)
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        self.client.force_login(admin)
        page = self.client.get(reverse("feedback_inbox"))
        self.assertContains(page, "Demo-Kennzahlen")
        self.assertContains(page, "<dt>Demos in 7 Tagen</dt><dd>8</dd>", html=False)
        self.assertContains(page, "<dt>Demos in 30 Tagen</dt><dd>12</dd>", html=False)
        self.assertContains(page, "(25 %)")

    @override_settings(DEMO_SANDBOX=False)
    def test_no_figures_without_public_demo(self):
        station = Station.objects.create(name="Betrieb", slug="betrieb")
        admin = User.objects.create_user("betreiber", password="x" * 16)
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        self.client.force_login(admin)
        self.assertNotContains(self.client.get(reverse("feedback_inbox")), "Demo-Kennzahlen")

    def test_management_command_prints_daily_figures(self):
        DemoDailyStat.objects.create(day=timezone.localdate(), started=5, tour_completed=1, feedback=2)
        out = StringIO()
        call_command("demo_stats", "--tage", "7", stdout=out)
        self.assertIn("Summe 7 Tage: 5 Demos, 1 Rundgänge (20 %), 2 Rückmeldungen", out.getvalue())


class LockScreenPhoneTests(TestCase):
    def test_photo_credit_on_phones_flows_above_the_unlock_button(self):
        # Am Handy lag der fest stehende Lizenzhinweis halb unter dem Knopf
        # „Zum Entsperren antippen“ (CC BY-SA verlangt eine lesbare Quelle).
        css = (STATIC / "lockscreen.css").read_text(encoding="utf-8")
        block = css[css.index("@media (max-width: 40rem)"):]
        rule = re.search(r"\.is-preview \.lock-credit \{([^}]*)\}", block)
        self.assertIsNotNone(rule)
        self.assertIn("position: static", rule.group(1))
        self.assertIn("margin: 0 1rem 5.5rem", rule.group(1))


@override_settings(**SANDBOX_ON)
class TourLanguageTests(TestCase):
    """Englische Oberfläche auf dem Rundgang: keine deutschen Auswahllisten und Meldungen."""

    def setUp(self):
        cache.clear()

    def test_handover_and_defect_choices_follow_the_language(self):
        from django.utils import translation
        from django.utils.functional import Promise

        from core.wachalltag_models import Defect

        self.assertIsInstance(HandoverEntry.Priority.URGENT.label, Promise)
        self.assertIsInstance(Defect.Status.OPEN.label, Promise)
        with translation.override("en"):
            self.assertEqual(
                [str(HandoverEntry.Priority.URGENT.label), str(HandoverEntry.Category.STATION.label),
                 str(HandoverEntry.Status.OPEN.label), str(Defect.Priority.IMPORTANT.label)],
                ["Urgent", "Station", "Open", "Important"],
            )
        with translation.override("de"):
            self.assertEqual(str(HandoverEntry.Priority.URGENT.label), "Dringend")

    def test_tour_handover_form_shows_the_priority_in_english(self):
        self.client.post(reverse("login"), DEMO, HTTP_ACCEPT_LANGUAGE="en")
        form = self.client.get(f'{reverse("handover_create")}?vorlage=sauerstoff', HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(form, '<option value="urgent" selected>Urgent</option>')

    def test_routine_check_message_uses_typographic_quotes(self):
        start_demo(self.client)
        response = self.client.post(reverse("mpg_routine_check", args=["demo-defi-rtw1"]), {"quick_pass": "1"},
                                    follow=True)
        self.assertContains(response, "Funktionskontrolle für „Defibrillator/Monitor RTW 83-1“ gespeichert.")


class WasteCalendarLabelTests(TestCase):
    def test_settings_labels_use_real_umlauts(self):
        from django.utils import translation

        from core.forms import StationSettingsForm

        # Unabhängig von der Sprache, die ein vorheriger Test aktiviert hat.
        with translation.override("de"):
            form = StationSettingsForm(instance=Station.get_default())
            self.assertEqual(str(form.fields["waste_calendar_enabled"].label), "Müllkalender aktiviert")
            self.assertEqual(str(form.fields["waste_calendar_url"].label), "Müllkalender-ICS-URL")
            self.assertNotIn("Muellkalender", form.as_p())
