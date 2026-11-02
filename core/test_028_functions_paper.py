from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.disinfection_plan import can_confirm_disinfection
from core.forms import MembershipEditForm, ShiftHandoverForm
from core.models import HandoverEntry, Membership, ShiftHandover, Station


class MembershipFunctionsTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache 1", slug="wache-1")
        self.admin_user = User.objects.create_user(username="admin", password="password123")
        self.admin_membership = Membership.objects.create(
            user=self.admin_user,
            station=self.station,
            role=Membership.Role.ADMIN,
        )
        self.user = User.objects.create_user(username="sanitaeter", password="password123")
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )

    def test_default_function_flags_and_labels(self):
        m = self.membership
        self.assertFalse(m.is_mpg_lead)
        self.assertFalse(m.is_hygiene_lead)
        self.assertFalse(m.is_material_lead)
        self.assertFalse(m.is_fleet_lead)
        self.assertFalse(m.is_safety_lead)
        self.assertEqual(m.function_labels, [])
        self.assertEqual(m.function_labels(), [])

    def test_all_function_flags_and_labels(self):
        m = self.membership
        m.is_mpg_lead = True
        m.is_hygiene_lead = True
        m.is_material_lead = True
        m.is_fleet_lead = True
        m.is_safety_lead = True
        m.save()

        expected = [
            "MPG-Beauftragte/r",
            "Hygiene / Desinfektor:in",
            "Material / Lager",
            "Fuhrpark",
            "Sicherheit / Arbeitsschutz",
        ]
        self.assertEqual(list(m.function_labels), expected)
        self.assertEqual(list(m.function_labels()), expected)

    def test_partial_function_flags(self):
        m = self.membership
        m.is_hygiene_lead = True
        m.is_fleet_lead = True
        m.save()

        self.assertEqual(list(m.function_labels), ["Hygiene / Desinfektor:in", "Fuhrpark"])

    def test_can_confirm_disinfection_hygiene_lead(self):
        # Regular member without hygiene lead cannot confirm disinfection
        self.assertFalse(can_confirm_disinfection(self.membership))

        # Regular member with hygiene lead can confirm disinfection
        self.membership.is_hygiene_lead = True
        self.membership.save()
        self.assertTrue(can_confirm_disinfection(self.membership))

        # Inactive member cannot confirm even with hygiene lead
        self.membership.is_active = False
        self.membership.save()
        self.assertFalse(can_confirm_disinfection(self.membership))

        # Shift lead and Admin can confirm
        self.assertTrue(can_confirm_disinfection(self.admin_membership))

    def test_membership_edit_form_and_view(self):
        form = MembershipEditForm(membership=self.membership)
        self.assertIn("is_mpg_lead", form.fields)
        self.assertIn("is_hygiene_lead", form.fields)
        self.assertIn("is_material_lead", form.fields)
        self.assertIn("is_fleet_lead", form.fields)
        self.assertIn("is_safety_lead", form.fields)

        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("membership_update", args=[self.membership.pk]),
            {
                "role": Membership.Role.MEMBER,
                "is_active": "on",
                "is_mpg_lead": "on",
                "is_hygiene_lead": "on",
                "is_material_lead": "on",
                "is_fleet_lead": "on",
                "is_safety_lead": "on",
            },
        )
        self.assertRedirects(response, reverse("team"))
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_mpg_lead)
        self.assertTrue(self.membership.is_hygiene_lead)
        self.assertTrue(self.membership.is_material_lead)
        self.assertTrue(self.membership.is_fleet_lead)
        self.assertTrue(self.membership.is_safety_lead)


class PaperBackfillHandoverTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache 1", slug="wache-1")
        self.user = User.objects.create_user(username="sanitaeter", password="password123")
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )
        self.client.force_login(self.user)

    def test_form_validation_for_paper_backfill(self):
        now = timezone.now()
        past_time = now - timedelta(hours=3)
        future_time = now + timedelta(hours=2)

        # Backfill without occurred_at is invalid
        form = ShiftHandoverForm(
            data={
                "category": HandoverEntry.Category.STATION,
                "priority": HandoverEntry.Priority.NORMAL,
                "title": "Papier-Übergabe",
                "details": "Details der Übergabe",
                "is_paper_backfill": True,
                "occurred_at": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)

        # Backfill with future occurred_at is invalid
        form_future = ShiftHandoverForm(
            data={
                "category": HandoverEntry.Category.STATION,
                "priority": HandoverEntry.Priority.NORMAL,
                "title": "Papier-Übergabe Zukunft",
                "details": "Details",
                "is_paper_backfill": True,
                "occurred_at": future_time.strftime("%Y-%m-%dT%H:%M"),
            }
        )
        self.assertFalse(form_future.is_valid())
        self.assertIn("occurred_at", form_future.errors)

        # Backfill with past occurred_at is valid
        form_valid = ShiftHandoverForm(
            data={
                "category": HandoverEntry.Category.STATION,
                "priority": HandoverEntry.Priority.NORMAL,
                "title": "Papier-Übergabe Gültig",
                "details": "Details",
                "is_paper_backfill": True,
                "occurred_at": past_time.strftime("%Y-%m-%dT%H:%M"),
            }
        )
        self.assertTrue(form_valid.is_valid())

        # Non-backfill without occurred_at is valid
        form_normal = ShiftHandoverForm(
            data={
                "category": HandoverEntry.Category.STATION,
                "priority": HandoverEntry.Priority.NORMAL,
                "title": "Normale Übergabe",
                "details": "Details",
                "is_paper_backfill": False,
                "occurred_at": "",
            }
        )
        self.assertTrue(form_normal.is_valid())

    def test_shift_handover_paper_backfill_display(self):
        now = timezone.now()
        occurred = now - timedelta(hours=4)

        # Create handover via view
        response = self.client.post(
            reverse("handover_create"),
            {
                "category": HandoverEntry.Category.STATION,
                "priority": HandoverEntry.Priority.NORMAL,
                "title": "Handschriftlicher Bogen Frühschicht",
                "details": "Wache sauber übergeben laut Papierprotokoll.",
                "is_paper_backfill": "on",
                "occurred_at": occurred.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        handover = ShiftHandover.objects.get(title="Handschriftlicher Bogen Frühschicht")
        self.assertRedirects(response, reverse("handover_detail", args=[handover.pk]))
        self.assertTrue(handover.is_paper_backfill)
        self.assertIsNotNone(handover.occurred_at)

        # Detail view shows paper backfill badge with both timestamps
        detail_response = self.client.get(reverse("handover_detail", args=[handover.pk]))
        self.assertEqual(detail_response.status_code, 200)
        content = detail_response.content.decode("utf-8")
        self.assertIn("Nachtrag von Papier", content)
        self.assertIn("Ereignis:", content)
        self.assertIn("Erfasst:", content)
        self.assertIn(handover.occurred_at.strftime("%d.%m.%Y"), content)
        self.assertIn(handover.created_at.strftime("%d.%m.%Y"), content)

        # List view shows paper backfill badge
        list_response = self.client.get(reverse("handover_list"))
        self.assertEqual(list_response.status_code, 200)
        list_content = list_response.content.decode("utf-8")
        self.assertIn("Nachtrag von Papier", list_content)
        self.assertIn("Ereignis:", list_content)
        self.assertIn("Erfasst:", list_content)

    def test_normal_handover_does_not_display_paper_backfill_badge(self):
        handover = ShiftHandover.objects.create(
            station=self.station,
            category=HandoverEntry.Category.STATION,
            priority=HandoverEntry.Priority.NORMAL,
            title="Normale digitale Übergabe",
            details="Alles in Ordnung",
            author=self.user,
            is_paper_backfill=False,
        )
        detail_response = self.client.get(reverse("handover_detail", args=[handover.pk]))
        content = detail_response.content.decode("utf-8")
        self.assertNotIn("Nachtrag von Papier", content)
