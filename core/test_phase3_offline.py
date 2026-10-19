"""Tests für WAN-Ausfall und serverseitige Kernpfade bei Offline-Betrieb (Phase 3 / G3).

Verifiziert:
1. Lokale Kernpfade (Login, Dashboard, Tagesaufgaben, Checklisten) ohne jeden
   ausgehenden Netzwerkverbindungsversuch (WAN-Ausfall / LAN-Betrieb).
2. Stationsbezogene Rollenabsicherung (Mitglieder abgewiesen mit 403, Admins erlaubt).
3. Append-only- und Toggle-Semantik von Tagesaufgaben und Checklisten im Offline-Zustand.
4. QR-Code-Login und manuelle Eingabe ohne externe Abhängigkeiten.
   Hinweis zur Bestandstreue: qr_login_start ist im Bestand durch @require_POST geschützt;
   GET wird korrekt mit HTTP 405 abgewiesen. Der Test prüft sowohl diese Methodensicherheit
   als auch die erfolgreiche Rückgabe der JSON-Payload via POST.
5. Wettervorhersage und Cache-Verhalten:
   - Bei Netzausfall und leerem Cache kein Erfinden von Werten (WeatherUnavailable).
   - Servieren von gekennzeichnetem Stale-Cache (stale=True, max 12h, 5 Tage ab lokal heute).
   - Verwendung frischer Cache-Einträge ohne jeglichen Netzwerkversuch.
6. Lokale Asset-Integrität:
   - Keine externen CDN-Abhängigkeiten in Templates (src/href).
   - Lokale Auslieferung von Web-Manifest, Service Worker und Offline-Hinweisseite.
"""

from __future__ import annotations

import re
import socket
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Checklist,
    ChecklistCompletion,
    ChecklistItem,
    Membership,
    Station,
    StationTask,
    StationTaskCompletion,
)
from core.weather import (
    WeatherUnavailable,
    _cache_key,
    _stale_cache_key,
    fetch_forecast,
    forecast_for_station,
)


