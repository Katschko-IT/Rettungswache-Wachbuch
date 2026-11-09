"""Tests for 0.28 Paket 4: Mangel in drei Tipps + Wand-Display 16:9 ohne Emojis.

Requirements from docs/ROADMAP.md (lines 84 & 88):
1. „Mangel in drei Tipps“: Foto aufnehmen, Kategorie und Priorität als Chips,
   Bezug als Auswahl, Hinweis „bereits gemeldet“.
2. Wand-Display als festes 16:9-Raster nur im Kiosk über den Display-Link,
   ohne Emojis. Der Screenshot- und Geometrietest bei 1920x1080 und 1280x720
   läuft im Browser im CI-Job „a11y“ (.github/workflows/ci.yml,
   tests/a11y/run-axe.js, Funktion checkDisplay); hier stehen nur die
   serverseitigen Voraussetzungen. Weitere Tests: core/test_028_defects_display.py.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.display_models import DisplayToken
from core.display_views import COOKIE_NAME
from core.models import Membership, PinboardNote, Station
from core.wachalltag_models import Defect, StationAsset

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2300-\u23ff\u2b50-\u2b55]"
)


class DefectQuickFormAndDuplicateHintTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache 4", slug="wache-4")
        self.user = User.objects.create_user("notfall-san", password="password123")
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD
        )
        self.asset_rtw = StationAsset.objects.create(
            station=self.station,
            asset_id="rtw-1",
            label="RTW 1",
            kind=StationAsset.Kind.VEHICLE,
        )
        self.asset_defi = StationAsset.objects.create(
            station=self.station,
            asset_id="defi-1",
            label="Defibrillator Corpuls",
            kind=StationAsset.Kind.DEVICE,
        )
        self.client.force_login(self.user)

    def test_duplicate_hint_data_is_escaped_json_script(self):
        """Mangeltitel dürfen den JSON-Block nicht verlassen (kein |safe, kein Inline-Skript)."""
        Defect.objects.create(
            station=self.station,
            title="</script><img src=x onerror=alert(1)>",
            asset_ref="RTW 1",
            created_by=self.user,
        )
        response = self.client.get(reverse("defect_create_web"))
        content = response.content.decode("utf-8")
        self.assertNotIn("</script><img", content)
        self.assertIn('id="defects-data"', content)
        self.assertIn("\\u003C/script\\u003E", content)
        self.assertNotRegex(content, r"<script(?![^>]*\ssrc=)(?![^>]*type=\"application/json\")")

    def test_defect_create_renders_3_step_quick_form(self):
        """Page renders 3-step quick form: photo input, category/priority chips, asset reference."""
        response = self.client.get(reverse("defect_create_web"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Tipp 1: Foto aufnehmen (accept="image/*" capture="environment")
        self.assertIn('accept="image/*"', content)
        self.assertIn('capture="environment"', content)
        self.assertIn("Foto aufnehmen", content)
        self.assertIn('name="attachments"', content)

        # Tipp 2: Kategorie und Priorität als Chips (Segment-Chips / Radiogroup)
        self.assertIn('role="radiogroup"', content)
        self.assertIn('name="priority"', content)
        self.assertIn('name="category"', content)
        self.assertIn('value="normal"', content)
        self.assertIn("chip-pill", content)

        # Tipp 3: Bezug als Auswahl (StationAsset options)
        self.assertIn('name="asset_ref"', content)
        self.assertIn("RTW 1", content)
        self.assertIn("Defibrillator Corpuls", content)

    def test_defect_create_shows_already_reported_hint_when_open_defect_exists(self):
        """Page shows 'Bereits gemeldet' warning banner when an open defect exists for the selected asset."""
        open_defect = Defect.objects.create(
            station=self.station,
            title="Blaulicht links defekt",
            asset_ref="RTW 1",
            priority=Defect.Priority.URGENT,
            status=Defect.Status.OPEN,
            created_by=self.user,
        )

        # Query by asset_id
        response = self.client.get(reverse("defect_create_web"), {"asset": "rtw-1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bereits gemeldet")
        self.assertContains(response, "Blaulicht links defekt")
        self.assertEqual(len(response.context["already_reported_defects"]), 1)
        self.assertEqual(response.context["already_reported_defects"][0].pk, open_defect.pk)
        self.assertEqual(response.context["already_reported_count"], 1)

        # Query by asset_ref
        response_ref = self.client.get(reverse("defect_create_web"), {"asset_ref": "RTW 1"})
        self.assertEqual(response_ref.status_code, 200)
        self.assertContains(response_ref, "Bereits gemeldet")
        self.assertContains(response_ref, "Blaulicht links defekt")

    def test_defect_create_shows_no_warning_when_no_defect_for_asset(self):
        """When an asset without open defects is selected, no 'Bereits gemeldet' banner is active."""
        response = self.client.get(reverse("defect_create_web"), {"asset": "defi-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["already_reported_defects"]), 0)
        self.assertEqual(response.context["already_reported_count"], 0)

    def test_defect_create_submits_with_chips_and_asset_choice(self):
        """Form submission creates Defect with selected priority, category, asset, and optional photo."""
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), color=(20, 40, 80)).save(buf, format="JPEG")
        fake_photo = SimpleUploadedFile("kamera.jpg", buf.getvalue(), content_type="image/jpeg")
        post_data = {
            "title": "Akkudeckel locker",
            "description": "Schließt nicht mehr zuverlässig.",
            "priority": "important",
            "category": "device",
            "asset_ref": "Defibrillator Corpuls",
            "attachments": fake_photo,
        }
        response = self.client.post(reverse("defect_create_web"), post_data)
        self.assertEqual(response.status_code, 302)

        created = Defect.objects.filter(
            station=self.station,
            title="Akkudeckel locker",
            priority=Defect.Priority.IMPORTANT,
            category=Defect.Category.DEVICE,
            asset_ref="Defibrillator Corpuls",
        ).first()
        self.assertIsNotNone(created)
        self.assertEqual(created.status, Defect.Status.OPEN)
        self.assertEqual(created.attachments.count(), 1)


class WallDisplay16x9AndEmojiTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Wanddisplay",
            slug="wache-wanddisplay",
            display_enabled=True,
            pinboard_enabled=True,
            tasks_enabled=True,
            fleet_enabled=True,
        )
        self.user = User.objects.create_user("display-admin", password="password123")
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.ADMIN
        )
        self.token_raw = secrets.token_urlsafe(32)
        DisplayToken.objects.create(
            station=self.station,
            label="Kiosk Flur",
            token_hash=hashlib.sha256(self.token_raw.encode()).hexdigest(),
            created_by=self.user,
        )
        self.client.cookies[COOKIE_NAME] = self.token_raw

    def test_wall_display_renders_with_display_grid_16x9_layout(self):
        """Wall display renders with display-grid-16x9 layout and no inline style attributes."""
        response = self.client.get(reverse("display_home"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("display-grid-16x9", content)
        self.assertNotIn("style=", content)

    def test_wall_display_view_contains_zero_emojis(self):
        """Rendered wall display contains zero emojis (checked via regex against emoji codepoints)."""
        # Create pinboard notes and ensure news/pinboard items exist
        PinboardNote.objects.create(
            station=self.station,
            title="Wichtige Durchsage",
            category="info",
            is_pinned=True,
            author=self.user,
        )

        response = self.client.get(reverse("display_home"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        found_emojis = EMOJI_PATTERN.findall(content)
        self.assertEqual(
            found_emojis,
            [],
            f"Wall display template contains emojis: {found_emojis}",
        )

    def test_display_data_payload_contains_zero_emojis(self):
        """JSON payload for display data contains zero emojis."""
        PinboardNote.objects.create(
            station=self.station,
            title="Wichtige Pinnwandnotiz",
            category="info",
            is_pinned=True,
            author=self.user,
        )

        response = self.client.get(reverse("display_data"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        found_emojis = EMOJI_PATTERN.findall(content)
        self.assertEqual(
            found_emojis,
            [],
            f"Display JSON payload contains emojis: {found_emojis}",
        )

    def test_16x9_geometry_is_checked_in_the_browser_by_ci(self):
        """Kein Ersatz-Screenshot per Textsuche: Der CI-Job „a11y“ rendert das Display.

        Früher prüfte dieser Test nur Zeichenketten in display.css und blieb grün,
        obwohl Fußzeile und Laufschrift außerhalb des Rahmens lagen. Die Geometrie
        (kein Scrollen, Raster 16:9, nichts außerhalb von Raster oder Bildschirm,
        keine abgeschnittene Spalte, keine Emojis) prüft jetzt run-axe.js im
        Browser; hier bleibt nur, dass es den Rahmen gibt und der Job ihn prüft.
        """
        root = Path(__file__).resolve().parent.parent
        css_text = (root / "core" / "static" / "core" / "display.css").read_text(encoding="utf-8")
        self.assertIn(".display-grid-16x9", css_text)
        self.assertIn("aspect-ratio: 16 / 9;", css_text)

        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("\n  a11y:", workflow)
        runner = (root / "tests" / "a11y" / "run-axe.js").read_text(encoding="utf-8")
        self.assertIn("async function checkDisplay(", runner)
        self.assertIn("{ width: 1920, height: 1080 }, { width: 1280, height: 720 }", runner)
        self.assertIn("display-${size.width}x${size.height}-${themeName}.png", runner)
