"""0.28 Paket 3: Mangel in drei Tipps, Wand-Display, Barrierefreiheit, API.

Prüft die Nacharbeit aus dem Audit zu 0.28 (Mangel, Display, axe-core-CI):

- Mangel in drei Tipps: Titel optional, Bezug aus Fahrzeugen, Medizingeräten
  und „Geräte & Fahrzeuge“, Verknüpfung (Defect.vehicle/medical_device),
  Gerätesperre, Freitext ohne JavaScript, Fehler ohne Datenverlust.
- Hinweis „bereits gemeldet“: am Bezugsfeld, aria-live, exakte Zuordnung,
  nie Mängel einer anderen Wache (Web, json_script-Daten, API).
- Bild-Metadaten: jeder Bild-Anhang ohne EXIF/GPS.
- API: ``?asset=`` ohne NameError, ``me`` mit csrf_exempt.
- Wand-Display: festes 16:9 nur im Kiosk, Zeilen begrenzt mit „+N weitere“.
  Die Geometrie (1920x1080, 1280x720) prüft der CI-Job „a11y“ im Browser
  (tests/a11y/run-axe.js), hier nur die serverseitigen Voraussetzungen.
- Barrierefreiheit: Kontrast der Chips, Fokusring-Token, Kaffeekasse.
"""
from __future__ import annotations

import io
import json
import re
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from PIL import Image
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.api.views import hash_api_token
from core.display_models import DisplayToken
from core.display_views import COOKIE_NAME as DISPLAY_COOKIE, _hash as display_hash
from core.fleet_models import Vehicle
from core.models import (
    ApiToken,
    AuditEvent,
    HandoverAttachment,
    HandoverEntry,
    Membership,
    NewsAttachment,
    NewsPost,
    PinboardAttachment,
    Station,
)
from core.mpg_models import MedicalDevice
from core.test_terminal import TerminalTestCase
from core.wachalltag_models import Defect, DefectAttachment, StationAsset

ROOT = Path(settings.BASE_DIR)
GPS_TAG = 0x8825
MAKE_TAG = 0x010F


