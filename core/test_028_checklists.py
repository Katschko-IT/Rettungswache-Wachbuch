"""Tests für 0.28 Paket 2: Checklisten mit Ergebnis je Punkt, Messwerten & Mangel-Anlage."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .api.views import hash_api_token
from .checklists_models import ChecklistRun, ChecklistTemplate
from .models import ApiToken, Checklist, ChecklistCompletion, ChecklistItem, Membership, Station
from .wachalltag_models import Defect

User = get_user_model()


class Checklist028Tests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Rettungswache Nord",
            slug="rw-nord",
            checklists_enabled=True,
        )
        self.user = User.objects.create_user(
            username="wachschicht1",
            password="test-password-123!",
            first_name="Alex",
        )
        Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        self.client.force_login(self.user)

        self.checklist = Checklist.objects.create(
            station=self.station,
            title="Tägliche Kühlschrank- & Geräteprüfung",
            description="Morgendlicher Rundgang",
            is_active=True,
        )
        self.item_temp = ChecklistItem.objects.create(
            checklist=self.checklist,
            text="Medikamentenkühlschrank Temperatur",
            position=1,
            is_required=True,
            measurement_unit="°C",
            min_value=Decimal("2.00"),
            max_value=Decimal("8.00"),
        )
        self.item_seal = ChecklistItem.objects.create(
            checklist=self.checklist,
            text="Notfallrucksack Plombe intakt",
            position=2,
            is_required=True,
        )
        self.item_opt = ChecklistItem.objects.create(
            checklist=self.checklist,
            text="Sonderfahrzeug Zusatzheizung",
            position=3,
            is_required=False,
        )

    def test_aliases_exposed(self):
        self.assertIs(ChecklistTemplate, Checklist)
        self.assertIs(ChecklistRun, ChecklistCompletion)

    def test_per_item_results_ok_and_na_requires_reason(self):
        url = reverse("checklist_complete", args=[self.checklist.id])

        # 'na' without reason fails validation on final completion
        resp = self.client.post(
            url,
            {
                f"result_{self.item_temp.id}": "ok",
                f"value_{self.item_temp.id}": "5.2",
                f"result_{self.item_seal.id}": "na",
                f"reason_{self.item_seal.id}": "",
                "action": "complete",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

        # 'na' with reason succeeds
        resp = self.client.post(
            url,
            {
                f"result_{self.item_temp.id}": "ok",
                f"value_{self.item_temp.id}": "5.2",
                f"result_{self.item_seal.id}": "na",
                f"reason_{self.item_seal.id}": "Rucksack aktuell im Desinfektionsraum",
                "action": "complete",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 1)
        run = ChecklistCompletion.objects.first()
        self.assertFalse(run.is_draft)
        self.assertEqual(run.item_results[str(self.item_temp.id)]["status"], "ok")
        self.assertAlmostEqual(run.item_results[str(self.item_temp.id)]["value"], 5.2)
        self.assertEqual(run.item_results[str(self.item_seal.id)]["status"], "na")
        self.assertEqual(
            run.item_results[str(self.item_seal.id)]["reason"],
            "Rucksack aktuell im Desinfektionsraum",
        )
        self.assertEqual(Defect.objects.count(), 0)

    def test_measurement_out_of_bounds_marks_not_ok_and_creates_defect(self):
        url = reverse("checklist_complete", args=[self.checklist.id])
        # User selects 'ok' but enters 9.5 °C (above 8.00 °C max_value)
        resp = self.client.post(
            url,
            {
                f"result_{self.item_temp.id}": "ok",
                f"value_{self.item_temp.id}": "9,5",
                f"result_{self.item_seal.id}": "ok",
                "action": "complete",
            },
        )
        self.assertEqual(resp.status_code, 302)
        run = ChecklistCompletion.objects.get()
        temp_res = run.item_results[str(self.item_temp.id)]
        self.assertEqual(temp_res["status"], "not_ok")
        self.assertAlmostEqual(temp_res["value"], 9.5)
        self.assertIsNotNone(temp_res["defect_id"])

        defect = Defect.objects.get(pk=temp_res["defect_id"])
        self.assertEqual(defect.station, self.station)
        self.assertIn("Medikamentenkühlschrank Temperatur", defect.title)
        self.assertIn("9.5 °C", defect.description)
        self.assertIn("2.00..8.00", defect.description)

    def test_explicit_not_ok_creates_defect_with_back_reference_via_api(self):
        raw_token = "wb_test_028_checklist_token_1234567890"
        ApiToken.objects.create(
            user=self.user,
            label="Test 028",
            token_prefix=raw_token[:11],
            token_hash=hash_api_token(raw_token),
            scopes=["read:checklists", "write:checklists"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        api_url = reverse("api_v1_checkliste_erledigt", args=[self.checklist.id])
        payload = {
            "note": "Plombe gerissen",
            "is_draft": False,
            "item_results": {
                str(self.item_temp.id): {"status": "ok", "value": 4.8},
                str(self.item_seal.id): {
                    "status": "not_ok",
                    "reason": "Plombe fehlt nach Einsatz",
                },
            },
        }
        resp = self.client.post(
            api_url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertFalse(data["is_draft"])
        self.assertEqual(len(data["defects_created"]), 1)

        defect_id = data["defects_created"][0]
        defect = Defect.objects.get(pk=defect_id)
        self.assertIn("Notfallrucksack Plombe intakt", defect.title)
        self.assertIn("Plombe fehlt nach Einsatz", defect.description)

        run = ChecklistCompletion.objects.get(pk=data["id"])
        self.assertEqual(
            run.item_results[str(self.item_seal.id)]["defect_id"],
            defect.id,
        )

    def test_draft_save_and_subsequent_completion(self):
        url = reverse("checklist_complete", args=[self.checklist.id])

        # Save partial draft (missing required item_seal, and item_temp is not_ok)
        resp = self.client.post(
            url,
            {
                f"result_{self.item_temp.id}": "not_ok",
                f"value_{self.item_temp.id}": "1.2",
                "note": "Unterbrochen durch Einsatz",
                "action": "draft",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 1)
        draft = ChecklistCompletion.objects.first()
        self.assertTrue(draft.is_draft)
        # Draft does NOT create defects yet
        self.assertEqual(Defect.objects.count(), 0)

        # Abschluss legt einen neuen Datensatz an; der Zwischenstand bleibt unverändert
        resp = self.client.post(
            url,
            {
                "draft_id": str(draft.id),
                f"result_{self.item_temp.id}": "not_ok",
                f"value_{self.item_temp.id}": "1.2",
                f"result_{self.item_seal.id}": "ok",
                "note": "Nach Einsatz abgeschlossen",
                "action": "complete",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 2)
        draft.refresh_from_db()
        self.assertTrue(draft.is_draft)
        self.assertEqual(draft.note, "Unterbrochen durch Einsatz")
        completed = ChecklistCompletion.objects.get(is_draft=False)
        self.assertNotEqual(completed.pk, draft.pk)
        self.assertEqual(completed.note, "Nach Einsatz abgeschlossen")
        self.assertEqual(Defect.objects.count(), 1)

        # Auch Zwischenstände sind append-only (kein UPDATE/DELETE für die App-Rolle)
        draft.note = "Manipulationsversuch"
        with self.assertRaises(ValidationError):
            draft.save()
        with self.assertRaises(ValidationError):
            draft.delete()

        # Finalized completion is append-only (cannot be modified or deleted)
        completed.note = "Manipulationsversuch"
        with self.assertRaises(ValidationError):
            completed.save()
        with self.assertRaises(ValidationError):
            completed.delete()


class ChecklistRobustnessTests(TestCase):
    """Review 2026-11: nan/inf und API ohne Ergebnisse bei Grenzwerten."""

    setUp = Checklist028Tests.setUp

    def test_non_finite_measurement_is_rejected_not_a_server_error(self):
        url = reverse("checklist_complete", args=[self.checklist.id])
        for raw in ("nan", "inf", "-inf", "1e999"):
            with self.subTest(value=raw):
                resp = self.client.post(url, {
                    f"result_{self.item_temp.id}": "ok",
                    f"value_{self.item_temp.id}": raw,
                    f"result_{self.item_seal.id}": "ok",
                    "action": "complete",
                })
                self.assertEqual(resp.status_code, 302)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

    def test_api_requires_item_results_when_limits_exist(self):
        raw_token = "wb_test_028_robust_token_1234567890"
        ApiToken.objects.create(
            user=self.user,
            label="Test robust",
            token_prefix=raw_token[:11],
            token_hash=hash_api_token(raw_token),
            scopes=["write:checklists"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.post(
            reverse("api_v1_checkliste_erledigt", args=[self.checklist.id]),
            data=json.dumps({"note": "ohne Ergebnisse"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ChecklistCompletion.objects.count(), 0)

    def test_huge_integer_measurement_is_a_validation_error(self):
        from .checklists_forms import validate_checklist_submission

        results, errors = validate_checklist_submission(
            self.checklist, {"item_results": {str(self.item_temp.id): {"status": "ok", "value": 10**400}}},
        )
        self.assertTrue(errors)
        self.assertIsNone(results[str(self.item_temp.id)]["value"])

    def test_checklist_form_blocks_double_submit(self):
        content = self.client.get(reverse("checklists")).content.decode("utf-8")
        self.assertIn('class="checklist-form" data-submit-once', content)