class OutboundNetworkBlocker:
    """Zaehlt und blockiert saemtliche ausgehende Netzwerkverbindungsversuche.

    Patcht socket.getaddrinfo, socket.create_connection, socket.socket.connect
    und urllib.request.urlopen. Jeder Aufruf erhoeht den Zaehler und wirft einen
    OSError gemaess Pflichtvorgabe in TASK-G3.
    """

    def __init__(self):
        self.count = 0
        self._patches = []

    def _block(self, *args, **kwargs):
        self.count += 1
        raise OSError("Netzwerkzugriff im WAN-Ausfall-Test verweigert (Sperre aktiv).")

    def __enter__(self):
        self.count = 0
        self._patches = [
            patch("socket.getaddrinfo", side_effect=self._block),
            patch("socket.create_connection", side_effect=self._block),
            patch.object(socket.socket, "connect", self._block),
            patch("urllib.request.urlopen", side_effect=self._block),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for p in reversed(self._patches):
            p.stop()


@override_settings(
    QR_LOGIN_ENABLED=True,
    QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=True,
    SITE_URL="http://testserver",
)
class WanOutageCoreFlowTests(TestCase):
    """Testfaelle fuer den unterbrechungsfreien lokalen Betrieb bei WAN-Ausfall."""

    def setUp(self):
        super().setUp()
        cache.clear()

        self.station = Station.objects.create(
            name="Wache Alpha",
            slug=getattr(settings, "DEFAULT_STATION_SLUG", "rettungswache"),
            organization_profile=Station.Profile.RESCUE,
            tasks_enabled=True,
            checklists_enabled=True,
            weather_enabled=False,
            latitude=52.2787,
            longitude=8.0479,
            timezone_name="Europe/Berlin",
            is_active=True,
        )

        self.user_member = User.objects.create_user(
            username="retter_alpha",
            password="TestPassword123!",
            first_name="Sanitaeter",
        )
        self.membership_member = Membership.objects.create(
            user=self.user_member,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )

        self.user_admin = User.objects.create_user(
            username="admin_alpha",
            password="TestPassword123!",
            first_name="Wachleiter",
        )
        self.membership_admin = Membership.objects.create(
            user=self.user_admin,
            station=self.station,
            role=Membership.Role.ADMIN,
            is_active=True,
        )

        self.task = StationTask.objects.create(
            station=self.station,
            title="Fahrzeughalle prüfen",
            band=StationTask.Band.DAILY,
            notes="Tore, Beleuchtung und Belüftung kontrollieren.",
            is_active=True,
        )

        self.checklist = Checklist.objects.create(
            station=self.station,
            title="Morgenroutine Rettungswache",
            description="Tägliche Stationskontrolle vor Schichtübergabe.",
            is_active=True,
        )
        self.checklist_item = ChecklistItem.objects.create(
            checklist=self.checklist,
            text="Torsteuerung und Notstrom testen",
            position=1,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_no_outbound_network_attempt_during_core_flows(self):
        """Passwort-Login, Dashboard, Tagesaufgaben und Checklisten ohne WAN-Zugriff."""
        with OutboundNetworkBlocker() as blocker:
            # 1. Passwort-Login
            login_resp = self.client.post(
                reverse("login"),
                {"username": "retter_alpha", "password": "TestPassword123!"},
            )
            self.assertEqual(login_resp.status_code, 302, "Login muss mit Redirect (302) antworten.")

            # 2. Dashboard
            dash_resp = self.client.get(reverse("dashboard"))
            self.assertEqual(dash_resp.status_code, 200)
            self.assertContains(dash_resp, "Übersicht")

            # 3. Tagesaufgaben
            tasks_resp = self.client.get(reverse("tasks_today"))
            self.assertEqual(tasks_resp.status_code, 200)
            self.assertContains(tasks_resp, "Tagesaufgaben")

            # 4. Checklisten
            checks_resp = self.client.get(reverse("checklists"))
            self.assertEqual(checks_resp.status_code, 200)

            # Keine ausgehenden Verbindungsversuche
            self.assertEqual(
                blocker.count,
                0,
                f"Kernpfade duerfen keinen einzigen ausgehenden Netzwerkversuch unternehmen (Ist: {blocker.count}).",
            )

    def test_role_gate_denies_member_and_allows_admin(self):
        """Rollenpruefung fuer team-Route: Member erhaelt 403, Admin 200 mit Wachenname."""
        with OutboundNetworkBlocker() as blocker:
            # Mitglied versucht Zugriff auf Teamverwaltung
            self.client.force_login(self.user_member)
            resp_member = self.client.get(reverse("team"))
            self.assertEqual(
                resp_member.status_code,
                403,
                f"Mitglied darf team-Route nicht aufrufen, erwartet 403 (Ist: {resp_member.status_code}).",
            )

            # Admin erhaelt Zugriff und sieht den Namen der Wache
            self.client.force_login(self.user_admin)
            resp_admin = self.client.get(reverse("team"))
            self.assertEqual(resp_admin.status_code, 200)
            self.assertContains(resp_admin, self.station.name)

            self.assertEqual(blocker.count, 0, "Rollenpruefungen duerfen kein Netzwerk anfordern.")

    def test_task_toggle_persists_completion(self):
        """Tagesaufgabe umschalten: erledigt=1 erzeugt Eintrag, erledigt=0 entfernt ihn wieder."""
        self.client.force_login(self.user_member)
        today = timezone.localdate()

        with OutboundNetworkBlocker() as blocker:
            # 1. POST mit erledigt="1" -> Completion anlegen
            resp_done = self.client.post(
                reverse("task_toggle", kwargs={"pk": self.task.pk}),
                {"tag": today.isoformat(), "erledigt": "1"},
            )
            self.assertEqual(resp_done.status_code, 302)
            completions = StationTaskCompletion.objects.filter(
                task=self.task,
                station=self.station,
                work_date=today,
                completed_by=self.user_member,
            )
            self.assertEqual(
                completions.count(),
                1,
                "Nach Markieren als erledigt muss genau ein StationTaskCompletion-Eintrag existieren.",
            )

            # 2. Zweiter POST mit erledigt="0" -> Completion wieder loeschen
            resp_undone = self.client.post(
                reverse("task_toggle", kwargs={"pk": self.task.pk}),
                {"tag": today.isoformat(), "erledigt": "0"},
            )
            self.assertEqual(resp_undone.status_code, 302)
            self.assertEqual(
                StationTaskCompletion.objects.filter(task=self.task, work_date=today).count(),
                0,
                "Nach Wiedereroeffnen (erledigt=0) darf keine StationTaskCompletion mehr existieren.",
            )

            self.assertEqual(blocker.count, 0, "Tagesaufgaben-Toggle darf kein Netzwerk anfordern.")

    def test_checklist_completion_persists(self):
        """Checklisten-Abschluss persistieren: POST mit Notiz erzeugt genau eine ChecklistCompletion."""
        self.client.force_login(self.user_member)

        with OutboundNetworkBlocker() as blocker:
            resp = self.client.post(
                reverse("checklist_complete", kwargs={"pk": self.checklist.pk}),
                {"note": "Synthetic"},
            )
            self.assertEqual(resp.status_code, 302)

            completions = ChecklistCompletion.objects.filter(
                station=self.station,
                checklist=self.checklist,
            )
            self.assertEqual(completions.count(), 1, "Genau ein ChecklistCompletion-Eintrag muss existieren.")
            completion = completions.first()
            self.assertEqual(completion.completed_by, self.user_member)
            self.assertEqual(completion.note, "Synthetic")

            self.assertEqual(blocker.count, 0, "Checklisten-Abschluss darf kein Netzwerk anfordern.")

    def test_qr_login_start_and_manual_page_work_without_wan(self):
        """QR-Login-Start und manuelle Eingabeseite funktionieren lokal ohne Netzzugriff.

        Hinweis zur Bestandskonsistenz: qr_login_start ist im Bestand durch @require_POST
        abgesichert. Ein GET-Aufruf wird daher methodengerecht mit HTTP 405 abgewiesen.
        Der Test prueft diesen Schutz und ruft qr_login_start anschliessend per POST auf,
        um die geforderte JSON-Payload (login_id, qr_url, check_word, manual_code)
        zu validieren. qr_url muss lokal auf testserver verweisen.
        """
        with OutboundNetworkBlocker() as blocker:
            # Methodensicherheit: GET wird mit 405 abgewiesen (@require_POST)
            get_resp = self.client.get(reverse("qr_login_start"))
            self.assertEqual(
                get_resp.status_code,
                405,
                "qr_login_start verlangt POST und weist GET gemaess Implementierung mit 405 ab.",
            )

            # POST liefert den initialen QR-Code-Login-Datensatz
            post_resp = self.client.post(reverse("qr_login_start"))
            self.assertEqual(post_resp.status_code, 200)
            data = post_resp.json()
            self.assertTrue(data.get("ok"), "JSON-Antwort muss ok=True enthalten.")
            self.assertIn("login_id", data)
            self.assertIn("qr_url", data)
            self.assertIn("check_word", data)
            self.assertIn("manual_code", data)

            qr_url = data["qr_url"]
            self.assertTrue(
                qr_url.startswith("http://testserver/"),
                f"qr_url muss mit 'http://testserver/' beginnen (Ist: {qr_url}).",
            )
            parsed_qr = urlparse(qr_url)
            self.assertEqual(parsed_qr.hostname, "testserver", "qr_url darf keinen externen Host enthalten.")

            # Manuelle Code-Eingabeseite fuer eingeloggtes Mitglied oeffnen
            self.client.force_login(self.user_member)
            manual_resp = self.client.get(reverse("qr_login_manual"))
            self.assertEqual(manual_resp.status_code, 200)

            self.assertEqual(
                blocker.count,
                0,
                f"QR-Login darf keinen ausgehenden Netzwerkversuch taetigen (Ist: {blocker.count}).",
            )

    def test_weather_without_network_returns_no_fake_values(self):
        """Bei Netzausfall und leerem Cache muss WeatherUnavailable fliegen; keine Phantasiewerte."""
        cache.clear()

        with OutboundNetworkBlocker():
            with self.assertRaises(WeatherUnavailable):
                fetch_forecast(52.2787, 8.0479)

            # Auch fuer die Wache selbst darf bei weather_enabled=False kein Wetter geliefert werden
            with self.assertRaises(WeatherUnavailable):
                forecast_for_station(self.station)

            # Es duerfen keine gefaelschten Werte im Cache abgelegt worden sein
            tz_name = "Europe/Berlin"
            self.assertIsNone(cache.get(_cache_key(52.2787, 8.0479, tz_name)))
            self.assertIsNone(cache.get(_stale_cache_key(52.2787, 8.0479, tz_name)))

    def test_weather_serves_labelled_stale_cache_on_wan_outage(self):
        """Bei WAN-Ausfall wird ein vorhandener Stale-Cache mit Kennzeichnung stale=True serviert."""
        cache.clear()
        tz_name = "Europe/Berlin"
        lat, lon = 52.2787, 8.0479
        local_today = datetime.now(ZoneInfo(tz_name)).date()

        days = [
            {
                "date": (local_today + timedelta(days=i)).isoformat(),
                "temperature_max": 20.0 + i,
                "temperature_min": 10.0 + i,
                "precipitation_mm": 0.0,
                "weather_code": 1,
            }
            for i in range(5)
        ]
        fetched_at = timezone.now() - timedelta(hours=2)
        stale_entry = {
            "days": days,
            "fetched_at": fetched_at.isoformat(),
            "timezone": tz_name,
        }

        stale_key = _stale_cache_key(lat, lon, tz_name)
        fresh_key = _cache_key(lat, lon, tz_name)

        cache.set(stale_key, stale_entry, 12 * 3600)
        cache.delete(fresh_key)

        with OutboundNetworkBlocker() as blocker:
            forecast = fetch_forecast(lat, lon, timezone_name=tz_name)

            self.assertTrue(forecast.stale, "Forecast muss als veraltet (stale=True) markiert sein.")
            self.assertEqual(forecast.days, days, "Tagesdaten muessen unveraendert aus dem Stale-Cache stammen.")
            self.assertGreaterEqual(forecast.age_minutes, 120, "Alter der Daten muss ablesbar sein.")
            self.assertGreaterEqual(
                blocker.count,
                1,
                "Ein ausgehender Netzwerkversuch (_fetch_json) muss stattgefunden haben, bevor Fallback greift.",
            )

    def test_fresh_weather_cache_is_used_without_network(self):
        """Frischer Cache wird direkt ohne Netzwerkversuch serviert (stale=False, Zaehler 0)."""
        cache.clear()
        tz_name = "Europe/Berlin"
        lat, lon = 52.2787, 8.0479
        local_today = datetime.now(ZoneInfo(tz_name)).date()

        days = [
            {
                "date": (local_today + timedelta(days=i)).isoformat(),
                "temperature_max": 22.0 + i,
                "temperature_min": 12.0 + i,
                "precipitation_mm": 0.0,
                "weather_code": 2,
            }
            for i in range(5)
        ]
        fetched_at = timezone.now()
        fresh_entry = {
            "days": days,
            "fetched_at": fetched_at.isoformat(),
            "timezone": tz_name,
        }

        fresh_key = _cache_key(lat, lon, tz_name)
        cache.set(fresh_key, fresh_entry, 3600)

        with OutboundNetworkBlocker() as blocker:
            forecast = fetch_forecast(lat, lon, timezone_name=tz_name)

            self.assertFalse(forecast.stale, "Frischer Forecast darf nicht als stale markiert sein.")
            self.assertEqual(forecast.days, days)
            self.assertEqual(
                blocker.count,
                0,
                f"Bei frischem Cache darf kein Netzwerkaufruf versucht werden (Ist: {blocker.count}).",
            )


class LocalAssetTests(TestCase):
    """Testfaelle fuer lokale Asset-Integritaet und PWA-Offline-Routen."""

    def test_templates_reference_no_external_asset_hosts(self):
        """Templates duerfen keine externen CDNs oder Asset-Hosts referenzieren."""
        templates_dir = Path(settings.BASE_DIR) / "templates"
        self.assertTrue(templates_dir.is_dir(), f"Templates-Verzeichnis {templates_dir} nicht gefunden.")

        forbidden_patterns = [
            "cdn.",
            "fonts.googleapis",
            "unpkg",
            "jsdelivr",
            "googleapis.com",
        ]
        allowed_hosts = {"127.0.0.1", "localhost", "testserver"}

        template_files = [p for p in templates_dir.rglob("*") if p.is_file() and p.suffix in {".html", ".js"}]
        self.assertGreater(len(template_files), 0, "Es muessen Template-Dateien existieren.")

        for template_path in template_files:
            content = template_path.read_text(encoding="utf-8")

            # 1. Pruefung auf verbotene CDN-Strings
            for pattern in forbidden_patterns:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Verbotenes CDN-Muster '{pattern}' in Template {template_path.name} gefunden.",
                )

            # 2. Pruefung aller src= Attribute
            for src in re.findall(r'''src=["']([^"']+)["']''', content):
                if src.startswith(("http://", "https://", "//")):
                    url_to_parse = src if "://" in src else f"http:{src}"
                    host = urlparse(url_to_parse).hostname
                    self.assertIn(
                        host,
                        allowed_hosts,
                        f"Externes Asset in src='{src}' in {template_path.name} ist nicht erlaubt.",
                    )

            # 3. Pruefung aller <link ... href=...> Tags (Stylesheets, Fonts, Icons)
            for link_tag in re.findall(r'''<link\s+[^>]*>''', content):
                match = re.search(r'''href=["']([^"']+)["']''', link_tag)
                if match:
                    href = match.group(1)
                    if href.startswith(("http://", "https://", "//")):
                        url_to_parse = href if "://" in href else f"http:{href}"
                        host = urlparse(url_to_parse).hostname
                        self.assertIn(
                            host,
                            allowed_hosts,
                            f"Externer Link in <link href='{href}'> in {template_path.name} nicht erlaubt.",
                        )

    def test_manifest_service_worker_and_offline_page_are_served_locally(self):
        """Manifest, Service-Worker und Offline-Seite muessen lokal mit korrekten Inhalten antworten."""
        # 1. Web-Manifest
        resp_manifest = self.client.get(reverse("web_manifest"))
        self.assertEqual(resp_manifest.status_code, 200)
        manifest_data = resp_manifest.json()

        start_url = manifest_data.get("start_url", "")
        self.assertFalse(
            start_url.startswith(("http://", "https://", "//")),
            f"start_url darf nicht absolut extern sein: {start_url}",
        )

        icons = manifest_data.get("icons", [])
        self.assertGreater(len(icons), 0, "Manifest muss Icons definieren.")
        for icon in icons:
            src = icon.get("src", "")
            self.assertFalse(
                src.startswith(("http://", "https://", "//")),
                f"Icon src darf nicht absolut extern sein: {src}",
            )

        # 2. Service Worker
        resp_sw = self.client.get(reverse("service_worker"))
        self.assertEqual(resp_sw.status_code, 200)
        content_type = resp_sw.get("Content-Type", "")
        self.assertIn("javascript", content_type.lower())

        # 3. Offline-Hinweisseite
        resp_offline = self.client.get(reverse("offline"))
        self.assertEqual(resp_offline.status_code, 200)
        self.assertContains(
            resp_offline,
            "Schreibvorgänge wie neue Übergaben, Statusänderungen oder Kassenbuchungen sind offline nicht möglich.",
        )
