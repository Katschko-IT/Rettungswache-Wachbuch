"""Papier-Rückfallebene (Roadmap 0.27, Baustein 8): Druckansichten.

Prüft Rollen, Stationsbindung, Modulschalter, das Wachenterminal, leere
Formulare ohne frühere Ergebnisse, Produktgrenze (keine Art/Stufe der
Desinfektion, keine Erreger, keine Namen) und die Fristenliste der Woche.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core import paper, paper_views
from core.fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
from core.models import Checklist, ChecklistCompletion, ChecklistItem, Membership, Station
from core.mpg_forms import DeviceRoutineCheckForm
from core.mpg_models import DeviceRoutineCheck, MedicalDevice
from core.orga_models import SOPDocument, StationContact
from core.terminal import COOKIE_NAME, hash_secret, set_station_code
from core.terminal_models import StationTerminal, StationTerminalCode
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StorageLocation

PAPER_URLS = (
    "paper_hub", "paper_deadlines", "paper_phonebook", "paper_checklists",
    "paper_vehicle_handover", "paper_disinfection", "paper_device_checks",
)
LANG_COOKIE = settings.LANGUAGE_COOKIE_NAME
# Wörtlich aus core/test_release_0261_fleet.py (0.26.1): Erregernamen und die
# Art der Desinfektion dürfen auf keinem Blatt stehen.
PATHOGENS = ("MRSA", "VRE", "MRGN", "Noro", "Rotavirus", "difficile", "Schlussdesinfektion")
BOUNDARY_WORDS = PATHOGENS + ("Erreger", "Diagnose", "Transportziel", "Einsatzstatus", "Art der Desinfektion")
ROW_RE = re.compile(r'<tr class="paper-row">(.*?)</tr>', re.DOTALL)


def main_html(response) -> str:
    """Nur der Seiteninhalt (``main#inhalt``) ohne Kopf, Leiste und Fuß der App."""
    html = response.content.decode()
    return html.split('<main id="inhalt"', 1)[1].split("</main>", 1)[0]


class PaperBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Papier", slug="wache-papier", checklists_enabled=True)
        self.other = Station.objects.create(name="Wache Fremd", slug="wache-fremd", checklists_enabled=True)
        self.member = self._user("nfs", Membership.Role.MEMBER)
        self.lead = self._user("sl", Membership.Role.SHIFT_LEAD)
        self.cashier = self._user("kasse", Membership.Role.CASHIER)
        self.admin = self._user("chef", Membership.Role.ADMIN)
        self.auditor = self._user("pruefer", Membership.Role.AUDITOR)
        self.zora = self._user("zora", Membership.Role.MEMBER, first_name="Zora")
        self.foreign = User.objects.create_user("fremd", password="x" * 12)
        Membership.objects.create(user=self.foreign, station=self.other, role=Membership.Role.ADMIN)
        self.today = timezone.localdate()
        self.monday = paper.week_start(self.today)

    def _user(self, username, role, first_name=""):
        user = User.objects.create_user(username, password="x" * 12, first_name=first_name)
        Membership.objects.create(user=user, station=self.station, role=role)
        return user

    def vehicle(self, station=None, call_sign="RTW 1", plate="PA-RW 1", **extra):
        station = station or self.station
        return Vehicle.objects.create(
            station=station, slug=call_sign.lower().replace(" ", "-"), call_sign=call_sign, license_plate=plate, **extra,
        )

    def device(self, name="Defi Alpha", station=None, **extra):
        station = station or self.station
        return MedicalDevice.objects.create(station=station, slug=name.lower().replace(" ", "-"), name=name, **extra)

    def stocked_batch(self, lot, station=None, quantity=3, location=None, **extra):
        station = station or self.station
        item, _created = MedicalItem.objects.get_or_create(station=station, slug="nacl", defaults={"name": "NaCl 0,9 %"})
        location = location or StorageLocation.objects.get_or_create(
            station=station, slug="lager", defaults={"name": "Lager"},
        )[0]
        batch = ItemBatch.objects.create(station=station, item=item, batch_number=lot, **extra)
        StockItem.objects.create(station=station, item=item, batch=batch, location=location, quantity=quantity)
        return batch

    def seed_final_disinfection(self, vehicle, agent, performer):
        """Legt eine Schlussdesinfektion an und gibt die Namen zurück, die fehlen müssen.

        Einzige Stelle mit ``DisinfectionProtocol.Kind``: Ersetzt Paket C die Art
        durch Stufen aus dem Hygieneplan, wird nur hier eine Stufe angelegt und
        deren Name zurückgegeben.
        """
        DisinfectionProtocol.objects.create(
            station=vehicle.station, vehicle=vehicle, performed_by=performer, disinfectant=agent,
            kind=DisinfectionProtocol.Kind.FINAL_NORO, notes="Wischprobe-QQ",
        )
        return [str(label) for _value, label in DisinfectionProtocol.Kind.choices]

    def get(self, name, user=None, **params):
        self.client.force_login(user or self.member)
        return self.client.get(reverse(name), params)


class PaperAccessTests(PaperBase):
    def test_anonymous_is_redirected_to_login(self):
        for name in PAPER_URLS:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("login"), response["Location"], name)

    def test_content_roles_can_open_every_view(self):
        for user in (self.member, self.lead, self.cashier, self.admin):
            for name in PAPER_URLS:
                self.assertEqual(self.get(name, user).status_code, 200, f"{user.username} {name}")

    def test_auditor_is_forbidden(self):
        for name in PAPER_URLS:
            self.assertEqual(self.get(name, self.auditor).status_code, 403, name)

    def test_user_without_membership_goes_to_access(self):
        lonely = User.objects.create_user("ohne", password="x" * 12)
        self.client.force_login(lonely)
        self.assertRedirects(self.client.get(reverse("paper_hub")), reverse("access"), fetch_redirect_response=False)

    def test_only_get_is_allowed(self):
        self.client.force_login(self.admin)
        for name in PAPER_URLS:
            self.assertEqual(self.client.post(reverse(name)).status_code, 405, name)

    def test_disabled_modules_return_404_and_vanish_from_the_hub(self):
        Station.objects.filter(pk=self.station.pk).update(
            fleet_enabled=False, mpg_enabled=False, orga_enabled=False, checklists_enabled=False,
        )
        for name in ("paper_phonebook", "paper_checklists", "paper_vehicle_handover",
                     "paper_disinfection", "paper_device_checks"):
            self.assertEqual(self.get(name).status_code, 404, name)
        hub = self.get("paper_hub")
        for name in ("paper_phonebook", "paper_checklists", "paper_vehicle_handover",
                     "paper_disinfection", "paper_device_checks"):
            self.assertNotContains(hub, reverse(name))
        # Lager ist noch an: Fristenliste bleibt erreichbar.
        self.assertContains(hub, reverse("paper_deadlines"))

    def test_service_account_is_rejected_even_without_the_middleware(self):
        set_station_code(self.station, "4827", set_by=self.admin)
        service = StationTerminalCode.objects.get(station=self.station).service_user
        request = RequestFactory().get(reverse("paper_hub"))
        request.user = service
        with self.assertRaises(PermissionDenied):
            paper_views.paper_hub(request)

    def test_settings_and_help_link_to_the_hub(self):
        self.assertContains(self.get("station_settings", self.admin), reverse("paper_hub"))
        self.assertContains(self.get("help_index", self.member), reverse("paper_hub"))
        self.assertNotContains(self.get("help_index", self.auditor), reverse("paper_hub"))

    def test_other_station_admin_sees_only_own_station(self):
        in_week = self.monday + timedelta(days=2)
        vehicle = self.vehicle(call_sign="RTW A-MARKE", plate="A-MARKE-KZ", next_hu_date=in_week)
        DisinfectantMaster.objects.create(station=self.station, name="Mittel A-MARKE")
        self.device("Defi A-MARKE", location="Lager A-MARKE", next_stk_date=in_week)
        StationContact.objects.create(station=self.station, name="Kontakt A-MARKE", phone_primary="0800 111",
                                      is_speed_dial=True)
        checklist = Checklist.objects.create(station=self.station, title="Liste A-MARKE")
        ChecklistItem.objects.create(checklist=checklist, text="Punkt A-MARKE")
        SOPDocument.objects.create(station=self.station, slug="da-a", doc_number="DA-A-MARKE", title="DA A-MARKE",
                                   review_due_date=in_week, created_by=self.admin)
        self.stocked_batch("LOT-A-MARKE", manufacturer_exp_date=in_week)
        VehicleHandover.objects.create(station=self.station, vehicle=vehicle, crew_member=self.zora, mileage=1)
        # Ein Merkmal der eigenen Wache des fremden Admins.
        self.vehicle(station=self.other, call_sign="RTW B-MARKE", plate="B-1", next_hu_date=in_week)
        StationContact.objects.create(station=self.other, name="Kontakt B-MARKE", phone_primary="0800 222")
        b_list = Checklist.objects.create(station=self.other, title="Liste B-MARKE")
        ChecklistItem.objects.create(checklist=b_list, text="Punkt B")
        self.device("Defi B-MARKE", station=self.other, location="Wache B")

        expected_b = {
            "paper_deadlines": "RTW B-MARKE",
            "paper_phonebook": "Kontakt B-MARKE",
            "paper_checklists": "Liste B-MARKE",
            "paper_vehicle_handover": "RTW B-MARKE",
            "paper_disinfection": "RTW B-MARKE",
            "paper_device_checks": "Defi B-MARKE",
        }
        for name in PAPER_URLS:
            response = self.get(name, self.foreign)
            self.assertEqual(response.status_code, 200, name)
            html = response.content.decode()
            self.assertNotIn("A-MARKE", html, name)
            self.assertNotIn("Wache Papier", html, name)
            self.assertIn("Wache Fremd", html, name)
            if name in expected_b:
                self.assertIn(expected_b[name], html, name)


