"""Tests für UX-Verbesserungsplan Welle A (A5–A10).

Prüft:
- A5: WCAG 2.4.11 Fokus nicht verdecken (scroll-padding-bottom im Mobil-Breakpoint)
- A6: Tagesaufgaben (Anker #aufgabe-<id>, scroll-margin-top, 48px Knöpfe, Status nur bei erledigt)
- A7: Sperrbildschirm 800x480 (@media max-height:540px, einzeilige Chips mit +N weitere)
- A8: Übergabe-Detail (Primäraktion „Gelesen – quittieren“ prominent direkt unter der Information)
- A9: 403-Fehlerseite (Rollenhinweis & „Zur Übersicht“ bei authentifizierten Nutzern)
- A10: Login-Knopf am Handy vollbreit (in .form-actions verpackt)
"""

from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import HandoverEntry, Membership, Station, StationTask, StationTerminal
from core.wachalltag_models import HandoverAck
from core.tests import PilotTestCase

User = get_user_model()
ROOT = Path(settings.BASE_DIR)


class UxWelleATests(PilotTestCase):
    def test_a5_scroll_padding_bottom_in_mobile_breakpoint(self):
        """A5 (WCAG 2.4.11): Im Mobil-Breakpoint (max-width: 48rem) ist scroll-padding-bottom definiert."""
        css = (ROOT / "core" / "static" / "core" / "app.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 48rem)", css)
        self.assertIn("scroll-padding-bottom: calc(var(--nav-height, 4rem) + var(--safe-bottom, 0px) + 1rem);", css)

    def test_a6_task_row_anchor_status_and_css(self):
        """A6: Tagesaufgaben haben id=aufgabe-<pk>, scroll-margin-top, 48px Touch-Ziel und kein Offen-Badge."""
        css = (ROOT / "core" / "static" / "core" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".task-row", css)
        self.assertIn("scroll-margin-top: 5rem;", css)
        self.assertIn("min-height: 48px;", css)
        self.assertIn("min-width: 48px;", css)

        # 1. Tagesaufgaben-Seite aufrufen
        response = self.client.get(reverse("tasks_today"))
        self.assertEqual(response.status_code, 200)

        task = StationTask.objects.filter(station=self.station).first()
        self.assertIsNotNone(task)

        # Anker-ID auf der Aufgaben-Zeile vorhanden
        self.assertContains(response, f'id="aufgabe-{task.pk}"')

        # Kein redundantes "Offen"-Statuslabel bei offenen Aufgaben
        self.assertNotContains(response, '<span class="status-label neutral">Offen</span>')

        # Formular übergibt Anker im next-Feld
        self.assertContains(response, f'#aufgabe-{task.pk}')

        # 2. Umschalten auf Erledigt mit übergebenem next inkl. Anker
        target_next = f"{reverse('tasks_today')}#aufgabe-{task.pk}"
        toggle_res = self.client.post(
            reverse("task_toggle", args=[task.pk]),
            {
                "tag": timezone.localdate().isoformat(),
                "erledigt": "1",
                "next": target_next,
            },
        )
        self.assertRedirects(toggle_res, target_next)

        # 3. Erledigte Aufgabe zeigt nun das "Erledigt"-Badge
        response_after = self.client.get(reverse("tasks_today"))
        self.assertContains(response_after, '<span class="status-label success">Erledigt</span>')

    def test_a7_lockscreen_800x480_rules_and_chips(self):
        """A7: Sperrbildschirm 800x480 hat max-height:540px Regeln und einzeilige Chips mit +N weitere."""
        lock_css = (ROOT / "core" / "static" / "core" / "lockscreen.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-height: 540px)", lock_css)
        self.assertIn("flex-wrap: nowrap;", lock_css)
        self.assertIn("overflow: hidden;", lock_css)
        self.assertIn(".lock-chip-more", lock_css)

        # Template-Rendering mit mehr als 6 Fahrzeugen
        vehicles = [
            {"status": "ready", "call_sign": f"RTW 1/83-{i}", "status_short": "Einsatzbereit"}
            for i in range(1, 9)
        ]
        context = {
            "data": {"fleet_vehicles": vehicles},
            "terminal": {"station": self.station},
            "background": {"css_class": "lock-bg-01", "credit": "Test"},
        }
        rendered = render_to_string("core/terminal_home.html", context)
        # Die ersten 6 Fahrzeuge sind gerendert
        self.assertIn("RTW 1/83-1", rendered)
        self.assertIn("RTW 1/83-6", rendered)
        # 7 und 8 nicht als eigene Chips
        self.assertNotIn("RTW 1/83-7", rendered)
        # Stattdessen +2 weitere
        self.assertIn("+2 weitere", rendered)

    def test_a8_handover_detail_quittieren_prominent_at_top(self):
        """A8: „Gelesen – quittieren“ ist prominent direkt unter der Information platziert."""
        other_user = User.objects.create_user("colleague@example.org")
        Membership.objects.create(user=other_user, station=self.station, role=Membership.Role.MEMBER)

        handover = HandoverEntry.objects.create(
            station=self.station,
            author=other_user,
            title="Wichtige Schichtübergabe",
            details="Details zur Schicht.",
            priority=HandoverEntry.Priority.URGENT,
            status=HandoverEntry.Status.OPEN,
        )

        # Vor Quittierung: Knopf steht in .handover-ack-action direkt unter der Information
        res = self.client.get(reverse("handover_detail", args=[handover.pk]))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("handover-ack-action", content)
        self.assertIn("Gelesen – quittieren", content)

        # Prüfen, dass .handover-ack-action vor .summary-list und vor .handover-acks gerendert wird
        ack_action_pos = content.find("handover-ack-action")
        summary_pos = content.find("summary-list")
        acks_pos = content.find("handover-acks")
        self.assertGreater(ack_action_pos, 0)
        self.assertGreater(summary_pos, ack_action_pos, "handover-ack-action muss vor summary-list stehen")
        self.assertGreater(acks_pos, ack_action_pos, "handover-ack-action muss vor handover-acks stehen")

        # Quittieren
        ack_res = self.client.post(
            reverse("handover_detail", args=[handover.pk]),
            {"action": "acknowledge"},
        )
        self.assertRedirects(ack_res, reverse("handover_detail", args=[handover.pk]))

        # Nach Quittierung: Knopf nicht mehr da, stattdessen Hinweis
        res_acked = self.client.get(reverse("handover_detail", args=[handover.pk]))
        content_acked = res_acked.content.decode("utf-8")
        self.assertNotIn("handover-ack-action", content_acked)
        self.assertNotIn("Gelesen – quittieren", content_acked)
        self.assertIn("Du hast diese Übergabe bereits quittiert.", content_acked)

    def test_a9_403_page_authenticated_role_guidance_and_overview_link(self):
        """A9: 403 erklärt fehlende Berechtigung der Rolle und bietet „Zur Übersicht“."""
        # Authentifizierter Member versucht Admin-Bereich aufzurufen
        res = self.client.get(reverse("tasks_manage"))
        self.assertEqual(res.status_code, 403)
        self.assertContains(res, "Deine aktuelle Rolle hat keine Berechtigung für diese Seite.", status_code=403)
        self.assertContains(res, "Zur Übersicht", status_code=403)
        self.assertContains(res, reverse("dashboard"), status_code=403)
        self.assertNotContains(res, '<a class="button primary" href="/anmelden/">Anmelden</a>', status_code=403)

        # Unauthentifizierter Benutzer erhält 403-Seite mit Anmelde-Aktion
        rendered_anon = render_to_string("errors/403.html", {
            "status_code": 403,
            "error_label": "Zugriff verweigert",
        })
        self.assertIn("Du hast keine Berechtigung für diese Seite", rendered_anon)
        self.assertIn("Anmelden", rendered_anon)

    def test_a10_login_button_wrapped_in_form_actions_for_mobile_fullwidth(self):
        """A10: Login-Knopf ist in <div class="form-actions"> verpackt."""
        self.client.logout()
        res = self.client.get(reverse("login"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '<div class="form-actions">\n      <button class="button primary" type="submit">Anmelden</button>\n    </div>', html=False)

        # In app.css: Mobil-Breakpoint macht .form-actions .button vollbreit (width: 100%)
        css = (ROOT / "core" / "static" / "core" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".form-actions .button { width: 100%; }", css)