def jpeg_with_exif(size=(32, 24)) -> bytes:
    image = Image.new("RGB", size, (120, 40, 40))
    exif = Image.Exif()
    exif[MAKE_TAG] = "Kamerahersteller"
    exif[GPS_TAG] = {1: "N", 2: (48.0, 8.0, 0.0)}
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def png_bytes(size=(8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, (0, 120, 0, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


def has_exif(raw: bytes) -> bool:
    with Image.open(io.BytesIO(bytes(raw))) as image:
        return bool(image.getexif()) or "exif" in image.info


class LabelCollector(HTMLParser):
    """Sammelt Labels, ids und verschachtelte Felder einer Seite."""

    def __init__(self):
        super().__init__()
        self.ids = set()
        self.labels = []  # (for, hat_feld)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "label":
            self.stack.append({"for": attrs.get("for"), "control": False})
        elif tag in {"input", "select", "textarea"} and self.stack:
            self.stack[-1]["control"] = True

    def handle_endtag(self, tag):
        if tag == "label" and self.stack:
            entry = self.stack.pop()
            self.labels.append((entry["for"], entry["control"]))


class DefectFormBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Drei", slug="wache-drei")
        self.user = User.objects.create_user("melder", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.vehicle = Vehicle.objects.create(
            station=self.station, slug="rtw-831", call_sign="RTW 1/83-1", license_plate="MU-RD 831",
        )
        self.retired = Vehicle.objects.create(
            station=self.station, slug="rtw-alt", call_sign="RTW Alt", license_plate="MU-RD 999", is_active=False,
        )
        self.device = MedicalDevice.objects.create(
            station=self.station, slug="defi-1", name="Defibrillator", inventory_number="INV-7",
        )
        self.decommissioned = MedicalDevice.objects.create(
            station=self.station, slug="defi-alt", name="Alter Defi",
            current_status=MedicalDevice.Status.DECOMMISSIONED,
        )
        self.key = StationAsset.objects.create(
            station=self.station, asset_id="schluessel-halle", label="Schlüssel Halle", kind=StationAsset.Kind.KEY,
        )
        # Spiegel des Fuhrparks in „Geräte & Fahrzeuge“: erscheint nicht doppelt.
        self.mirror = StationAsset.objects.create(
            station=self.station, asset_id="rtw-831", label="RTW 1/83-1", kind=StationAsset.Kind.VEHICLE,
        )
        self.other = Station.objects.create(name="Andere Wache", slug="andere-wache")
        self.other_user = User.objects.create_user("fremd", password="x-test-pass-123")
        Membership.objects.create(user=self.other_user, station=self.other, role=Membership.Role.MEMBER)
        self.other_vehicle = Vehicle.objects.create(
            station=self.other, slug="rtw-fremd", call_sign="RTW Fremd", license_plate="XX-1",
        )
        self.client.force_login(self.user)

    def defect(self, station=None, **fields):
        fields.setdefault("title", "Mangel")
        return Defect.objects.create(
            station=station or self.station,
            created_by=self.user if station in (None, self.station) else self.other_user,
            **fields,
        )

    def post(self, data, files=None, follow=False):
        payload = {"priority": "normal", "category": "material", "owner_self": "1", **data}
        if files:
            payload["attachments"] = files
        return self.client.post(reverse("defect_create_web"), payload, follow=follow)


class DefectThreeTapTests(DefectFormBase):
    def test_three_taps_with_preselected_reference(self):
        """Ehrliche Zählung der Tipps für „Mangel in drei Tipps“.

        Mit vorgewähltem Bezug (``?asset=`` von Fahrzeugseite, Geräteseite
        oder QR-Code) sind es drei Tipps: 1. Formular öffnen (Link „Mangel
        melden“ bzw. „Mangel mit Foto melden“), 2. „Foto aufnehmen“ (Auslösen
        und Bestätigen in der Kamera-App des Telefons kommen dazu), 3. „Mangel
        speichern“. Titel, Kategorie und Priorität sind vorbelegt bzw. werden
        gebildet. Ohne vorgewählten Bezug kommt ein Tipp für die Auswahl des
        Bezugs dazu (vier Tipps).
        """
        form = self.client.get(reverse("defect_create_web"), {"asset": f"vehicle:{self.vehicle.pk}"})
        self.assertEqual(form.context["selected_key"], f"vehicle:{self.vehicle.pk}")
        self.assertContains(form, 'id="cat_vehicle" name="category" value="vehicle" checked')
        self.assertContains(form, 'id="prio_normal" name="priority" value="normal" checked')
        # Der Browser sendet genau die vorbelegten Werte plus das Foto.
        photo = SimpleUploadedFile("IMG_0001.JPG", jpeg_with_exif(), content_type="image/jpeg")
        response = self.client.post(reverse("defect_create_web"), {
            "asset_ref": f"vehicle:{self.vehicle.pk}", "asset_ref_custom": "",
            "category": "vehicle", "priority": "normal", "owner_self": "1",
            "title": "", "description": "", "due_at": "", "attachments": photo,
        })
        defect = Defect.objects.get(station=self.station)
        self.assertRedirects(response, reverse("defect_detail_web", args=[defect.pk]), fetch_redirect_response=False)
        self.assertEqual(defect.title, "Fahrzeug: RTW 1/83-1 (MU-RD 831)")
        self.assertEqual(defect.asset_ref, "RTW 1/83-1 (MU-RD 831)")
        self.assertEqual(defect.vehicle, self.vehicle)
        self.assertIsNone(defect.medical_device)
        self.assertEqual(defect.attachments.count(), 1)
        self.assertEqual(defect.owner, self.user)

    def test_title_is_optional_and_built_from_category_without_reference(self):
        self.post({"title": "", "description": "Tür schließt nicht"})
        defect = Defect.objects.get(station=self.station)
        self.assertEqual(defect.title, "Material: ohne Bezug")
        self.assertEqual(defect.asset_ref, "")

    def test_completely_empty_report_is_rejected_without_redirect(self):
        response = self.post({"title": "", "description": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["errors"])
        self.assertFalse(Defect.objects.exists())

    def test_sensible_defaults_without_reference(self):
        form = self.client.get(reverse("defect_create_web"))
        self.assertContains(form, 'id="cat_material" name="category" value="material" checked')
        self.assertContains(form, 'id="prio_normal" name="priority" value="normal" checked')
        self.assertContains(form, 'name="owner_self" value="1" checked')

    def test_asset_parameter_accepts_keys_slugs_and_names(self):
        cases = {
            f"vehicle:{self.vehicle.pk}": f"vehicle:{self.vehicle.pk}",
            "rtw-831": f"vehicle:{self.vehicle.pk}",  # Fahrzeug-Kurzname
            str(self.mirror.pk): f"vehicle:{self.vehicle.pk}",  # gespiegelter Eintrag
            "defi-1": f"device:{self.device.pk}",
            f"device:{self.device.pk}": f"device:{self.device.pk}",
            "schluessel-halle": f"asset:{self.key.pk}",
            "Schlüssel Halle": f"asset:{self.key.pk}",
        }
        for value, key in cases.items():
            with self.subTest(value=value):
                response = self.client.get(reverse("defect_create_web"), {"asset": value})
                self.assertEqual(response.context["selected_key"], key)
        device_form = self.client.get(reverse("defect_create_web"), {"asset": "defi-1"})
        self.assertContains(device_form, 'id="cat_device" name="category" value="device" checked')

    def test_unknown_asset_parameter_becomes_free_text(self):
        response = self.client.get(reverse("defect_create_web"), {"asset": "Küche OG"})
        self.assertEqual(response.context["selected_key"], "__custom__")
        self.assertContains(response, 'value="Küche OG"')

    def test_dashboard_offers_one_tap_entry(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, f'href="{reverse("defect_create_web")}"')
        self.assertContains(response, "Mangel melden")

    def test_vehicle_and_device_pages_link_the_prefilled_form(self):
        url = reverse("defect_create_web")
        vehicle_page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.assertContains(vehicle_page, f'href="{url}?asset=vehicle:{self.vehicle.pk}"')
        device_page = self.client.get(reverse("mpg_device_detail", args=[self.device.slug]))
        self.assertContains(device_page, f'href="{url}?asset=device:{self.device.pk}"')


class DefectReferenceListTests(DefectFormBase):
    def test_list_has_fleet_devices_and_assets_grouped(self):
        response = self.client.get(reverse("defect_create_web"))
        groups = {group: [option.key for option in items] for group, items in response.context["reference_groups"]}
        self.assertEqual(list(groups), ["Fahrzeuge", "Medizingeräte", "Schlüssel"])
        self.assertEqual(groups["Fahrzeuge"], [f"vehicle:{self.vehicle.pk}"])  # Spiegel nicht doppelt, Altfahrzeug fehlt
        self.assertEqual(groups["Medizingeräte"], [f"device:{self.device.pk}"])  # außer Betrieb genommen fehlt
        self.assertEqual(groups["Schlüssel"], [f"asset:{self.key.pk}"])
        self.assertContains(response, '<optgroup label="Medizingeräte">')
        self.assertNotContains(response, "RTW Alt")
        self.assertNotContains(response, "Alter Defi")

    def test_other_station_objects_are_never_listed(self):
        response = self.client.get(reverse("defect_create_web"))
        self.assertNotContains(response, "RTW Fremd")
        self.assertNotContains(response, f"vehicle:{self.other_vehicle.pk}")

    def test_modules_switched_off_hide_their_objects(self):
        Station.objects.filter(pk=self.station.pk).update(fleet_enabled=False, mpg_enabled=False)
        response = self.client.get(reverse("defect_create_web"))
        keys = [option.key for _group, items in response.context["reference_groups"] for option in items]
        self.assertNotIn(f"vehicle:{self.vehicle.pk}", keys)
        self.assertNotIn(f"device:{self.device.pk}", keys)
        self.assertIn(f"asset:{self.mirror.pk}", keys)  # ohne Fuhrpark bleibt der Eintrag wählbar

    def test_vehicle_defect_shows_on_vehicle_page(self):
        self.post({"asset_ref": f"vehicle:{self.vehicle.pk}", "category": "vehicle", "title": "Spiegel lose"})
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.assertContains(page, "Spiegel lose")

    def test_device_defect_links_and_locks_device(self):
        response = self.post(
            {"asset_ref": f"device:{self.device.pk}", "category": "device", "title": "Akku lädt nicht"}, follow=True,
        )
        defect = Defect.objects.get(station=self.station)
        self.assertEqual(defect.medical_device, self.device)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        self.assertIn(f"#{defect.pk}", self.device.status_note)
        self.assertTrue(AuditEvent.objects.filter(action="mpg.device_locked", object_id=str(self.device.pk)).exists())
        self.assertContains(response, "ist gesperrt")
        from core.device_status import release_blockers

        self.assertEqual(release_blockers(self.device), [defect])

    def test_foreign_key_of_another_station_is_rejected(self):
        response = self.post({"asset_ref": f"vehicle:{self.other_vehicle.pk}", "title": "Fremd"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("asset_ref", response.context["errors"])
        self.assertFalse(Defect.objects.exists())

    def test_free_text_without_javascript(self):
        # Ohne JavaScript bleibt die Auswahl leer, das Freitextfeld ist sichtbar.
        page = self.client.get(reverse("defect_create_web"))
        self.assertRegex(page.content.decode(), r'<div class="custom-reference" data-custom-reference>')
        self.post({"asset_ref": "", "asset_ref_custom": "  Küche   OG ", "title": "Kühlschrank"})
        defect = Defect.objects.get(station=self.station)
        self.assertEqual(defect.asset_ref, "Küche   OG")
        self.assertIsNone(defect.vehicle)

    def test_free_text_and_values_survive_an_error(self):
        too_big = SimpleUploadedFile("gross.jpg", b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 10), content_type="image/jpeg")
        response = self.post({
            "asset_ref": "__custom__", "asset_ref_custom": "Kühlschrank Küche", "title": "Tür klemmt",
            "description": "Seit gestern", "category": "facility", "priority": "important",
        }, files=too_big)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Defect.objects.exists())
        self.assertIn("attachments", response.context["errors"])
        html = response.content.decode()
        self.assertIn('value="Kühlschrank Küche"', html)
        self.assertIn('<option value="__custom__" selected>', html)
        self.assertIn('value="Tür klemmt"', html)
        self.assertIn("Seit gestern</textarea>", html)
        self.assertIn('id="cat_facility" name="category" value="facility" checked', html)
        self.assertIn('id="prio_important" name="priority" value="important" checked', html)
        self.assertIn("5 MiB", response.context["errors"]["attachments"])


class DefectFormMarkupTests(DefectFormBase):
    def test_every_label_belongs_to_a_control_and_no_jargon(self):
        html = self.client.get(reverse("defect_create_web")).content.decode()
        self.assertNotIn("(Tipp 1)", html)
        self.assertNotRegex(html, r"Tipp \d")
        parser = LabelCollector()
        parser.feed(html)
        form_labels = [label for label in parser.labels if label[0] or label[1]]
        self.assertEqual(len(form_labels), len(parser.labels))
        for target, _has_control in parser.labels:
            if target:
                self.assertIn(target, parser.ids)
        self.assertIn('<legend class="field-label">Foto</legend>', html)

    def test_duplicate_hint_sits_at_the_reference_field_and_is_polite(self):
        html = self.client.get(reverse("defect_create_web")).content.decode()
        select = html.index('id="id_asset_ref"')
        hint = html.index('id="defect-duplicates"')
        description = html.index('id="id_description"')
        self.assertLess(select, hint)
        self.assertLess(hint, description)
        self.assertRegex(html, r'id="defect-duplicates" aria-live="polite"')
        self.assertNotIn('role="alert" data-already-reported-banner', html)

    def test_photo_inputs_are_hidden_inside_positioned_buttons(self):
        css = (ROOT / "core/static/core/app.css").read_text(encoding="utf-8")
        hidden = re.search(r"\.visually-hidden \{(.*?)\}", css, re.S).group(1)
        for rule in ("width: 1px !important", "height: 1px !important", "min-height: 0 !important",
                     "padding: 0 !important", "clip-path: inset(50%) !important"):
            self.assertIn(rule, hidden)
        buttons = re.search(r"\.photo-capture-btn,\n\.photo-upload-btn \{(.*?)\}", css, re.S).group(1)
        self.assertIn("position: relative", buttons)
        # Sichtbarer Fokus auf „Foto aufnehmen“ und „Datei wählen“.
        self.assertIn(".photo-capture-btn:has(input:focus-visible)", css)
        self.assertIn(".photo-upload-btn:has(input:focus-visible)", css)


class DuplicateHintTests(DefectFormBase):
    def setUp(self):
        super().setUp()
        self.rtw1 = StationAsset.objects.create(station=self.station, asset_id="rtw-1", label="RTW 1", kind="vehicle")
        self.rtw10 = StationAsset.objects.create(station=self.station, asset_id="rtw-10", label="RTW 10", kind="vehicle")

    def test_rtw_1_is_not_rtw_10_nor_generic_rtw(self):
        own = self.defect(title="Blaulicht links", asset_ref="RTW 1")
        self.defect(title="Tür klemmt", asset_ref="RTW 10")
        self.defect(title="Allgemein", asset_ref="RTW")
        response = self.client.get(reverse("defect_create_web"), {"asset": "rtw-1"})
        self.assertEqual([d.pk for d in response.context["already_reported_defects"]], [own.pk])
        data = response.context["defects_by_asset_data"]
        self.assertEqual(data["by_key"][f"asset:{self.rtw1.pk}"], [own.pk])
        self.assertEqual(data["by_text"]["rtw 1"], [own.pk])

    def test_free_text_matches_normalized_exact_text_only(self):
        own = self.defect(title="Licht", asset_ref="Küche  OG")
        self.defect(title="Anderes", asset_ref="Küche OG Flur")
        response = self.client.get(reverse("defect_create_web"), {"asset": "küche og"})
        self.assertEqual([d.pk for d in response.context["already_reported_defects"]], [own.pk])

    def test_linked_defect_matches_vehicle_even_with_other_text(self):
        linked = self.defect(title="Reifen", asset_ref="Irgendein Text", vehicle=self.vehicle)
        legacy = self.defect(title="Altbezug", asset_ref="RTW 1/83-1")  # Name des Spiegeleintrags
        done = self.defect(title="Erledigt", asset_ref="RTW 1/83-1 (MU-RD 831)", status=Defect.Status.DONE)
        response = self.client.get(reverse("defect_create_web"), {"asset": f"vehicle:{self.vehicle.pk}"})
        found = {d.pk for d in response.context["already_reported_defects"]}
        self.assertEqual(found, {linked.pk, legacy.pk})
        self.assertNotIn(done.pk, found)

    def test_other_station_defects_never_appear(self):
        Defect.objects.create(station=self.other, title="Fremder Mangel", asset_ref="RTW 1", created_by=self.other_user)
        foreign = Defect.objects.create(
            station=self.other, title="Fremd verknüpft", asset_ref="RTW Fremd", vehicle=self.other_vehicle,
            created_by=self.other_user,
        )
        response = self.client.get(reverse("defect_create_web"), {"asset": "rtw-1"})
        self.assertEqual(response.context["already_reported_defects"], [])
        html = response.content.decode()
        self.assertNotIn("Fremder Mangel", html)
        self.assertNotIn("Fremd verknüpft", html)
        raw = re.search(r'<script id="defects-data" type="application/json">(.*?)</script>', html, re.S).group(1)
        data = json.loads(raw)
        self.assertNotIn(str(foreign.pk), data["defects"])
        self.assertEqual(data["defects"], {})
        # Auch ein erratener Schlüssel der anderen Wache zeigt nichts.
        response = self.client.get(reverse("defect_create_web"), {"asset": f"vehicle:{self.other_vehicle.pk}"})
        self.assertEqual(response.context["already_reported_defects"], [])

    def test_hint_data_is_json_script_not_markup(self):
        self.defect(title="<b>Fett</b>", asset_ref="RTW 1")
        html = self.client.get(reverse("defect_create_web")).content.decode()
        self.assertIn('<script id="defects-data" type="application/json">', html)
        self.assertNotIn("<b>Fett</b>", html)


class TerminalDefectFormTests(TerminalTestCase):
    """Das Wachenterminal meldet Mängel, aber keine Gerätemängel (keine Medizingeräte)."""

    def setUp(self):
        super().setUp()
        Station.objects.filter(pk=self.station.pk).update(mpg_enabled=True, fleet_enabled=True)
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi-t", name="Defi Terminal")
        self.vehicle = Vehicle.objects.create(station=self.station, slug="rtw-t", call_sign="RTW T", license_plate="T-1")
        self.use_terminal()
        self.unlock()

    def test_devices_are_not_offered_and_cannot_be_posted(self):
        form = self.client.get(reverse("defect_create_web"))
        self.assertEqual(form.status_code, 200)
        self.assertNotContains(form, "Defi Terminal")
        self.assertContains(form, "RTW T (T-1)")
        response = self.client.post(reverse("defect_create_web"), {
            "asset_ref": f"device:{self.device.pk}", "category": "device", "priority": "normal", "title": "Defekt",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Defect.objects.exists())
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        # Auch über ?asset= wird das Gerät nicht vorgewählt.
        prefilled = self.client.get(reverse("defect_create_web"), {"asset": "defi-t"})
        self.assertIsNone(prefilled.context["selected_option"])


class DefectUploadPrivacyTests(DefectFormBase):
    def test_defect_photo_is_stored_without_exif(self):
        self.post({"title": "Mit Foto"}, files=SimpleUploadedFile("gps.jpg", jpeg_with_exif(), content_type="image/jpeg"))
        attachment = DefectAttachment.objects.get()
        self.assertFalse(has_exif(attachment.data))
        self.assertEqual(attachment.content_type, "image/jpeg")

    def test_image_that_cannot_be_rewritten_is_rejected_not_stored(self):
        upload = SimpleUploadedFile("foto.jpg", jpeg_with_exif(), content_type="image/jpeg")
        with mock.patch("core.attachments.normalize_image_to_jpeg", side_effect=ValueError("kaputt")):
            response = self.post({"title": "Kaputtes Foto", "description": "bleibt"}, files=upload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Defect.objects.exists())
        self.assertFalse(DefectAttachment.objects.exists())
        self.assertIn("ohne Metadaten", response.context["errors"]["attachments"])
        self.assertContains(response, "bleibt</textarea>")


class UploadMetadataTests(TestCase):
    """EXIF/GPS verschwinden bei jedem Bild-Anhang (auch Fotos von Papierbögen)."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Foto", slug="wache-foto", pinboard_enabled=True)
        self.user = User.objects.create_user("fotograf", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def upload(self, name="papier.jpg", raw=None, content_type="image/jpeg"):
        return SimpleUploadedFile(name, raw or jpeg_with_exif(), content_type=content_type)

    def test_handover_create_strips_exif(self):
        response = self.client.post(reverse("handover_create"), {
            "category": "station", "priority": "normal", "title": "Papierbogen nachgetragen", "details": "Foto",
            "attachments": self.upload(),
        })
        self.assertEqual(response.status_code, 302)
        attachment = HandoverAttachment.objects.get()
        self.assertFalse(has_exif(attachment.data))
        self.assertEqual(attachment.size, len(attachment.data))

    def test_handover_detail_upload_strips_exif_and_converts_png(self):
        handover = HandoverEntry.objects.create(
            station=self.station, category="station", title="Übergabe", details="x", author=self.user,
        )
        self.client.post(reverse("handover_detail", args=[handover.pk]), {
            "action": "upload", "attachment": self.upload("bogen.png", png_bytes(), "image/png"),
        })
        attachment = HandoverAttachment.objects.get()
        self.assertEqual(attachment.content_type, "image/jpeg")
        self.assertEqual(attachment.filename, "bogen.jpg")
        self.assertFalse(has_exif(attachment.data))

    def test_pinboard_create_strips_exif(self):
        self.client.post(reverse("pinboard_create"), {
            "title": "Aushang", "body": "Text", "category": "info", "attachments": self.upload(),
        })
        self.assertFalse(has_exif(PinboardAttachment.objects.get().data))

    def test_news_create_and_detail_strip_exif(self):
        self.client.post(reverse("news_create"), {"title": "Neu", "body": "Text", "attachment": self.upload()})
        post = NewsPost.objects.get()
        self.client.post(reverse("news_detail", args=[post.pk]), {"action": "upload", "attachment": self.upload()})
        self.assertEqual(NewsAttachment.objects.count(), 2)
        for attachment in NewsAttachment.objects.all():
            self.assertFalse(has_exif(attachment.data))

    def test_news_create_keeps_text_when_attachment_is_rejected(self):
        response = self.client.post(reverse("news_create"), {
            "title": "Bleibt", "body": "Auch der Text", "attachment": self.upload("x.jpg", b"kein bild"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(NewsPost.objects.exists())
        self.assertContains(response, 'value="Bleibt"')
        self.assertContains(response, "Auch der Text</textarea>")

    def test_signal_strips_metadata_on_other_code_paths(self):
        handover = HandoverEntry.objects.create(
            station=self.station, category="station", title="Import", details="x", author=self.user,
        )
        raw = jpeg_with_exif()
        attachment = HandoverAttachment.objects.create(
            handover=handover, station=self.station, filename="import.jpg", content_type="image/jpeg",
            data=raw, size=len(raw), uploaded_by=self.user,
        )
        self.assertFalse(has_exif(attachment.data))
        self.assertEqual(attachment.size, len(attachment.data))


class DefectApiTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache API", slug="wache-api")
        self.user = User.objects.create_user("api-nutzer", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        raw = "wb_test_p3_defects_token_1234567890"
        ApiToken.objects.create(
            user=self.user, label="Tests", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:me", "read:handovers", "write:handovers"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Token {raw}"}
        self.other = Station.objects.create(name="Fremde Wache", slug="fremde-wache")
        self.other_user = User.objects.create_user("fremd-api", password="x-test-pass-123")

    def titles(self, **params):
        response = self.client.get("/api/v1/defects/", params, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return sorted(item["title"] for item in response.json()["results"])

    def test_asset_filter_is_exact_and_does_not_crash(self):
        for title, ref in (("eins", "RTW 1"), ("zehn", "RTW 10"), ("allgemein", "RTW"), ("eins klein", "rtw  1")):
            Defect.objects.create(station=self.station, title=title, asset_ref=ref, created_by=self.user)
        self.assertEqual(self.titles(asset="RTW 1", active="1"), ["eins", "eins klein"])
        self.assertEqual(self.titles(asset_ref="RTW 10"), ["zehn"])

    def test_asset_filter_by_vehicle_key_includes_linked_defects(self):
        vehicle = Vehicle.objects.create(station=self.station, slug="rtw-api", call_sign="RTW API", license_plate="A-1")
        Defect.objects.create(station=self.station, title="verknüpft", asset_ref="egal", vehicle=vehicle, created_by=self.user)
        Defect.objects.create(station=self.station, title="Text", asset_ref="RTW API (A-1)", created_by=self.user)
        self.assertEqual(self.titles(asset=f"vehicle:{vehicle.pk}"), ["Text", "verknüpft"])
        self.assertEqual(self.titles(asset="rtw-api"), ["Text", "verknüpft"])

    def test_asset_filter_never_returns_other_stations(self):
        Defect.objects.create(station=self.other, title="fremd", asset_ref="RTW 1", created_by=self.other_user)
        foreign_vehicle = Vehicle.objects.create(station=self.other, slug="rtw-x", call_sign="RTW X", license_plate="X-1")
        Defect.objects.create(
            station=self.other, title="fremd verknüpft", asset_ref="RTW X (X-1)", vehicle=foreign_vehicle,
            created_by=self.other_user,
        )
        self.assertEqual(self.titles(asset="RTW 1"), [])
        self.assertEqual(self.titles(asset=f"vehicle:{foreign_vehicle.pk}"), [])
        self.assertEqual(self.titles(asset="rtw-x"), [])

    def test_me_view_is_csrf_exempt_and_helper_is_plain(self):
        from core.api import wachalltag

        self.assertTrue(getattr(wachalltag.me, "csrf_exempt", False))
        self.assertFalse(hasattr(wachalltag._station_modules, "csrf_exempt"))
        self.assertFalse(hasattr(wachalltag._station_modules, "__wrapped__"))
        self.assertIsInstance(wachalltag._station_modules(self.station), dict)
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn("modules", response.json()["membership"]["station"])


class WallDisplayKioskTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Wand", slug="wache-wand", display_enabled=True)
        self.user = User.objects.create_user("wand", password="x-test-pass-123")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.raw = "display-token-for-p3-tests-1234567890"
        DisplayToken.objects.create(station=self.station, label="Flur", token_hash=display_hash(self.raw), created_by=self.user)

    def test_kiosk_via_display_link_gets_the_fixed_frame(self):
        self.client.cookies[DISPLAY_COOKIE] = self.raw
        html = self.client.get(reverse("display_home")).content.decode()
        self.assertIn('class="display-root display-kiosk"', html)
        self.assertIn('class="display-grid display-grid-16x9"', html)

    def test_session_view_stays_fluid(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("display_home")).content.decode()
        self.assertNotIn("display-grid-16x9", html)
        self.assertNotIn("display-kiosk", html)
        self.assertIn("Zurück zur Übersicht", html)

    def test_every_list_has_a_row_cap_and_a_more_label(self):
        self.client.cookies[DISPLAY_COOKIE] = self.raw
        html = self.client.get(reverse("display_home")).content.decode()
        self.assertIn('data-more-label="weitere"', html)
        for hook in ("data-display-events", "data-display-fleet", "data-display-mpg", "data-display-warehouse",
                     "data-display-birthdays", "data-display-waste", "data-display-tasks-urgent"):
            self.assertRegex(html, rf'{hook}[^>]*data-max-rows="\d+"')

    def test_display_assets_contain_no_emoji_and_no_inline_styles(self):
        emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
        for path in ("core/static/core/display.js", "core/static/core/display.css",
                     "templates/core/display.html", "templates/core/_display_surface.html"):
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIsNone(emoji.search(text), path)
        script = (ROOT / "core/static/core/display.js").read_text(encoding="utf-8")
        self.assertNotIn(".innerHTML", script)
        self.assertNotIn(".style.", script.replace("layer.style.backgroundImage", "").replace("bar.style.width", ""))

    def test_grid_rows_shrink_and_frame_is_kiosk_only(self):
        css = (ROOT / "core/static/core/display.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-rows: auto minmax(0, 1fr) auto auto;", css)
        kiosk = css[css.index("@media (min-width: 901px) {\n  .display-kiosk {"):]
        self.assertIn("--frame-w: min(100vw, calc(100vh * 16 / 9));", kiosk)
        self.assertIn("place-items: center;", kiosk)
        self.assertIn("aspect-ratio: 16 / 9;", kiosk)
        # Das Raster selbst trägt keine feste Seitenrate mehr außerhalb des Kiosks.
        self.assertNotIn(".display-grid-16x9 {\n  aspect-ratio", css)


class AccessibilityTokenTests(TestCase):
    """Kontraste aus tokens.css, hell und dunkel (WCAG 1.4.3 und 1.4.11)."""

    @staticmethod
    def luminance(hex_color):
        value = hex_color.lstrip("#")
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def ratio(self, a, b):
        high, low = sorted((self.luminance(a), self.luminance(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def themes(self):
        css = (ROOT / "core/static/core/tokens.css").read_text(encoding="utf-8")
        light = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", css[: css.index("@media (prefers-color-scheme: dark)")]))
        dark_block = css[css.index(':root[data-theme="dark"]'):]
        dark = dict(light)
        dark.update(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", dark_block))
        return {"hell": light, "dunkel": dark}

    def test_selected_chip_text_and_focus_ring(self):
        for name, tokens in self.themes().items():
            with self.subTest(theme=name):
                self.assertGreaterEqual(self.ratio(tokens["--on-primary"], tokens["--brand"]), 4.5)
                for surface in ("--surface", "--bg", "--surface-soft"):
                    self.assertGreaterEqual(self.ratio(tokens["--focus-halo"], tokens[surface]), 3.0, surface)
                    self.assertGreaterEqual(self.ratio(tokens["--muted"], tokens[surface]), 4.5, surface)

    def test_focus_ring_token_is_defined_in_both_themes(self):
        css = (ROOT / "core/static/core/tokens.css").read_text(encoding="utf-8")
        self.assertEqual(css.count("--focus-ring: 0 0 0 6px var(--focus-halo);"), 3)
        app = (ROOT / "core/static/core/app.css").read_text(encoding="utf-8")
        self.assertNotIn("--display-accent", app)
        chip = re.search(r'\.chip-pill:has\(input\[type="radio"\]:checked\),\n\.chip-pill\.is-selected \{(.*?)\}', app, re.S)
        self.assertIn("color: var(--on-primary);", chip.group(1))
        focus = re.search(r'\.chip-pill:has\(input\[type="radio"\]:focus-visible\) \{(.*?)\}', app, re.S).group(1)
        self.assertIn("var(--focus)", focus)
        self.assertIn("var(--focus-ring)", focus)

    def test_coffee_months_keep_full_opacity_and_a_text_label(self):
        app = (ROOT / "core/static/core/app.css").read_text(encoding="utf-8")
        self.assertNotRegex(app, r"\.coffee-month\.is-(future|none)[^{]*\{[^}]*opacity")
        template = (ROOT / "templates/core/coffee.html").read_text(encoding="utf-8")
        self.assertIn('{% translate "kein Beitrag" %}', template)
        self.assertNotIn("{% else %}–{% endif %}", template)


class A11yCiJobTests(TestCase):
    """Der Browser-Teil (axe-core, Display-Geometrie, Handybreite) läuft im CI-Job „a11y“."""

    def test_ci_runs_axe_and_display_geometry(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow[workflow.index("\n  a11y:"):]
        for step in ("python manage.py collectstatic --noinput", "gunicorn --config config/gunicorn.py",
                     "npm ci --ignore-scripts", "node run-axe.js", "actions/upload-artifact@"):
            self.assertIn(step, job)
        self.assertNotIn("manage.py runserver", job)
        self.assertIn("--select E4,E7,E9,F63,F7,F82", workflow)
        runner = (ROOT / "tests/a11y/run-axe.js").read_text(encoding="utf-8")
        self.assertIn("{ width: 1920, height: 1080 }, { width: 1280, height: 720 }", runner)
        self.assertIn("const PHONE = { width: 390, height: 844 };", runner)
        self.assertIn("['defect-form-phone', '/maengel/neu/', PHONE]", runner)
        for check in ("document scrolls", "grid ratio", "elements outside the viewport", "elements clipped by the grid",
                      "cut off inside the grid", "emoji in display text", "scrolls sideways"):
            self.assertIn(check, runner)
        self.assertIn("'critical,serious'", runner)

    def test_proxies_accept_a_photo_with_form_overhead(self):
        for path in ("deploy/pilot/nginx-https.conf.template", "deploy/pi/nginx.conf.template"):
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("client_max_body_size 12M;", text, path)
        caddy = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
        self.assertIn("max_size 20MB", caddy)
