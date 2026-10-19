"""Functional and negative tests for four core routes in Phase 1 / G1:

1. chat_hide (core/community_views.py)
2. task_edit (core/views.py)
3. checklist_complete (core/views.py)
4. station_member_keys (core/secure_views.py)

Each route is tested with:
- Positive path
- Role matrix (MEMBER, CASHIER, SHIFT_LEAD, ADMIN, AUDITOR)
- Cross-station isolation (Fremdwache)
- Invalid HTTP methods
- Route-specific invariants (audit content redaction, module deactivation,
  ledger append-only behavior, input validation and secret leakage prevention).
"""

from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from core.models import (
    AuditEvent,
    ChatMessage,
    Checklist,
    ChecklistCompletion,
    Membership,
    Station,
    StationTask,
    UserCryptoIdentity,
)


class BasePhase1RoutesTestCase(TestCase):
    """Shared test fixture providing two isolated stations and users for all roles."""

    def setUp(self):
        super().setUp()
        self.station_a = Station.objects.create(
            name="Wache Alpha",
            slug="wache-alpha",
            chat_enabled=True,
            tasks_enabled=True,
            checklists_enabled=True,
        )
        self.station_b = Station.objects.create(
            name="Wache Beta",
            slug="wache-beta",
            chat_enabled=True,
            tasks_enabled=True,
            checklists_enabled=True,
        )

        self.user_member = self._create_user_with_role(
            "user_member_a", self.station_a, Membership.Role.MEMBER
        )
        self.user_cashier = self._create_user_with_role(
            "user_cashier_a", self.station_a, Membership.Role.CASHIER
        )
        self.user_lead = self._create_user_with_role(
            "user_lead_a", self.station_a, Membership.Role.SHIFT_LEAD
        )
        self.user_admin = self._create_user_with_role(
            "user_admin_a", self.station_a, Membership.Role.ADMIN
        )
        self.user_auditor = self._create_user_with_role(
            "user_auditor_a", self.station_a, Membership.Role.AUDITOR
        )

        self.user_beta_member = self._create_user_with_role(
            "user_member_b", self.station_b, Membership.Role.MEMBER
        )
        self.user_beta_lead = self._create_user_with_role(
            "user_lead_b", self.station_b, Membership.Role.SHIFT_LEAD
        )
        self.user_beta_admin = self._create_user_with_role(
            "user_admin_b", self.station_b, Membership.Role.ADMIN
        )

    def _create_user_with_role(self, username: str, station: Station, role: str) -> User:
        user = User.objects.create_user(username=username, password="TestPassword123!")
        Membership.objects.create(user=user, station=station, role=role, is_active=True)
        return user