@override_settings(TERMINAL_ENABLED=True, TERMINAL_IDLE_SECONDS=120)
class PaperTerminalTests(PaperBase):
    def test_terminal_everyday_mode_cannot_reach_print_views(self):
        raw = "terminal-secret-token-value"
        StationTerminal.objects.create(station=self.station, label="Halle", token_hash=hash_secret(raw), created_by=self.admin)
        set_station_code(self.station, "4827", set_by=self.admin)
        self.client.cookies[COOKIE_NAME] = raw
        self.client.post(reverse("terminal_home"), data={"code": "4827"})
        for name in PAPER_URLS:
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse("terminal_menu"), fetch_redirect_response=False, msg_prefix=name)
        self.assertNotContains(self.client.get(reverse("help_index")), reverse("paper_hub"))


class PaperFormTests(PaperBase):
    def test_every_sheet_has_station_and_stand(self):
        self.vehicle()
        self.device()
        StationContact.objects.create(station=self.station, name="Leitstelle", phone_primary="0800 1")
        checklist = Checklist.objects.create(station=self.station, title="Wachenrundgang")
        ChecklistItem.objects.create(checklist=checklist, text="Fluchtwege frei")
        for name in PAPER_URLS:
            response = self.get(name)
            self.assertContains(response, "Wache Papier", msg_prefix=name)
            self.assertContains(response, "Stand:", msg_prefix=name)
            self.assertContains(response, "core/paper.css", msg_prefix=name)
            self.assertContains(response, "data-print", msg_prefix=name)
            self.assertContains(response, "paper-view", msg_prefix=name)

    def test_cover_sheet_does_not_ask_for_backdated_entries(self):
        response = self.get("paper_hub")
        self.assertContains(
            response,
            "Läuft das Wachbuch wieder: nur den aktuellen Stand erfassen (je Fahrzeug eine neue "
            "Fahrzeugübernahme, offene Mängel). Die ausgefüllten Blätter sind der Nachweis für die "
            "Ausfallzeit und bleiben bei der Wachleitung, bis Nachträge mit Ereigniszeit möglich sind.",
        )
        self.assertContains(response, "Keine Patienten- oder Einsatzangaben eintragen.")
        self.assertNotContains(response, "Einträge nachtragen")

    def test_handover_sheet_is_empty_and_uses_the_form_checkpoints(self):
        vehicle = self.vehicle()
        self.vehicle(call_sign="RTW alt", plate="PA-RW 9", is_active=False)
        self.vehicle(station=self.other, call_sign="Fremd-RTW", plate="X-1")
        VehicleHandover.objects.create(
            station=self.station, vehicle=vehicle, crew_member=self.zora, mileage=123457,
            notes="Steinschlag-XYZ",
        )
        response = self.get("paper_vehicle_handover")
        html = response.content.decode()
        self.assertContains(response, "RTW 1")
        self.assertContains(response, "PA-RW 1")
        self.assertEqual(html.count('class="paper-sheet"'), 1)
        for label in VehicleHandover.CHECKPOINTS.values():
            escaped = str(label).replace("&", "&amp;")
            self.assertContains(response, escaped)
            # Spaltenkopf „1/2/3“ trägt die Beschriftung für Screenreader.
            self.assertContains(response, f'<span class="visually-hidden">{escaped}</span>')
        self.assertEqual(html.count('class="paper-row"'), paper.HANDOVER_ROWS)
        for leaked in ("123457", "123.457", "Steinschlag-XYZ", "Zora", "RTW alt", "PA-RW 9", "Fremd-RTW"):
            self.assertNotIn(leaked, html)
        self.assertContains(response, "Bemerkung (keine Patienten- oder Einsatzangaben)")

    def test_disinfection_sheet_shows_agents_but_no_kind_or_pathogen(self):
        vehicle = self.vehicle()
        self.vehicle(call_sign="RTW alt", plate="PA-RW 9", is_active=False)
        self.vehicle(station=self.other, call_sign="Fremd-RTW", plate="X-1")
        agent = DisinfectantMaster.objects.create(station=self.station, name="Wischmittel A", default_exposure_minutes=30)
        DisinfectantMaster.objects.create(station=self.other, name="Fremdmittel")
        hidden_names = self.seed_final_disinfection(vehicle, agent, self.zora)
        # Das Blatt liegt offen im Fahrzeug: gleiche Zurückhaltung, egal wer druckt.
        for user in (self.member, self.lead, self.admin):
            response = self.get("paper_disinfection", user)
            html = main_html(response)
            self.assertContains(response, "Wischmittel A (30 Min)")
            self.assertEqual(html.count('class="paper-sheet"'), 1, user.username)
            self.assertEqual(html.count('class="paper-row"'), paper.DISINFECTION_ROWS, user.username)
            for name in hidden_names:
                self.assertNotIn(name, html, user.username)
            for word in BOUNDARY_WORDS + ("Wischprobe-QQ", "Zora", "Transport", "Fremdmittel", "RTW alt", "Fremd-RTW"):
                self.assertNotIn(word, html, f"{user.username}: {word}")
            # D2: Einwirkzeit je Durchgang verrät die Stufe, also keine Spalte dafür.
            thead = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
            self.assertNotIn("Einwirkzeit", thead, user.username)
            self.assertNotIn("Stufe", thead, user.username)
            self.assertNotIn("Bemerkung", thead, user.username)
            headers = [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<th[^>]*>(.*?)</th>", thead, re.DOTALL)]
            self.assertEqual(headers, [
                "Datum", "Beginn (Uhrzeit)", "Desinfektionsmittel", "Frei ab (Uhrzeit)",
                "Durchgeführt (Kürzel)", "Freigegeben (Uhrzeit, Kürzel)",
            ], user.username)
            for row in ROW_RE.findall(html):
                self.assertEqual(row.count("<td"), len(headers), user.username)
            self.assertContains(response, "keine Stufe und keine Einwirkzeit")

    def test_device_sheet_groups_by_location_without_results(self):
        defi = self.device("Defi Alpha", location="RTW 1", inventory_number="INV-7")
        self.device("Absaugung", location="Wache")
        self.device("Altgerät", location="RTW 1", current_status=MedicalDevice.Status.DECOMMISSIONED)
        self.device("Beatmung Delta", location="RTW 1", current_status=MedicalDevice.Status.OOB)
        self.device("Fremdgerät", station=self.other)
        DeviceRoutineCheck.objects.create(
            station=self.station, device=defi, performed_by=self.zora, notes="Kabelbruch-77",
        )
        response = self.get("paper_device_checks")
        html = response.content.decode()
        self.assertContains(response, "Standort: RTW 1")
        self.assertContains(response, "Standort: Wache")
        self.assertEqual(html.count('class="paper-sheet"'), 2)
        self.assertContains(response, "INV-7")
        self.assertContains(response, "Nur prüfen und verwenden, wer in das Gerät eingewiesen ist.", count=2)
        for name in DeviceRoutineCheckForm.CHECK_POINTS:
            label = str(DeviceRoutineCheckForm.base_fields[name].label).replace("&", "&amp;")
            self.assertContains(response, label)
            self.assertContains(response, f'<span class="visually-hidden">{label}</span>')
        rows = ROW_RE.findall(html)
        self.assertEqual(len(rows), 3)
        locked = next(row for row in rows if "Beatmung Delta" in row)
        ready = next(row for row in rows if "Defi Alpha" in row)
        self.assertIn("Beim Ausdruck: Außer Betrieb (Gesperrt)", locked)
        self.assertIn("Gesperrt – erst nach Freigabe verwenden.", locked)
        self.assertNotIn("paper-box", locked)
        self.assertEqual(ready.count("paper-box"), 2 * len(DeviceRoutineCheckForm.CHECK_POINTS))
        self.assertNotIn("Gesperrt – erst nach Freigabe", ready)
        self.assertNotIn("Beim Ausdruck", ready)
        for leaked in ("Altgerät", "Fremdgerät", "Kabelbruch-77", "Zora"):
            self.assertNotIn(leaked, html)

    def test_device_location_is_escaped_on_the_subtitle(self):
        self.device("Defi Alpha", location="<img src=x onerror=alert(1)>")
        html = self.get("paper_device_checks").content.decode()
        self.assertNotIn("<img src=x onerror=alert(1)>", html)
        self.assertIn("Standort: &lt;img src=x onerror=alert(1)&gt;", html)

    def test_checklist_sheet_lists_items_in_order_without_completions(self):
        checklist = Checklist.objects.create(station=self.station, title="Wachenrundgang", description="Jeden Morgen")
        ChecklistItem.objects.create(checklist=checklist, text="Zweiter Punkt", position=2)
        ChecklistItem.objects.create(checklist=checklist, text="Erster Punkt", position=1)
        Checklist.objects.create(station=self.station, title="Alte Liste", is_active=False)
        Checklist.objects.create(station=self.other, title="Fremde Liste")
        ChecklistCompletion.objects.create(station=self.station, checklist=checklist, completed_by=self.zora, note="Notiz-55")
        response = self.get("paper_checklists")
        html = response.content.decode()
        self.assertLess(html.index("Erster Punkt"), html.index("Zweiter Punkt"))
        self.assertEqual(html.count('class="paper-row"'), 2)
        for leaked in ("Alte Liste", "Fremde Liste", "Notiz-55", "Zora"):
            self.assertNotIn(leaked, html)

    def test_phonebook_speed_dial_first_and_text_is_escaped(self):
        StationContact.objects.create(station=self.station, name="Klinik Nord", phone_primary="0800 2",
                                      category=StationContact.Category.HOSPITAL)
        StationContact.objects.create(station=self.station, name="Leitstelle", phone_primary="0800 1",
                                      is_speed_dial=True)
        StationContact.objects.create(station=self.station, name="<script>alert(1)</script>", phone_primary="1")
        StationContact.objects.create(station=self.other, name="Fremde Klinik", phone_primary="9")
        response = self.get("paper_phonebook")
        html = response.content.decode()
        self.assertLess(html.index("Leitstelle"), html.index("Klinik Nord"))
        self.assertLess(html.index("Notfall-Schnellwahl"), html.index("Leitstelle"))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("Fremde Klinik", html)
        self.assertEqual(html.count('class="paper-row"'), paper.PHONEBOOK_BLANK_ROWS)

    def test_no_view_crosses_the_product_boundary(self):
        vehicle = self.vehicle(next_hu_date=self.monday)
        agent = DisinfectantMaster.objects.create(station=self.station, name="Wischmittel A", default_exposure_minutes=30)
        self.seed_final_disinfection(vehicle, agent, self.zora)
        self.device("Defi Alpha", location="RTW 1", current_status=MedicalDevice.Status.OOB, next_dguv_date=self.monday)
        checklist = Checklist.objects.create(station=self.station, title="Wachenrundgang")
        ChecklistItem.objects.create(checklist=checklist, text="Fluchtwege frei")
        StationContact.objects.create(station=self.station, name="Leitstelle", phone_primary="112",
                                      category=StationContact.Category.DISPATCH, is_speed_dial=True)
        StationContact.objects.create(station=self.station, name="Notarzt", phone_primary="0800 3",
                                      category=StationContact.Category.EMERGENCY_SERVICES)
        for name in PAPER_URLS:
            html = main_html(self.get(name))
            for word in BOUNDARY_WORDS:
                self.assertNotIn(word, html, f"{name}: {word}")
            self.assertEqual(set(re.findall(r"Einsatz\w*", html)) - {"Einsatzangaben"}, set(), name)

    def test_english_titles(self):
        self.client.force_login(self.member)
        self.client.cookies[LANG_COOKIE] = "en"
        response = self.client.get(reverse("paper_hub"))
        self.assertContains(response, "Paper fallback")
        self.assertContains(response, "Do not enter patient or mission details.")


class PaperDeadlineTests(PaperBase):
    def test_week_helpers(self):
        self.assertEqual(paper.week_start(date(2026, 11, 4)), date(2026, 11, 2))
        self.assertEqual(paper.parse_week("2026-W46"), date(2026, 11, 9))
        self.assertEqual(paper.iso_week_param(date(2026, 11, 9)), "2026-W46")
        for raw in ("", None, "quatsch", "2026-W00", "2026-W54", "1999-W10", "2026-W4", "2026W46"):
            self.assertIsNone(paper.parse_week(raw), raw)

    def test_selected_week_is_never_in_the_past(self):
        today = date(2026, 11, 4)
        current = date(2026, 11, 2)
        self.assertEqual(paper.selected_week("2026-W46", today), date(2026, 11, 9))
        self.assertEqual(paper.selected_week("2026-W45", today), current)
        for raw in ("2026-W44", "2020-W10", "quatsch", None):
            self.assertEqual(paper.selected_week(raw, today), current, raw)

    def test_sources_and_window(self):
        in_week = self.monday + timedelta(days=3)
        before = self.monday - timedelta(days=10)
        later = self.monday + timedelta(days=9)
        self.vehicle(next_hu_date=in_week, next_uvv_date=later)
        self.vehicle(call_sign="RTW alt", plate="PA-RW 9", is_active=False, next_hu_date=in_week)
        self.vehicle(station=self.other, call_sign="Fremd-RTW", plate="X-1", next_hu_date=in_week)
        self.device("Defi Alpha", next_stk_date=in_week, next_dguv_date=before)
        self.device("Ohne STK-Pflicht", is_anlage_1=False, next_stk_date=in_week)
        self.device("Ausgemustert", next_stk_date=in_week, current_status=MedicalDevice.Status.DECOMMISSIONED)
        self.device("Fremd-Defi", station=self.other, next_stk_date=in_week)
        SOPDocument.objects.create(station=self.station, slug="da-1", doc_number="DA-1", title="Hygieneplan",
                                   review_due_date=in_week, created_by=self.zora)
        SOPDocument.objects.create(station=self.station, slug="da-2", doc_number="DA-2", title="Archiv-DA",
                                   review_due_date=in_week, created_by=self.zora, status=SOPDocument.Status.ARCHIVED)
        SOPDocument.objects.create(station=self.other, slug="da-9", doc_number="DA-9", title="Fremd-DA",
                                   review_due_date=in_week, created_by=self.foreign)
        vehicle_place = StorageLocation.objects.create(station=self.station, slug="rtw-1", name="RTW 1")
        shelf = StorageLocation.objects.create(station=self.station, slug="rtw-1-schrank", name="Schrank 2",
                                               parent=vehicle_place)
        self.stocked_batch("L-1", location=shelf, manufacturer_exp_date=in_week)
        self.stocked_batch("L-LEER", quantity=0, manufacturer_exp_date=in_week)
        self.stocked_batch("L-RUECK", quantity=2, manufacturer_exp_date=in_week, is_recalled=True)
        self.stocked_batch("L-FREMD", station=self.other, manufacturer_exp_date=in_week)

        data = paper.week_deadlines(self.station, self.monday)
        subjects = [(row.subject, str(row.what)) for row in data["this_week"]]
        self.assertIn(("RTW 1", "HU (Hauptuntersuchung)"), subjects)
        self.assertIn(("Defi Alpha", "STK (sicherheitstechnische Kontrolle)"), subjects)
        self.assertIn(("Hygieneplan", "Überprüfung"), subjects)
        self.assertIn(("NaCl 0,9 %", "Verfall"), subjects)
        self.assertEqual([(row.subject, str(row.what)) for row in data["earlier"]],
                         [("Defi Alpha", "DGUV V3 (elektrische Prüfung)")])
        flat = " ".join(f"{row.subject} {row.detail}" for row in data["this_week"] + data["earlier"])
        for absent in ("RTW alt", "Fremd-RTW", "Ohne STK-Pflicht", "Ausgemustert", "Fremd-Defi", "Archiv-DA",
                       "Fremd-DA", "L-LEER", "L-RUECK", "L-FREMD"):
            self.assertNotIn(absent, flat)
        self.assertNotIn("UVV", " ".join(str(row.what) for row in data["this_week"]))
        self.assertIn("Charge L-1 · RTW 1 → Schrank 2", flat)

        html = self.get("paper_deadlines").content.decode()
        self.assertNotIn("Zora", html)
        self.assertIn("Hygieneplan", html)
        self.assertIn("RTW 1 → Schrank 2", html)

    def test_next_week_and_invalid_parameter(self):
        self.vehicle(next_hu_date=self.monday + timedelta(days=8))
        self.assertNotContains(self.get("paper_deadlines"), "HU (Hauptuntersuchung)")
        nxt = paper.iso_week_param(self.monday + timedelta(days=7))
        self.assertContains(self.get("paper_deadlines", woche=nxt), "HU (Hauptuntersuchung)")
        current_heading = f"KW {self.monday.isocalendar()[1]} ·"
        last_week = paper.iso_week_param(self.monday - timedelta(days=7))
        for raw in ("quatsch", "2026-W99", "<b>", "2020-W10", last_week):
            response = self.get("paper_deadlines", woche=raw)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "HU (Hauptuntersuchung)")
            self.assertContains(response, current_heading, msg_prefix=raw)
            self.assertNotContains(response, "<b>", msg_prefix=raw)

    def test_disabled_module_is_not_listed(self):
        self.vehicle(next_hu_date=self.monday)
        Station.objects.filter(pk=self.station.pk).update(fleet_enabled=False)
        self.assertNotContains(self.get("paper_deadlines"), "RTW 1")

    def test_query_count_does_not_grow(self):
        def count():
            self.client.force_login(self.member)
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(reverse("paper_deadlines")).status_code, 200)
            return len(ctx.captured_queries)

        due = self.monday + timedelta(days=1)
        self.vehicle(next_hu_date=due)
        self.device("Gerät 0", next_stk_date=due)
        self.stocked_batch("L-0", manufacturer_exp_date=due)
        first = count()
        for index in range(1, 6):
            self.vehicle(call_sign=f"RTW {index + 1}", plate=f"PA-{index}", next_hu_date=due)
            self.device(f"Gerät {index}", next_stk_date=due)
            self.stocked_batch(f"L-{index}", manufacturer_exp_date=due)
        self.assertEqual(count(), first)


class PaperStaticTests(TestCase):
    def test_print_stylesheet_follows_design_rules(self):
        raw = (Path(settings.BASE_DIR) / "core/static/core/paper.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
        self.assertIn("@page", css)
        self.assertIn("A4", css)
        self.assertIn("@media print", css)
        self.assertIn(":not(#inhalt)", css)
        self.assertNotIn("!important", css)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b", css))

    def test_paper_templates_do_not_use_safe(self):
        paths = list((Path(settings.BASE_DIR) / "templates/core").glob("*paper*.html"))
        self.assertGreaterEqual(len(paths), 13)
        for path in paths:
            self.assertNotIn("|safe", path.read_text(encoding="utf-8"), path.name)
