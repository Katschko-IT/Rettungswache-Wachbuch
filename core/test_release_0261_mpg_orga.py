"""Regressionstests 0.26.1 „Schaden begrenzen“ – Paket Medizinprodukte, Dienstanweisungen, API.

1. Funktionskontrolle ohne Vorauswahl: Jeder Prüfpunkt ist eine Pflichtfrage
   Ja/Nein; die Schnellkontrolle verlangt eine ausdrückliche Bestätigung.
2. Lesebestätigung von Dienstanweisungen speichert weder IP noch Browser und
   zeigt bzw. exportiert Altbestände davon nicht mehr.
3. Die API-Statistik verrät keine offenen Mängel je Person mehr.
"""
import csv
import io
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.api.views import hash_api_token
from core.models import ApiToken, Membership, NewsAcknowledgement, Station
from core.mpg_forms import DeviceRoutineCheckForm, MaintenanceLogForm
from core.mpg_models import DeviceRoutineCheck, MaintenanceLog, MedicalDevice
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision
from core.wachalltag_models import Defect, HandoverAck

CHECK_POINTS = ("battery_ok", "visual_ok", "function_ok")


def _inputs(html: str, name: str) -> list[str]:
    return re.findall(rf'<input[^>]*name="{name}"[^>]*>', html)


class RoutineCheckWithoutPreselectionTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW 0.26.1", slug="rw-0261-mpg", mpg_enabled=True)
        self.user = User.objects.create_user(username="pruefer", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.lead = User.objects.create_user(username="schichtleitung", password="x-test-pass-123")
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi-0261", name="Defi 0261")
        self.client.force_login(self.user)
        self.url = reverse("mpg_routine_check", args=[self.device.slug])

    def _answers(self, **overrides):
        data = {name: "yes" for name in CHECK_POINTS}
        data.update(overrides)
        return {key: value for key, value in data.items() if value is not None}

    def test_unbound_form_has_no_initial_answer(self):
        # Das Modell setzt die Prüfpunkte auf True; im Formular darf das nicht ankommen.
        form = DeviceRoutineCheckForm()
        for name in CHECK_POINTS:
            self.assertIsNone(form[name].value(), name)
            self.assertTrue(form.fields[name].required, name)
            self.assertEqual([value for value, _label in form.fields[name].choices], ["yes", "no"])

    def test_detail_form_offers_required_yes_no_without_preselection(self):
        html = self.client.get(reverse("mpg_device_detail", args=[self.device.slug])).content.decode()
        for name in CHECK_POINTS:
            inputs = _inputs(html, name)
            # Erfassung (Ja/Nein) – die Freigabe-Checkboxen erscheinen nur bei gesperrten Geräten.
            radios = [tag for tag in inputs if 'type="radio"' in tag]
            self.assertEqual(len(radios), 2, name)
            self.assertTrue(any('value="yes"' in tag for tag in radios), name)
            self.assertTrue(any('value="no"' in tag for tag in radios), name)
            for tag in inputs:
                self.assertNotIn("checked", tag, name)
                self.assertIn("required", tag, name)
        self.assertNotIn('type="checkbox" name="battery_ok"', html)

    def test_missing_answer_is_rejected_and_nothing_is_saved(self):
        response = self.client.post(self.url, self._answers(function_ok=None, notes="vergessen"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DeviceRoutineCheck.objects.filter(device=self.device).exists())
        self.assertFalse(Defect.objects.filter(medical_device=self.device).exists())
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        self.assertIsNone(self.device.last_routine_check)
        text = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("Ja oder Nein", text)

    def test_empty_submission_is_not_a_failed_check(self):
        # Früher: kein Haken = „nicht bestanden“, Gerät gesperrt. Jetzt: nichts gespeichert.
        self.client.post(self.url, {"selftest_protocol": "SELFTEST:PASS"})
        self.assertFalse(DeviceRoutineCheck.objects.filter(device=self.device).exists())
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

    def test_legacy_checkbox_value_is_not_accepted_as_yes(self):
        self.client.post(self.url, {name: "on" for name in CHECK_POINTS})
        self.assertFalse(DeviceRoutineCheck.objects.filter(device=self.device).exists())

    def test_all_yes_passes(self):
        self.client.post(self.url, self._answers())
        check = DeviceRoutineCheck.objects.get(device=self.device)
        self.assertTrue(check.passed)
        self.assertTrue(check.battery_ok and check.visual_ok and check.function_ok)
        self.assertEqual(check.performed_by, self.user)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

    def test_explicit_no_locks_device_until_release(self):
        self.client.post(self.url, self._answers(visual_ok="no", notes="Kabel fehlt"))
        check = DeviceRoutineCheck.objects.get(device=self.device)
        self.assertFalse(check.passed)
        self.assertFalse(check.visual_ok)
        self.assertTrue(check.battery_ok)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        defect = Defect.objects.get(medical_device=self.device)
        self.assertIn("Sichtprüfung/Zubehör", defect.description)

        # Weder Schnellkontrolle noch eine bestandene Kontrolle heben die Sperre auf.
        self.client.post(self.url, {"quick_pass": "1"})
        self.client.post(self.url, self._answers())
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        # Erst die Freigabe nach Abschluss des Mangels.
        defect.status = Defect.Status.DONE
        defect.save()
        self.client.force_login(self.lead)
        self.client.post(
            reverse("mpg_device_release", args=[self.device.slug]),
            {"battery_ok": "on", "visual_ok": "on", "function_ok": "on", "notes": "Kabel ersetzt"},
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

    def test_quick_pass_is_labelled_and_needs_confirmation(self):
        label = "Alles in Ordnung – Funktion geprüft"
        for url in (reverse("mpg_device_detail", args=[self.device.slug]), reverse("mpg_dashboard")):
            html = self.client.get(url).content.decode()
            self.assertIn(label, html, url)
            forms = re.findall(r"<form[^>]*>(?:(?!</form>).)*?name=\"quick_pass\"", html, flags=re.S)
            self.assertTrue(forms, url)
            for form in forms:
                opening = form.split(">", 1)[0]
                self.assertRegex(opening, r'data-confirm="[^"]+"', url)
        self.assertNotIn(">Check<", re.sub(r"\s+", "", self.client.get(reverse("mpg_dashboard")).content.decode()))

    def test_quick_pass_still_records_a_passed_check(self):
        self.client.post(self.url, {"quick_pass": "1"})
        check = DeviceRoutineCheck.objects.get(device=self.device)
        self.assertTrue(check.passed)
        self.assertIn("Schnellkontrolle", check.notes)


class QuickPassOnlyForReadyDevicesTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW 0.26.1 QP", slug="rw-0261-qp", mpg_enabled=True)
        self.user = User.objects.create_user(username="qp-pruefer", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.client.force_login(self.user)

    def test_quick_pass_hidden_and_refused_unless_ready(self):
        for status in (MedicalDevice.Status.LIMITED, MedicalDevice.Status.MAINTENANCE,
                       MedicalDevice.Status.OOB, MedicalDevice.Status.DECOMMISSIONED):
            with self.subTest(status=status):
                device = MedicalDevice.objects.create(
                    station=self.station, slug=f"geraet-{status}", name=f"Gerät {status}", current_status=status,
                )
                detail = self.client.get(reverse("mpg_device_detail", args=[device.slug])).content.decode()
                self.assertNotIn('name="quick_pass"', detail)
                if status == MedicalDevice.Status.DECOMMISSIONED:
                    # Außer Betrieb genommen: keine Kontrolle mehr, nur der Hinweis.
                    self.assertNotIn('data-modal-open="check-modal"', detail)
                    self.assertIn("Außer Betrieb genommen.", detail)
                else:
                    self.assertIn('data-modal-open="check-modal"', detail)
                response = self.client.post(reverse("mpg_routine_check", args=[device.slug]), {"quick_pass": "1"})
                self.assertEqual(response.status_code, 302)
                self.assertFalse(DeviceRoutineCheck.objects.filter(device=device).exists())
                device.refresh_from_db()
                self.assertEqual(device.current_status, status)
        dashboard = self.client.get(reverse("mpg_dashboard")).content.decode()
        self.assertNotIn('name="quick_pass"', dashboard)


class MaintenanceResultWithoutPreselectionTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW 0.26.1 STK", slug="rw-0261-stk", mpg_enabled=True)
        self.lead = User.objects.create_user(username="stk-lead", password="x-test-pass-123")
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi-stk", name="Defi STK")
        self.client.force_login(self.lead)
        self.url = reverse("mpg_maintenance_create", args=[self.device.slug])
        self.data = {"kind": MaintenanceLog.Kind.STK, "performed_at": timezone.localdate().isoformat(),
                     "performed_by": "Medizintechnik GmbH", "next_due_date": "2028-10-01", "findings": ""}

    def test_result_has_no_preselection(self):
        form = MaintenanceLogForm()
        self.assertIsNone(form["passed"].value())
        self.assertTrue(form.fields["passed"].required)
        html = self.client.get(reverse("mpg_device_detail", args=[self.device.slug])).content.decode()
        radios = _inputs(html, "passed")
        self.assertEqual(len(radios), 2)
        self.assertFalse(any(re.search(r"\schecked[\s>=/]", radio) for radio in radios), radios)

    def test_missing_result_is_rejected(self):
        response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "Bitte das Ergebnis wählen")
        self.assertFalse(MaintenanceLog.objects.exists())

    def test_failed_result_does_not_move_the_deadline(self):
        before = self.device.next_stk_date
        self.client.post(self.url, {**self.data, "passed": "no"})
        log = MaintenanceLog.objects.get()
        self.assertFalse(log.passed)
        self.device.refresh_from_db()
        self.assertEqual(self.device.next_stk_date, before)
        self.client.post(self.url, {**self.data, "passed": "yes"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.next_stk_date.isoformat(), "2028-10-01")


class SOPReceiptDataMinimisationTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW Orga 0.26.1", slug="rw-0261-orga", orga_enabled=True)
        self.user = User.objects.create_user(
            username="leserin", first_name="Lea", last_name="Leser", password="x-test-pass-123",
        )
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.colleague = User.objects.create_user(username="altbestand", password="x-test-pass-123")
        Membership.objects.create(user=self.colleague, station=self.station, role=Membership.Role.MEMBER)
        self.sop = SOPDocument.objects.create(
            station=self.station, slug="sop-0261", doc_number="SOP-0261", title="Datensparsam",
            status=SOPDocument.Status.ACTIVE, requires_acknowledgment=True, created_by=self.user,
        )
        self.revision = SOPRevision.objects.create(
            sop=self.sop, version_label="1.0", content_markdown="Text", change_summary="Erstfassung",
            approved_by=self.user,
        )
        # Altbestand aus der Zeit vor 0.26.1 – bleibt unverändert (append-only).
        self.legacy = SOPReceipt.objects.create(
            station=self.station, sop=self.sop, revision=self.revision, user=self.colleague,
            acknowledged_at=timezone.now() - timedelta(days=3),
            ip_address="198.51.100.77", user_agent="LegacyBrowser/9.9 (Altgeraet)",
        )
        self.client.force_login(self.user)

    def test_new_acknowledgement_stores_neither_ip_nor_user_agent(self):
        response = self.client.post(
            reverse("sop_acknowledge", args=[self.sop.slug]),
            REMOTE_ADDR="203.0.113.9",
            HTTP_USER_AGENT="Testbrowser/1.0 (Wachenhandy)",
        )
        self.assertEqual(response.status_code, 302)
        receipt = SOPReceipt.objects.get(sop=self.sop, user=self.user)
        self.assertIsNone(receipt.ip_address)
        self.assertEqual(receipt.user_agent, "")
        self.assertEqual(receipt.revision, self.revision)

    def test_csv_export_has_no_ip_or_user_agent(self):
        self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]), HTTP_USER_AGENT="Testbrowser/1.0")
        response = self.client.get(reverse("sop_export_audit", args=[self.sop.slug]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content), delimiter=";"))
        header = rows[0]
        self.assertNotIn("IP-Adresse", header)
        self.assertEqual(header[-1], "Quittiert am (Ortszeit)")
        self.assertFalse(any("Browser" in column for column in header), header)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(len(row) == len(header) for row in rows))
        self.assertNotIn("198.51.100.77", content)
        self.assertNotIn("LegacyBrowser", content)
        self.assertNotIn("Testbrowser", content)
        self.assertIn("altbestand", content)
        self.assertIn("leserin", content)

    def test_detail_page_never_shows_legacy_ip_or_user_agent(self):
        html = self.client.get(reverse("sop_detail", args=[self.sop.slug])).content.decode()
        self.assertNotIn("198.51.100.77", html)
        self.assertNotIn("LegacyBrowser", html)

    def test_members_see_only_their_own_state(self):
        self.client.force_login(self.colleague)
        html = self.client.get(reverse("sop_detail", args=[self.sop.slug])).content.decode()
        self.assertNotIn("Mitarbeiter-Quittierungsbuch", html)
        self.assertNotIn(reverse("sop_export_audit", args=[self.sop.slug]), html)
        response = self.client.get(reverse("sop_export_audit", args=[self.sop.slug]))
        self.assertRedirects(response, reverse("sop_detail", args=[self.sop.slug]), fetch_redirect_response=False)
        self.client.force_login(self.user)
        self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]))
        html = self.client.get(reverse("sop_detail", args=[self.sop.slug])).content.decode()
        self.assertIn("Mitarbeiter-Quittierungsbuch", html)
        self.assertIn("altbestand", html)

    def test_legacy_rows_stay_untouched(self):
        # Der normale Betrieb ändert Altbestände nie; leeren darf sie nur der
        # einmalige Befehl cleanup_legacy_data (core.test_release_027_legacy_cleanup).
        self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]))
        self.client.get(reverse("sop_export_audit", args=[self.sop.slug]))
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.ip_address, "198.51.100.77")
        self.assertEqual(self.legacy.user_agent, "LegacyBrowser/9.9 (Altgeraet)")

    def test_other_acknowledgements_have_no_ip_or_user_agent_fields(self):
        # News- und Übergabe-Quittungen speichern nur Person und Zeitpunkt.
        for model in (NewsAcknowledgement, HandoverAck):
            names = {field.name for field in model._meta.get_fields()}
            self.assertFalse({"ip_address", "user_agent"} & names, model.__name__)


class ReportsWithoutPerPersonStatsTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW API 0.26.1", slug="rw-0261-api")
        self.user = User.objects.create_user(username="api_nutzer", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.owner = User.objects.create_user(username="zustaendige_person", password="x-test-pass-123")
        Membership.objects.create(user=self.owner, station=self.station, role=Membership.Role.MEMBER)
        raw = "wb_test_release_0261_token_1234567890"
        ApiToken.objects.create(
            user=self.user, label="Tests", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:me", "read:handovers"], expires_at=timezone.now() + timedelta(days=1),
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Token {raw}"}

    def test_defects_by_owner_is_empty_list(self):
        for index in range(3):
            Defect.objects.create(station=self.station, title=f"Offen {index}", created_by=self.user, owner=self.owner)
        Defect.objects.create(station=self.station, title="Ohne Zuständigkeit", created_by=self.user)
        response = self.client.get("/api/v1/reports/", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("defects_by_owner", data)  # bleibt für ältere Clients erhalten
        self.assertEqual(data["defects_by_owner"], [])
        self.assertEqual(data["open_defects"], 4)
        self.assertNotIn("zustaendige_person", response.content.decode())