class ChatHideRouteTests(BasePhase1RoutesTestCase):
    """Tests for chat_hide route (core/community_views.py)."""

    def setUp(self):
        super().setUp()
        self.message_a = ChatMessage.objects.create(
            station=self.station_a,
            author=self.user_member,
            body="Sensible interne Meldung auf Wache Alpha",
            is_hidden=False,
        )
        self.message_b = ChatMessage.objects.create(
            station=self.station_b,
            author=self.user_beta_member,
            body="Nachricht auf Fremdwache Beta",
            is_hidden=False,
        )
        self.hide_url_a = reverse("chat_hide", kwargs={"pk": self.message_a.pk})
        self.hide_url_b = reverse("chat_hide", kwargs={"pk": self.message_b.pk})

    def test_positive_path_shift_lead_can_hide_message(self):
        client = Client()
        client.force_login(self.user_lead)

        response = client.post(self.hide_url_a)
        self.assertRedirects(response, reverse("chat"))

        self.message_a.refresh_from_db()
        self.assertTrue(self.message_a.is_hidden)

    def test_positive_path_admin_can_hide_message(self):
        client = Client()
        client.force_login(self.user_admin)

        response = client.post(self.hide_url_a)
        self.assertRedirects(response, reverse("chat"))

        self.message_a.refresh_from_db()
        self.assertTrue(self.message_a.is_hidden)

    def test_role_matrix_member_and_cashier_and_auditor_forbidden(self):
        for user in (self.user_member, self.user_cashier, self.user_auditor):
            with self.subTest(role=user.station_memberships.first().role):
                client = Client()
                client.force_login(user)
                response = client.post(self.hide_url_a)
                self.assertEqual(response.status_code, 403)
                self.message_a.refresh_from_db()
                self.assertFalse(self.message_a.is_hidden)

    def test_foreign_station_message_returns_404(self):
        # Shift Lead and Admin of Station A cannot hide messages from Station B
        for user in (self.user_lead, self.user_admin):
            with self.subTest(role=user.station_memberships.first().role):
                client = Client()
                client.force_login(user)
                response = client.post(self.hide_url_b)
                self.assertEqual(response.status_code, 404)
                self.message_b.refresh_from_db()
                self.assertFalse(self.message_b.is_hidden)

    def test_get_method_not_allowed(self):
        client = Client()
        client.force_login(self.user_admin)
        response = client.get(self.hide_url_a)
        self.assertEqual(response.status_code, 405)
        self.message_a.refresh_from_db()
        self.assertFalse(self.message_a.is_hidden)

    def test_hidden_message_disappears_from_chat_feed(self):
        client_lead = Client()
        client_lead.force_login(self.user_lead)
        client_lead.post(self.hide_url_a)

        # Another normal member views the chat
        client_member = Client()
        client_member.force_login(self.user_member)
        response = client_member.get(reverse("chat"))
        self.assertEqual(response.status_code, 200)

        feed_pks = [item["message"].pk for item in response.context["feed"]]
        self.assertNotIn(self.message_a.pk, feed_pks)

        client_feed = json.loads(response.context["feed_json"])
        feed_json_pks = [item["id"] for item in client_feed]
        self.assertNotIn(self.message_a.pk, feed_json_pks)

    def test_audit_log_remains_content_free(self):
        client = Client()
        client.force_login(self.user_lead)
        client.post(self.hide_url_a)

        event = AuditEvent.objects.filter(
            station=self.station_a,
            action="chat.message_hidden",
            object_id=str(self.message_a.pk),
        ).latest("created_at")

        self.assertEqual(event.actor, self.user_lead)
        self.assertEqual(event.object_type, "ChatMessage")
        self.assertEqual(event.metadata.get("fields"), ["is_hidden"])
        self.assertEqual(
            event.metadata.get("changes"),
            {"is_hidden": {"from": False, "to": True}},
        )
        # Verify no message content or body leaks into the audit entry
        metadata_str = json.dumps(event.metadata)
        self.assertNotIn("body", event.metadata)
        self.assertNotIn("ciphertext", event.metadata)
        self.assertNotIn(self.message_a.body, metadata_str)

    def test_module_disabled_returns_404(self):
        self.station_a.chat_enabled = False
        self.station_a.save(update_fields=["chat_enabled"])

        client = Client()
        client.force_login(self.user_admin)
        response = client.post(self.hide_url_a)
        self.assertEqual(response.status_code, 404)


