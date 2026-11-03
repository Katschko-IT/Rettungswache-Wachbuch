"""Barrierefreiheit: Muster aus dem Audit vom 2026-11-03 (WCAG 2.1 AA).

Prüft Markup und die deklarativen Bausteine in ``ui.js``. Ein Screenreader-
und Zoom-Test im Browser bleibt nach Go-live-Checkliste erforderlich.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Checklist, ChecklistItem, Membership, Station

UI_JS = Path(settings.BASE_DIR) / "core" / "static" / "core" / "ui.js"


class ChecklistFormA11yTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache A11y", slug="wache-a11y", checklists_enabled=True)
        user = get_user_model().objects.create_user("a11y-user", password="test-password-123!")
        Membership.objects.create(user=user, station=self.station, role=Membership.Role.MEMBER)
        self.client.force_login(user)
        self.checklist = Checklist.objects.create(station=self.station, title="Kühlschrank", is_active=True)
        self.item = ChecklistItem.objects.create(
            checklist=self.checklist,
            text="Temperatur",
            position=1,
            measurement_unit="°C",
            min_value=Decimal("0"),
            max_value=Decimal("8"),
        )

    def test_each_item_is_a_labelled_group_with_labelled_fields(self):
        content = self.client.get(reverse("checklists")).content.decode("utf-8")
        self.assertIn('<fieldset class="item-controls cluster">', content)
        self.assertIn("Ergebnis für: Temperatur", content)
        for field_id in (f"value_{self.item.id}", f"reason_{self.item.id}", f"note_{self.checklist.id}"):
            self.assertIn(f'id="{field_id}"', content)
            self.assertIn(f'for="{field_id}"', content)

    def test_lower_limit_zero_is_shown(self):
        content = self.client.get(reverse("checklists")).content.decode("utf-8")
        self.assertRegex(content, r"Soll:\s*0[.,]00\s*–\s*8[.,]00")


class UiScriptA11yTests(SimpleTestCase):
    def setUp(self):
        self.js = UI_JS.read_text(encoding="utf-8")

    def test_modal_traps_tab_and_blocks_background(self):
        self.assertIn("inertBackground(modal)", self.js)
        self.assertIn("releaseBackground()", self.js)
        self.assertIn('event.key === "Tab"', self.js)

    def test_idle_logout_warns_and_can_be_extended(self):
        self.assertIn("data-idle-warning", self.js)
        self.assertIn("data-idle-extend", self.js)

    def test_form_errors_are_linked_to_fields(self):
        self.assertIn("aria-invalid", self.js)
        self.assertIn("aria-describedby", self.js)
        self.assertIn("data-error-list", self.js)


class TerminalBarA11yTests(SimpleTestCase):
    def test_countdown_is_not_a_live_region(self):
        base = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertNotIn('class="terminal-session-bar" role="status"', base)
        self.assertIn("data-idle-countdown aria-hidden=\"true\"", base)
        self.assertIn("data-idle-warning", base)
        self.assertIn("data-idle-extend", base)


class TableMarkupTests(SimpleTestCase):
    """Jede Tabelle der Oberfläche hat einen Namen, jede Kopfzelle einen scope (WCAG 1.3.1)."""

    def _tables(self):
        import re

        root = Path(settings.BASE_DIR) / "templates" / "core"
        for path in sorted(root.glob("*.html")):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"<table\b[^>]*>", text):
                segment = text[match.start():text.find("</table>", match.start())]
                yield path.name, match.group(0), segment

    def test_every_table_has_a_caption_or_label(self):
        missing = [
            name for name, tag, segment in self._tables()
            if "<caption" not in segment and "aria-label" not in tag
        ]
        self.assertEqual(missing, [])

    def test_every_header_cell_has_a_scope(self):
        import re

        missing = [
            name for name, _tag, segment in self._tables()
            if re.search(r"<th(?=[\s>])(?![^>]*\bscope=)[^>]*>", segment)
        ]
        self.assertEqual(missing, [])


class ChecklistProgressTests(TestCase):
    setUp = ChecklistFormA11yTests.setUp

    def test_progress_box_is_hidden_until_script_runs_and_not_live(self):
        content = self.client.get(reverse("checklists")).content.decode("utf-8")
        self.assertIn("data-checklist-progress", content)
        self.assertIn("data-progress-box hidden", content)
        self.assertIn("0 von 1 Prüfpunkten beantwortet", content)
        self.assertNotIn('data-progress-text role="status"', content)
