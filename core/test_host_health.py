"""Zustand der Host-Überwachung in Wachwerk (core/host_health.py).

Parser (streng, nie Ausnahmen), Banner nur für Master-Admins echter Wachen,
Abschnitt „Betrieb und Datensicherung“ auf /system/ und Meldungen des
notify-workers (Posteingang, E-Mail, Signal).
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
import re
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from core import host_health
from core.api.views import hash_api_token
from core.demo_models import DemoSandbox
from core.host_health import (
    MAX_PROBLEMS,
    PROBLEM_TEXTS,
    Problem,
    notify_host_health,
    parse_status,
    read_host_health,
)
from core.models import ApiToken, Membership, Station
from core.notification_models import SignalContact, SignalOutbox, UserNotification

ROOT = Path(__file__).resolve().parents[1]
HEALTH_SCRIPT = ROOT / "deploy" / "hetzner" / "wachwerk-health.sh"
ALERT = "20261031T091500Z"
# Codes, die erst die USB-Rotation (Kopie außer Haus mit Sticks) schreibt.
PENDING_ROTATION_CODES = {("offsite", "no_medium"), ("offsite", "rotation")}


def iso(moment: datetime) -> str:
    return moment.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def status(**overrides) -> dict:
    now = timezone.now()
    data = {
        "schema": 1, "checked_at": iso(now), "state": "ok", "failing_since": None,
        "alert": "", "last_alert": "", "problems": [], "notes": [],
        "backup": {"newest_at": iso(now - timedelta(hours=3)), "age_hours": 3},
        "offsite": None, "restore_test": None, "restore_probe": None,
    }
    data.update(overrides)
    return data


def alerting(*problems, **overrides) -> dict:
    items = [{"area": a, "issue": i, "param": p} for a, i, p in problems] or [
        {"area": "service", "issue": "stopped", "param": "backup"}]
    defaults = {"state": "problem", "alert": ALERT, "last_alert": ALERT, "problems": items,
                "failing_since": iso(timezone.now() - timedelta(minutes=10))}
    defaults.update(overrides)
    return status(**defaults)


class StatusFileMixin:
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory(prefix="wachwerk-host-health-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "status.json"
        host_health.reset_state()
        self.addCleanup(host_health.reset_state)
        override = override_settings(HOST_HEALTH_FILE=str(self.path))
        override.enable()
        self.addCleanup(override.disable)

    def write(self, data) -> None:
        """Wie der Host: neue Datei daneben, dann ersetzen (neue Inode)."""
        temporary = self.dir / ".status.tmp"
        temporary.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        os.replace(temporary, self.path)


class ParserTests(StatusFileMixin, SimpleTestCase):
    def test_valid_status_is_parsed(self):
        now = timezone.now().replace(microsecond=0)
        self.write(status(
            checked_at=iso(now), state="problem", alert=ALERT, last_alert=ALERT,
            failing_since=iso(now - timedelta(minutes=12)),
            problems=[{"area": "backup", "issue": "stale", "param": "31"}],
            notes=[{"area": "service", "issue": "restarted", "param": "web"}],
            offsite={"kind": "usb", "newest_at": iso(now - timedelta(hours=5)), "age_hours": 5,
                     "sync_age_hours": 2, "away_age_days": 6,
                     "media": [{"name": "Stick A", "last_write": iso(now - timedelta(days=6))},
                               {"name": "Stick B", "last_write": None}]},
            restore_test={"at": iso(now - timedelta(days=2)), "ok": True, "dump_at": None, "tables": 140,
                          "migrations": 72, "stations": 1, "users": 25, "audit": 900},
            restore_probe={"at": iso(now - timedelta(days=40)), "ok": False, "sha256": "a" * 64},
        ))
        health = read_host_health()
        self.assertTrue(health.available)
        self.assertEqual(health.checked_at, now)
        self.assertTrue(health.alerting)
        self.assertEqual(health.failing_since, now - timedelta(minutes=12))
        self.assertEqual(health.problems, (Problem("backup", "stale", "31"),))
        self.assertEqual(health.problems[0].text, "Das neueste Backup ist 31 Stunden alt.")
        self.assertEqual(health.notes[0].param, "web")
        self.assertEqual(health.backup_age_hours, 3)
        self.assertEqual((health.offsite_kind, health.offsite_sync_age_hours, health.offsite_away_age_days),
                         ("usb", 2, 6))
        self.assertEqual(health.offsite_kind_label, "USB-Sticks im Wechsel")
        self.assertEqual([m.name for m in health.media], ["Stick A", "Stick B"])
        self.assertIsNone(health.media[1].last_write)
        self.assertEqual((health.restore_test.ok, health.restore_test.tables, health.restore_test.migrations),
                         (True, 140, 72))
        self.assertEqual(health.restore_probe.sha256, "a" * 64)
        self.assertFalse(health.restore_probe.ok)
        self.assertFalse(health.is_stale())

    def test_missing_file_is_unavailable(self):
        health = read_host_health()
        self.assertFalse(health.available)
        self.assertFalse(health.needs_banner())

    def test_broken_inputs_are_ignored(self):
        valid = status()
        cases = {
            "kein JSON": "{nicht json",
            "zu groß": json.dumps(status(padding="x" * (65 * 1024))),
            "Liste": json.dumps([valid]),
            "Schema 2": json.dumps(status(schema=2)),
            "Schema true": json.dumps(status(schema=True)),
            "Schema als Text": json.dumps(status(schema="1")),
            "ohne checked_at": json.dumps({k: v for k, v in valid.items() if k != "checked_at"}),
            "checked_at mit Zeilenumbruch": json.dumps(status(checked_at=valid["checked_at"] + "\n")),
            "checked_at ungültig": json.dumps(status(checked_at="2026-13-45T25:00:00Z")),
            "kein UTF-8": b"\xff\xfe{}",
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                host_health.reset_state()
                self.path.unlink(missing_ok=True)
                if isinstance(raw, bytes):
                    self.path.write_bytes(raw)
                else:
                    self.write(raw)
                self.assertFalse(read_host_health().available)
        with self.subTest(name="Symlink"):
            self.path.unlink()
            target = self.dir / "echt.json"
            target.write_text(json.dumps(valid))
            self.path.symlink_to(target)
            self.assertFalse(read_host_health().available)
        with self.subTest(name="Ordner"):
            self.path.unlink()
            self.path.mkdir()
            self.assertFalse(read_host_health().available)
        with self.subTest(name="FIFO"):
            self.path.rmdir()
            os.mkfifo(self.path)
            self.assertFalse(read_host_health().available)

    def test_invalid_fields_are_dropped_individually(self):
        problems = [{"area": "service", "issue": "stopped", "param": "<script>"}]
        problems += [{"area": "disk", "issue": "full", "param": str(90 + n)} for n in range(24)]
        problems.insert(1, {"area": "Service", "issue": "stopped"})
        problems.insert(2, "kein Objekt")
        health = parse_status(status(
            state="kaputt", alert="20261031", last_alert=123, problems=problems,
            backup={"newest_at": "gestern", "age_hours": True},
            offsite={"kind": "usb", "age_hours": -1, "sync_age_hours": "2",
                     "media": [{"name": "<b>Stick</b>"}, {"name": "Stick C", "last_write": "x"}] + [
                         {"name": f"Stick {n}"} for n in range(9)]},
            restore_test={"at": "nie", "ok": True},
            restore_probe={"at": iso(timezone.now()), "ok": "ja", "sha256": "xyz", "tables": 10**9},
        ))
        self.assertTrue(health.available)
        self.assertEqual(len(health.problems), MAX_PROBLEMS)
        self.assertEqual(health.problems[0], Problem("service", "stopped", ""))
        self.assertEqual(health.problems[0].text, "Weitere Meldung der Überwachung.")
        self.assertEqual(health.state, "problem", "ungültiger Zustand: aus den Meldungen abgeleitet")
        self.assertEqual((health.alert, health.last_alert), ("", ""))
        self.assertFalse(health.alerting)
        self.assertIsNone(health.backup_newest_at)
        self.assertIsNone(health.backup_age_hours)
        self.assertIsNone(health.offsite_age_hours)
        self.assertIsNone(health.offsite_sync_age_hours)
        self.assertEqual([m.name for m in health.media], ["Stick C", "Stick 0", "Stick 1", "Stick 2", "Stick 3"])
        self.assertIsNone(health.media[0].last_write)
        self.assertIsNone(health.restore_test)
        self.assertIsNone(health.restore_probe.ok)
        self.assertEqual(health.restore_probe.sha256, "")
        self.assertIsNone(health.restore_probe.tables)
        unknown_kind = parse_status(status(offsite={"kind": "ftp", "age_hours": 3}))
        self.assertEqual((unknown_kind.offsite_kind, unknown_kind.offsite_age_hours), ("", None))

    def test_unknown_codes_get_generic_text(self):
        self.assertEqual(Problem("geheim", "befehl", "rm").text, "Weitere Meldung der Überwachung.")
        self.assertEqual(Problem("service", "stopped", "").text, "Weitere Meldung der Überwachung.")
        self.assertEqual(Problem("service", "stopped", "backup").text, "Dienst „backup“ läuft nicht.")

    def test_problem_texts_are_translated_to_english(self):
        for key in PROBLEM_TEXTS:
            problem = Problem(*key, param="7")
            with translation.override("de"):
                german = problem.text
            with translation.override("en"):
                english = problem.text
            with self.subTest(code=key):
                self.assertNotEqual(german, english)
                self.assertNotIn("%(", english)
        with translation.override("en"):
            self.assertNotEqual(Problem("x", "y").text, "Weitere Meldung der Überwachung.")

    def test_cache_rereads_after_atomic_replace(self):
        self.write(status())
        first = read_host_health()
        self.assertIs(read_host_health(), first, "unveränderte Datei wird nicht neu gelesen")
        self.write(alerting())
        second = read_host_health()
        self.assertTrue(second.alerting)
        self.path.unlink()
        self.assertFalse(read_host_health().available)

    def test_stale_status(self):
        old = timezone.now() - timedelta(minutes=21)
        self.write(status(checked_at=iso(old)))
        health = read_host_health()
        self.assertTrue(health.is_stale())
        self.assertTrue(health.needs_banner())
        self.assertFalse(health.is_stale(old + timedelta(minutes=19)))

    def test_every_health_code_has_a_text(self):
        """Vertrag mit wachwerk-health.sh: jeder Code hat einen Text, kein Text ist verwaist."""
        script = HEALTH_SCRIPT.read_text(encoding="utf-8")
        codes = set(re.findall(r'\b(?:bad|note) "?\$?\(?(?:codes_for )?([a-z_]+):([a-z_]+)', script))
        self.assertIn(("service", "restarting"), codes)
        self.assertIn(("test", "alert"), codes)
        self.assertGreaterEqual(len(codes), 30, codes)
        self.assertEqual(codes, set(PROBLEM_TEXTS) - PENDING_ROTATION_CODES)
        self.assertFalse(codes & PENDING_ROTATION_CODES, "Code schon im Skript: aus PENDING_ROTATION_CODES nehmen")


class HostHealthPageMixin(StatusFileMixin):
    def setUp(self):
        super().setUp()
        self.station = Station.objects.create(name="RW Nord", slug="rw-nord")
        self.admin = self.member("chefin", Membership.Role.ADMIN)

    def member(self, username, role, station=None, **user_fields):
        user = User.objects.create_user(username=username, password="pw-123456789", **user_fields)
        Membership.objects.create(user=user, station=station or self.station, role=role)
        return user


class BannerTests(HostHealthPageMixin, TestCase):
    def dashboard(self, user=None):
        self.client.force_login(user or self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_admin_sees_banner_when_alerting(self):
        self.write(alerting(("service", "stopped", "backup"), ("disk", "full", "91")))
        response = self.dashboard()
        self.assertContains(response, "data-host-health")
        self.assertContains(response, "Technische Störung.")
        self.assertContains(response, "Dienst „backup“ läuft nicht.")
        self.assertContains(response, "(+1 weitere)")
        self.assertContains(response, f'href="{reverse("system_status")}#betrieb"')
        self.assertContains(response, 'role="status"')

    def test_no_banner_before_alert_threshold(self):
        self.write(alerting(alert=""))
        self.assertNotContains(self.dashboard(), "data-host-health")
        self.write(status(last_alert=ALERT))
        self.assertNotContains(self.dashboard(), "data-host-health")

    def test_stale_status_shows_silent_monitoring(self):
        self.write(status(checked_at=iso(timezone.now() - timedelta(minutes=25))))
        response = self.dashboard()
        self.assertContains(response, "Überwachung meldet sich nicht.")
        self.assertContains(response, "Letzte Prüfung:")

    def test_other_roles_see_no_banner(self):
        self.write(alerting())
        for role in (Membership.Role.MEMBER, Membership.Role.SHIFT_LEAD, Membership.Role.CASHIER,
                     Membership.Role.AUDITOR):
            with self.subTest(role=role):
                user = self.member(f"user-{role}", role)
                self.client.force_login(user)
                response = self.client.get(reverse("audit_log" if role == Membership.Role.AUDITOR else "dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "data-host-health")

    @override_settings(TERMINAL_ENABLED=True)
    def test_terminal_session_and_lock_screen_show_no_banner(self):
        from core.terminal import COOKIE_NAME, hash_secret
        from core.terminal_models import StationTerminal

        self.write(alerting())
        StationTerminal.objects.create(station=self.station, label="Halle", token_hash=hash_secret("geraet-1"),
                                       created_by=self.admin)
        self.client.cookies[COOKIE_NAME] = "geraet-1"
        lock_screen = self.client.get(reverse("terminal_home"))
        self.assertEqual(lock_screen.status_code, 200)
        self.assertNotContains(lock_screen, "data-host-health")
        # Persönliche Anmeldung eines Master-Admins am gemeinsamen Bildschirm.
        self.client.force_login(self.admin)
        response = self.client.get(reverse("handover_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["terminal_session"])
        self.assertNotContains(response, "data-host-health")

    @override_settings(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)
    def test_demo_sandbox_admin_sees_no_banner(self):
        DemoSandbox.objects.create(station=self.station, token="demo-tok-1")
        self.write(alerting())
        self.assertNotContains(self.dashboard(), "data-host-health")
        real = Station.objects.create(name="RW Echt", slug="rw-echt")
        self.assertContains(self.dashboard(self.member("echt-admin", Membership.Role.ADMIN, real)),
                            "data-host-health")

    @override_settings(DEMO_MODE=True, DEMO_SANDBOX=False, MFA_REQUIRED=False)
    def test_shared_demo_admin_sees_no_banner_or_section_and_gets_no_alert(self):
        self.write(alerting())
        self.assertNotContains(self.dashboard(), "data-host-health")
        page = self.client.get(reverse("system_status"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="betrieb"')
        self.assertEqual(notify_host_health(), 0)
        self.assertFalse(UserNotification.objects.exists())

    def test_healthz_does_not_expose_host_status(self):
        without = self.client.get("/healthz/")
        self.write(alerting())
        with_file = self.client.get("/healthz/")
        self.assertEqual(with_file.status_code, without.status_code)
        self.assertEqual(with_file.content, without.content)
        self.assertNotIn(b"backup", with_file.content)

    def test_banner_values_are_escaped(self):
        self.write(alerting(("service", "stopped", "<script>alert(1)</script>")))
        response = self.dashboard()
        self.assertContains(response, "data-host-health")
        self.assertNotContains(response, "<script>alert(1)")
        self.assertNotContains(response, "alert(1)")

    def test_banner_adds_no_queries(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("dashboard"))
        with CaptureQueriesContext(connection) as without:
            self.client.get(reverse("dashboard"))
        self.write(alerting())
        with CaptureQueriesContext(connection) as with_file:
            response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "data-host-health")
        self.assertEqual(len(with_file), len(without))


class SystemPageTests(HostHealthPageMixin, TestCase):
    def page(self, user=None):
        self.client.force_login(user or self.admin)
        return self.client.get(reverse("system_status"))

    def test_admin_sees_backup_offsite_and_restore_facts(self):
        now = timezone.now()
        self.write(alerting(
            ("backup", "stale", "31"),
            offsite={"kind": "usb", "newest_at": iso(now - timedelta(hours=4)), "age_hours": 4,
                     "sync_age_hours": 1, "away_age_days": 5,
                     "media": [{"name": "Stick A", "last_write": iso(now - timedelta(days=5))}]},
            restore_test={"at": iso(now - timedelta(days=2)), "ok": True, "tables": 141, "migrations": 72,
                          "stations": 3, "users": 4242, "audit": 99999},
        ))
        response = self.page()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="betrieb"')
        self.assertContains(response, "Betrieb und Datensicherung")
        self.assertContains(response, "Das neueste Backup ist 31 Stunden alt.")
        self.assertContains(response, "Meldungen: 1, seit")
        self.assertContains(response, "3 h alt")
        self.assertContains(response, "USB-Sticks im Wechsel")
        self.assertContains(response, "Zuletzt übertragen vor 1 h")
        self.assertContains(response, "Kopie außer Haus, Alter in Tagen: 5")
        self.assertContains(response, "Stick „Stick A“")
        self.assertContains(response, "141 Tabellen, 72 Migrationen")
        self.assertContains(response, "erfolgreich")
        self.assertContains(response, "noch nie – vierteljährlich empfohlen")
        # Zahlen der ganzen Installation (andere Wachen, Konten) bleiben verborgen.
        self.assertNotContains(response, "4242")
        self.assertNotContains(response, "99999")

    def test_system_page_shows_calm_state(self):
        self.write(status(notes=[{"area": "service", "issue": "restarted", "param": "web"}]))
        response = self.page()
        self.assertContains(response, "alles in Ordnung")
        self.assertContains(response, "Dienst „web“ reagierte nicht und wurde neu gestartet.")
        self.assertContains(response, "nicht eingerichtet")
        self.assertNotContains(response, "vierteljährlich")

    def test_problem_below_threshold_is_marked_as_not_yet_reported(self):
        self.write(alerting(alert=""))
        self.assertContains(self.page(), "noch nicht gemeldet")

    def test_system_page_without_status_shows_setup_hint(self):
        response = self.page()
        self.assertContains(response, 'id="betrieb"')
        self.assertContains(response, "Die Überwachung des Servers ist nicht eingerichtet")
        self.assertContains(response, "deploy/lan/setup-monitoring.sh")

    def test_stale_status_is_marked(self):
        self.write(status(checked_at=iso(timezone.now() - timedelta(hours=2))))
        self.assertContains(self.page(), "die Überwachung meldet sich nicht")

    def test_non_admin_cannot_open_system_page_even_with_status(self):
        self.write(alerting())
        for role in (Membership.Role.MEMBER, Membership.Role.SHIFT_LEAD, Membership.Role.AUDITOR):
            with self.subTest(role=role):
                response = self.page(self.member(f"nicht-admin-{role}", role))
                self.assertEqual(response.status_code, 403)

    @override_settings(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)
    def test_sandbox_admin_system_page_has_no_operations_section(self):
        DemoSandbox.objects.create(station=self.station, token="demo-tok-2")
        self.write(alerting())
        response = self.page()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="betrieb"')
        self.assertNotContains(response, "Dienst „backup“")


class NotificationTests(HostHealthPageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin.email = "chefin@example.org"
        self.admin.save()

    def notes(self, **filters):
        return UserNotification.objects.filter(kind=UserNotification.Kind.SYSTEM_HEALTH, **filters)

    def notify(self, **kwargs) -> int:
        host_health.reset_state()
        return notify_host_health(**kwargs)

    def test_one_notification_per_admin_and_incident(self):
        second = self.member("vize", Membership.Role.ADMIN)
        self.write(alerting(("service", "stopped", "backup")))
        self.assertEqual(self.notify(), 2)
        rows = list(self.notes().order_by("user_id"))
        self.assertEqual([row.user for row in rows], [self.admin, second])
        for row in rows:
            self.assertEqual(row.title, "Wachwerk: technische Störung")
            self.assertIn("Dienst „backup“ läuft nicht.", row.body)
            self.assertIn("Details unter System.", row.body)
            self.assertEqual(row.url, reverse("system_status"))
            self.assertEqual(row.dedupe_key, f"host_health:{ALERT}")
            self.assertEqual(row.station, self.station)
        self.assertEqual(self.notify(), 0)
        self.assertEqual(self.notes().count(), 2)

    def test_unchanged_status_is_not_reprocessed(self):
        self.write(alerting())
        self.assertEqual(notify_host_health(), 1)
        with self.assertNumQueries(0):
            self.assertEqual(notify_host_health(), 0)

    def test_alert_body_names_time_and_first_three_problems(self):
        problems = [("service", "stopped", f"dienst-{n}") for n in range(5)]
        since = timezone.now() - timedelta(minutes=10)
        self.write(alerting(*problems, failing_since=iso(since)))
        self.notify()
        body = self.notes().get().body
        self.assertTrue(body.startswith(f"Seit {timezone.localtime(since):%H:%M} Uhr: Dienst „dienst-0“"), body)
        self.assertIn("dienst-2", body)
        self.assertNotIn("dienst-3", body)
        self.assertIn("(+2 weitere)", body)
        self.assertTrue(body.endswith("Details unter System."))
        self.assertLessEqual(len(body), 300)

    def test_members_inactive_and_demo_admins_get_nothing(self):
        self.member("mitglied", Membership.Role.MEMBER)
        self.member("kasse", Membership.Role.CASHIER)
        inactive = self.member("ehemalig", Membership.Role.ADMIN)
        Membership.objects.filter(user=inactive).update(is_active=False)
        self.member("gesperrt", Membership.Role.ADMIN, is_active=False)
        closed = Station.objects.create(name="RW Alt", slug="rw-alt", is_active=False)
        self.member("alt-admin", Membership.Role.ADMIN, closed)
        demo = Station.objects.create(name="Demo", slug="demo-1")
        DemoSandbox.objects.create(station=demo, token="demo-tok-3")
        self.member("demo-admin", Membership.Role.ADMIN, demo)
        self.write(alerting())
        self.assertEqual(self.notify(), 1)
        self.assertEqual([n.user for n in self.notes()], [self.admin])

    def test_admin_with_inactive_second_station_is_notified_where_active(self):
        older = Station.objects.create(name="RW Früher", slug="rw-frueher")
        self.assertLess(older.pk, Station.objects.create(name="RW Neu", slug="rw-neu").pk)
        user = User.objects.create_user("wechsler", password="pw-123456789")
        Membership.objects.create(user=user, station=older, role=Membership.Role.ADMIN, is_active=False)
        Membership.objects.create(user=user, station=self.station, role=Membership.Role.ADMIN)
        self.write(alerting())
        self.notify()
        row = self.notes().get(user=user)
        self.assertEqual(row.station, self.station)
        self.assertFalse(self.notes(user=user, station=older).exists())
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("dashboard")), "Wachwerk: technische Störung")

    def allow_second_active_membership(self, user, station):
        """Zweite aktive Mitgliedschaft trotz ``unique_active_membership``.

        Die Datenbank erlaubt je Person nur eine aktive Mitgliedschaft.
        admin_recipients() legt die Nachricht trotzdem nur einmal an, falls es
        je mehrere gäbe. Dafür fällt der Index nur in diesem Test weg; das
        Zurückrollen am Testende stellt ihn auf SQLite und PostgreSQL wieder her.
        """
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(user=user, station=station, role=Membership.Role.ADMIN)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP INDEX {connection.ops.quote_name('unique_active_membership')}")
        Membership.objects.create(user=user, station=station, role=Membership.Role.ADMIN)

    def test_admin_of_two_active_stations_gets_one_notification(self):
        Membership.objects.filter(user=self.admin).update(is_active=False)
        station_a = Station.objects.create(name="RW A", slug="rw-a")
        station_b = Station.objects.create(name="RW B", slug="rw-b")
        self.assertLess(station_a.pk, station_b.pk)
        user = User.objects.create_user("doppelt", password="pw-123456789")
        # Erst B, dann A: die Reihenfolge der Mitgliedschaften entscheidet nicht.
        Membership.objects.create(user=user, station=station_b, role=Membership.Role.ADMIN)
        self.allow_second_active_membership(user, station_a)
        self.assertEqual(Membership.objects.filter(user=user, is_active=True, role=Membership.Role.ADMIN).count(), 2)
        raw = "wb_test_health_token_1234567890"
        ApiToken.objects.create(
            user=user, label="t", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:me"], expires_at=timezone.now() + timedelta(days=1),
        )
        auth = {"HTTP_AUTHORIZATION": f"Token {raw}"}
        self.write(alerting())

        self.assertEqual(self.notify(), 1)
        row = self.notes().get()
        self.assertEqual((row.user, row.station), (user, station_a))
        self.assertEqual(self.notify(), 0)

        def inbox_ids():
            data = self.client.get("/api/v1/benachrichtigungen/", **auth).json()
            return [item["id"] for item in data["results"] if item["kind"] == "system_health"]

        # Wache A: Übersicht und API zeigen die Nachricht.
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("dashboard")), "Wachwerk: technische Störung")
        self.assertEqual(inbox_ids(), [row.pk])
        # Wache B (A ruht): weder Übersicht noch API zeigen sie.
        Membership.objects.filter(user=user, station=station_a).update(is_active=False)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Wachwerk: technische Störung")
        self.assertEqual(inbox_ids(), [])
        # Wieder Wache A: die API zeigt sie wieder.
        Membership.objects.filter(user=user, station=station_b).update(is_active=False)
        Membership.objects.filter(user=user, station=station_a).update(is_active=True)
        self.assertEqual(inbox_ids(), [row.pk])

    @override_settings(EMAIL_HOST="smtp.example.org", SITE_URL="https://wache.example")
    def test_email_only_with_email_host_and_address(self):
        self.member("ohne-mail", Membership.Role.ADMIN)
        self.write(alerting())
        self.assertEqual(self.notify(), 2)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["chefin@example.org"])
        self.assertEqual(message.subject, "Wachwerk: technische Störung")
        self.assertIn("Dienst „backup“ läuft nicht.", message.body)
        self.assertIn("https://wache.example/system/", message.body)
        self.assertIn("keine Inhalte aus Wachwerk", message.body)

    def test_no_email_without_email_host(self):
        self.write(alerting())
        self.notify()
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_HOST="smtp.example.org", HEALTH_ALERT_EMAIL=["betrieb@example.org"])
    def test_operator_address_gets_one_mail_per_incident(self):
        self.write(alerting())
        self.notify()
        self.notify()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["betrieb@example.org", "chefin@example.org"])

    @override_settings(SIGNAL_API_URL="http://signal:8080", SIGNAL_NUMBER="+4915112345678")
    def test_signal_only_for_verified_admin_number(self):
        other = self.member("vize", Membership.Role.ADMIN)
        SignalContact.objects.create(user=self.admin, number="+4915199999999", verified_at=timezone.now())
        SignalContact.objects.create(user=other, number="+4915188888888")
        self.write(alerting())
        self.notify()
        self.assertEqual(list(SignalOutbox.objects.values_list("recipient", flat=True)), ["+4915199999999"])
        self.assertIn("Wachwerk: technische Störung", SignalOutbox.objects.get().message)

    @override_settings(EMAIL_HOST="smtp.example.org")
    def test_email_failure_keeps_inbox_entry(self):
        self.write(alerting())
        with mock.patch("django.core.mail.get_connection", side_effect=OSError("SMTP aus")), \
                self.assertLogs("core.host_health", level="ERROR"):
            self.assertEqual(self.notify(), 1)
        self.assertEqual(self.notes().count(), 1)

    def test_recovery_notice_only_for_alerted_admins_and_marks_alert_read(self):
        self.write(alerting())
        self.notify()
        later = self.member("spaeter", Membership.Role.ADMIN)
        self.write(status(last_alert=ALERT))
        self.assertEqual(self.notify(), 1)
        recovery = self.notes(dedupe_key=f"host_health:{ALERT}:ok").get()
        self.assertEqual(recovery.user, self.admin)
        self.assertEqual(recovery.title, "Wachwerk: Störung behoben")
        self.assertIn("wieder alles in Ordnung", recovery.body)
        self.assertIsNotNone(self.notes().get(dedupe_key=f"host_health:{ALERT}").read_at)
        self.assertFalse(self.notes(user=later).exists())
        self.assertEqual(self.notify(), 0)

    def test_recovery_without_delivered_alert_sends_nothing(self):
        self.write(status(last_alert=ALERT))
        self.assertEqual(self.notify(), 0)
        self.assertFalse(self.notes().exists())

    def test_stale_alert_waits_for_worker_uptime(self):
        checked = timezone.now() - timedelta(minutes=30)
        self.write(status(checked_at=iso(checked)))
        self.assertEqual(self.notify(allow_stale_alert=False), 0)
        self.assertEqual(self.notify(allow_stale_alert=True), 1)
        row = self.notes().get()
        self.assertEqual(row.title, "Wachwerk: Überwachung meldet sich nicht")
        self.assertIn("sudo wachwerk-health --verbose", row.body)
        self.assertTrue(row.dedupe_key.startswith("host_health_stale:"))

    def test_fresh_status_marks_stale_notice_read(self):
        self.write(status(checked_at=iso(timezone.now() - timedelta(minutes=30))))
        self.notify()
        self.write(status())
        self.assertEqual(self.notify(), 0)
        self.assertIsNotNone(self.notes().get().read_at)

    def test_no_status_file_means_no_database_access(self):
        with self.assertNumQueries(0):
            self.assertEqual(self.notify(), 0)
        self.write("{kaputt")
        with self.assertNumQueries(0):
            self.assertEqual(self.notify(), 0)

    def notify_crew(self) -> str:
        """Einmaliger Lauf wie der Ersatzweg von wachwerk-health.

        close_old_connections würde unter PostgreSQL die Verbindung der
        Testtransaktion schließen (SQLite im Speicher ignoriert das).
        """
        out = io.StringIO()
        with mock.patch("core.management.commands.notify_crew.close_old_connections"):
            call_command("notify_crew", stdout=out)
        return out.getvalue()

    def test_notify_crew_survives_broken_status_file(self):
        self.write("{kaputt")
        with mock.patch("core.management.commands.notify_crew.notify_ready_vehicles", return_value=1):
            self.assertIn("1 Benachrichtigungen angelegt", self.notify_crew())
        with mock.patch("core.management.commands.notify_crew.notify_host_health", side_effect=RuntimeError("x")), \
                self.assertLogs("core.management.commands.notify_crew", level="ERROR"):
            self.notify_crew()

    def test_notify_crew_delivers_alert_but_one_off_run_never_reports_silence(self):
        self.write(alerting())
        self.notify_crew()
        self.assertEqual(self.notes().count(), 1)
        self.notes().delete()
        self.write(status(checked_at=iso(timezone.now() - timedelta(hours=1))))
        host_health.reset_state()
        self.notify_crew()
        self.assertFalse(self.notes().exists())