class TaskEditRouteTests(BasePhase1RoutesTestCase):
    """Tests for task_edit route (core/views.py)."""

    def setUp(self):
        super().setUp()
        self.task_a = StationTask.objects.create(
            station=self.station_a,
            title="Wache fegen",
            band=StationTask.Band.DAILY,
            sort_order=10,
            is_active=True,
        )
        self.task_b = StationTask.objects.create(
            station=self.station_b,
            title="Fahrzeughalle Beta wischen",
            band=StationTask.Band.DAILY,
            sort_order=20,
            is_active=True,
        )
        self.edit_url_a = reverse("task_edit", kwargs={"pk": self.task_a.pk})
        self.edit_url_b = reverse("task_edit", kwargs={"pk": self.task_b.pk})

    def test_positive_path_shift_lead_can_edit_task(self):
        client = Client()
        client.force_login(self.user_lead)

        get_res = client.get(self.edit_url_a)
        self.assertEqual(get_res.status_code, 200)

        post_data = {
            "title": "Wache gründlich fegen und lüften",
            "band": StationTask.Band.DAILY,
            "notes": "Besonders Flurbereich beachten",
            "sort_order": 15,
            "is_active": "on",
        }
        post_res = client.post(self.edit_url_a, post_data)
        self.assertRedirects(post_res, reverse("tasks_manage"))

        self.task_a.refresh_from_db()
        self.assertEqual(self.task_a.title, "Wache gründlich fegen und lüften")
        self.assertEqual(self.task_a.notes, "Besonders Flurbereich beachten")
        self.assertEqual(self.task_a.sort_order, 15)

        # Verify audit record
        event = AuditEvent.objects.filter(
            station=self.station_a,
            action="station_task.updated",
            object_id=str(self.task_a.pk),
        ).latest("created_at")
        self.assertEqual(event.actor, self.user_lead)
        self.assertIn("title", event.metadata.get("fields", []))

    def test_positive_path_admin_can_edit_task(self):
        client = Client()
        client.force_login(self.user_admin)

        post_data = {
            "title": "Aufgabe durch Admin geändert",
            "band": StationTask.Band.DAILY,
            "sort_order": 5,
            "is_active": "on",
        }
        post_res = client.post(self.edit_url_a, post_data)
        self.assertRedirects(post_res, reverse("tasks_manage"))

        self.task_a.refresh_from_db()
        self.assertEqual(self.task_a.title, "Aufgabe durch Admin geändert")

    def test_role_matrix_member_and_cashier_and_auditor_forbidden(self):
        for user in (self.user_member, self.user_cashier, self.user_auditor):
            with self.subTest(role=user.station_memberships.first().role):
                client = Client()
                client.force_login(user)

                self.assertEqual(client.get(self.edit_url_a).status_code, 403)
                self.assertEqual(
                    client.post(self.edit_url_a, {"title": "Verbotene Änderung"}).status_code,
                    403,
                )
                self.task_a.refresh_from_db()
                self.assertEqual(self.task_a.title, "Wache fegen")

    def test_foreign_station_task_returns_404(self):
        for user in (self.user_lead, self.user_admin):
            with self.subTest(role=user.station_memberships.first().role):
                client = Client()
                client.force_login(user)

                self.assertEqual(client.get(self.edit_url_b).status_code, 404)
                self.assertEqual(
                    client.post(self.edit_url_b, {"title": "Angriff auf Beta"}).status_code,
                    404,
                )
                self.task_b.refresh_from_db()
                self.assertEqual(self.task_b.title, "Fahrzeughalle Beta wischen")

    def test_invalid_input_saves_nothing(self):
        client = Client()
        client.force_login(self.user_lead)

        # 1. Missing title
        response = client.post(self.edit_url_a, {"title": "", "band": StationTask.Band.DAILY})
        self.assertEqual(response.status_code, 200)
        self.task_a.refresh_from_db()
        self.assertEqual(self.task_a.title, "Wache fegen")

        # 2. Weekday band without weekday selected
        response = client.post(
            self.edit_url_a,
            {"title": "Gültiger Titel", "band": StationTask.Band.WEEKDAY, "weekday": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.task_a.refresh_from_db()
        self.assertEqual(self.task_a.title, "Wache fegen")

    def test_unsupported_methods_return_405(self):
        client = Client()
        client.force_login(self.user_admin)
        for method in ("put", "delete", "patch"):
            with self.subTest(method=method):
                response = getattr(client, method)(self.edit_url_a)
                self.assertEqual(response.status_code, 405)

    def test_module_disabled_returns_404(self):
        self.station_a.tasks_enabled = False
        self.station_a.save(update_fields=["tasks_enabled"])

        client = Client()
        client.force_login(self.user_admin)
        self.assertEqual(client.get(self.edit_url_a).status_code, 404)
        self.assertEqual(
            client.post(self.edit_url_a, {"title": "Neu"}).status_code, 404
        )


class ChecklistCompleteRouteTests(BasePhase1RoutesTestCase):
    """Tests for checklist_complete route (core/views.py)."""

    def setUp(self):
        super().setUp()
        self.checklist_a = Checklist.objects.create(
            station=self.station_a,
            title="Täglicher RTW-Check",
            is_active=True,
        )
        self.checklist_b = Checklist.objects.create(
            station=self.station_b,
            title="KTW-Prüfung Beta",
            is_active=True,
        )
        self.complete_url_a = reverse(
            "checklist_complete", kwargs={"pk": self.checklist_a.pk}
        )
        self.complete_url_b = reverse(
            "checklist_complete", kwargs={"pk": self.checklist_b.pk}
        )

    def test_positive_path_member_can_complete_checklist(self):
        client = Client()
        client.force_login(self.user_member)

        response = client.post(self.complete_url_a, {"note": "Alles vollständig und einsatzbereit"})
        self.assertRedirects(response, reverse("checklists"))

        completion = ChecklistCompletion.objects.filter(
            station=self.station_a,
            checklist=self.checklist_a,
            completed_by=self.user_member,
        ).latest("created_at")
        self.assertEqual(completion.note, "Alles vollständig und einsatzbereit")

        # Verify audit record
        event = AuditEvent.objects.filter(
            station=self.station_a,
            action="checklist.completed",
            object_id=str(completion.pk),
        ).latest("created_at")
        self.assertEqual(event.actor, self.user_member)
        self.assertEqual(event.metadata.get("fields"), ["checklist", "note"])

    def test_role_matrix_all_content_roles_allowed_auditor_forbidden(self):
        # CONTENT_ROLES: MEMBER, CASHIER, SHIFT_LEAD, ADMIN
        for user in (self.user_cashier, self.user_lead, self.user_admin):
            with self.subTest(role=user.station_memberships.first().role):
                client = Client()
                client.force_login(user)
                response = client.post(self.complete_url_a, {"note": f"Check durch {user.username}"})
                self.assertRedirects(response, reverse("checklists"))

        # Auditor is NOT in CONTENT_ROLES
        client_auditor = Client()
        client_auditor.force_login(self.user_auditor)
        response_auditor = client_auditor.post(self.complete_url_a, {"note": "Auditor-Versuch"})
        self.assertEqual(response_auditor.status_code, 403)

    def test_foreign_station_checklist_returns_404(self):
        client = Client()
        client.force_login(self.user_member)

        response = client.post(self.complete_url_b, {"note": "Fremdwachen-Check"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ChecklistCompletion.objects.filter(checklist=self.checklist_b).count(), 0)

    def test_get_method_not_allowed(self):
        client = Client()
        client.force_login(self.user_member)
        response = client.get(self.complete_url_a)
        self.assertEqual(response.status_code, 405)

    def test_double_completion_records_each_event_in_append_only_ledger(self):
        client = Client()
        client.force_login(self.user_member)

        # First completion
        res1 = client.post(self.complete_url_a, {"note": "Erster Durchlauf"})
        self.assertRedirects(res1, reverse("checklists"))
        self.assertEqual(ChecklistCompletion.objects.filter(checklist=self.checklist_a).count(), 1)

        # Second completion creates a subsequent entry in the append-only ledger
        res2 = client.post(self.complete_url_a, {"note": "Zweiter Durchlauf am Nachmittag"})
        self.assertRedirects(res2, reverse("checklists"))
        self.assertEqual(ChecklistCompletion.objects.filter(checklist=self.checklist_a).count(), 2)

        # Invariant check: In-place update of an existing completion is strictly prevented by model
        existing = ChecklistCompletion.objects.filter(checklist=self.checklist_a).first()
        existing.note = "Nachträgliche Manipulation"
        with self.assertRaises(ValidationError):
            existing.save()

    def test_note_length_is_strictly_bounded(self):
        client = Client()
        client.force_login(self.user_member)

        long_note = "A" * 600
        client.post(self.complete_url_a, {"note": long_note})

        completion = ChecklistCompletion.objects.filter(
            station=self.station_a, checklist=self.checklist_a
        ).latest("created_at")
        self.assertEqual(len(completion.note), 300)
        self.assertEqual(completion.note, "A" * 300)

    def test_inactive_checklist_returns_404(self):
        self.checklist_a.is_active = False
        self.checklist_a.save(update_fields=["is_active"])

        client = Client()
        client.force_login(self.user_member)
        response = client.post(self.complete_url_a, {"note": "Inaktiv"})
        self.assertEqual(response.status_code, 404)

    def test_module_disabled_returns_404(self):
        self.station_a.checklists_enabled = False
        self.station_a.save(update_fields=["checklists_enabled"])

        client = Client()
        client.force_login(self.user_member)
        response = client.post(self.complete_url_a, {"note": "Check"})
        self.assertEqual(response.status_code, 404)


class StationMemberKeysRouteTests(BasePhase1RoutesTestCase):
    """Tests for station_member_keys route (core/secure_views.py)."""

    def setUp(self):
        super().setUp()
        self.keys_url = reverse("station_member_keys")

        # Set up E2EE identity for user_member on station_a
        self.crypto_member = UserCryptoIdentity.objects.create(
            user=self.user_member,
            public_jwk={"kty": "EC", "crv": "P-256", "x": "alpha_x_b64", "y": "alpha_y_b64"},
            wrapped_private_jwk="secret-wrapped-private-key-member-a",
            kdf_salt="test-salt-member-a-1234",
            kdf_iterations=210000,
        )

        # Set up E2EE identity for beta user on station_b
        self.crypto_beta = UserCryptoIdentity.objects.create(
            user=self.user_beta_member,
            public_jwk={"kty": "EC", "crv": "P-256", "x": "beta_x_b64", "y": "beta_y_b64"},
            wrapped_private_jwk="secret-wrapped-private-key-beta",
            kdf_salt="test-salt-beta-5678",
            kdf_iterations=210000,
        )

        # Additional edge case users on station_a:
        # Inactive user
        self.user_inactive = User.objects.create_user(
            username="user_inactive_a", is_active=False
        )
        Membership.objects.create(
            user=self.user_inactive, station=self.station_a, role=Membership.Role.MEMBER, is_active=True
        )
        UserCryptoIdentity.objects.create(
            user=self.user_inactive,
            public_jwk={"kty": "EC", "crv": "P-256", "x": "inact_x", "y": "inact_y"},
            wrapped_private_jwk="secret-inactive-user",
            kdf_salt="salt-inactive",
        )

        # User with inactive membership
        self.user_inactive_mem = User.objects.create_user(
            username="user_inactive_mem_a", is_active=True
        )
        Membership.objects.create(
            user=self.user_inactive_mem,
            station=self.station_a,
            role=Membership.Role.MEMBER,
            is_active=False,
        )
        UserCryptoIdentity.objects.create(
            user=self.user_inactive_mem,
            public_jwk={"kty": "EC", "crv": "P-256", "x": "inact_mem_x", "y": "inact_mem_y"},
            wrapped_private_jwk="secret-inactive-mem",
            kdf_salt="salt-inact-mem",
        )

    def test_positive_path_returns_public_keys_for_active_members_of_own_station(self):
        client = Client()
        client.force_login(self.user_member)

        response = client.get(self.keys_url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data.get("ok"))
        members = data.get("members", [])
        member_ids = {m["user_id"] for m in members}

        # Active members of station_a must be included
        self.assertIn(self.user_member.id, member_ids)
        self.assertIn(self.user_lead.id, member_ids)
        self.assertIn(self.user_admin.id, member_ids)

        # Details for member with crypto identity
        member_entry = next(m for m in members if m["user_id"] == self.user_member.id)
        self.assertTrue(member_entry["has_keys"])
        self.assertEqual(member_entry["public_jwk"], self.crypto_member.public_jwk)
        self.assertIsNotNone(member_entry.get("fingerprint"))

        # Details for member without crypto identity
        lead_entry = next(m for m in members if m["user_id"] == self.user_lead.id)
        self.assertFalse(lead_entry["has_keys"])
        self.assertIsNone(lead_entry["public_jwk"])
        self.assertIsNone(lead_entry["fingerprint"])

    def test_foreign_station_and_inactive_users_are_excluded(self):
        client = Client()
        client.force_login(self.user_member)

        response = client.get(self.keys_url)
        data = response.json()
        member_ids = {m["user_id"] for m in data.get("members", [])}

        # Beta member (Fremdwache) must never appear
        self.assertNotIn(self.user_beta_member.id, member_ids)
        # Inactive user must never appear
        self.assertNotIn(self.user_inactive.id, member_ids)
        # Inactive membership user must never appear
        self.assertNotIn(self.user_inactive_mem.id, member_ids)
        # Auditor is not a content role and must never appear
        self.assertNotIn(self.user_auditor.id, member_ids)

    def test_no_private_keys_or_secrets_in_response(self):
        client = Client()
        client.force_login(self.user_member)

        response = client.get(self.keys_url)
        content_str = response.content.decode("utf-8")

        # Verify no secret keywords or values appear in payload
        self.assertNotIn("wrapped_private_jwk", content_str)
        self.assertNotIn("secret-wrapped-private-key", content_str)
        self.assertNotIn("kdf_salt", content_str)
        self.assertNotIn("kdf_iterations", content_str)
        self.assertNotIn("password", content_str)

        # Verify each member dict has strictly allowed keys
        data = response.json()
        allowed_keys = {"user_id", "label", "public_jwk", "has_keys", "fingerprint"}
        for item in data.get("members", []):
            self.assertTrue(set(item.keys()).issubset(allowed_keys))

    def test_unauthenticated_and_foreign_station_locking(self):
        # 1. Anonymous user redirected to login
        anon_client = Client()
        anon_response = anon_client.get(self.keys_url)
        self.assertEqual(anon_response.status_code, 302)
        self.assertIn(reverse("login"), anon_response.url)

        # 2. Beta member gets only Beta station keys, never Alpha keys
        beta_client = Client()
        beta_client.force_login(self.user_beta_member)
        beta_res = beta_client.get(self.keys_url)
        self.assertEqual(beta_res.status_code, 200)
        beta_member_ids = {m["user_id"] for m in beta_res.json().get("members", [])}
        self.assertIn(self.user_beta_member.id, beta_member_ids)
        self.assertNotIn(self.user_member.id, beta_member_ids)

    def test_role_matrix_content_roles_allowed_auditor_forbidden(self):
        for user in (self.user_member, self.user_cashier, self.user_lead, self.user_admin):
            with self.subTest(role=user.station_memberships.first().role):
                client = Client()
                client.force_login(user)
                response = client.get(self.keys_url)
                self.assertEqual(response.status_code, 200)

        # Auditor is forbidden from content endpoints
        client_auditor = Client()
        client_auditor.force_login(self.user_auditor)
        response_auditor = client_auditor.get(self.keys_url)
        self.assertEqual(response_auditor.status_code, 403)

    def test_post_method_not_allowed(self):
        client = Client()
        client.force_login(self.user_member)
        response = client.post(self.keys_url, {})
        self.assertEqual(response.status_code, 405)

    def test_module_disabled_returns_404(self):
        self.station_a.chat_enabled = False
        self.station_a.save(update_fields=["chat_enabled"])

        client = Client()
        client.force_login(self.user_member)
        response = client.get(self.keys_url)
        self.assertEqual(response.status_code, 404)
