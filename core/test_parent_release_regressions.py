"""Parent integration regressions: invitation recovery is strictly station-bound."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import EmployeeActivation, Membership, Station
from core.setup_wizard import SetupConflict, create_employee_invite, revoke_activation


class PendingInvitationOwnershipTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Alpha", slug="parent-alpha")
        self.foreign = Station.objects.create(name="Beta", slug="parent-beta")
        self.admin = User.objects.create_user("parent-admin", password=None)
        self.other_admin = User.objects.create_user("parent-other-admin", password=None)
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.other_admin, station=self.foreign, role=Membership.Role.ADMIN)
        self.data = {"username": "pending-parent", "role": Membership.Role.MEMBER}

    def create_revoked_invite(self):
        user, activation, _ = create_employee_invite(
            station=self.station, created_by=self.admin, data=self.data
        )
        revoke_activation(activation)
        return user

    def test_foreign_station_cannot_claim_revoked_pending_account(self):
        user = self.create_revoked_invite()
        with self.assertRaises(SetupConflict):
            create_employee_invite(station=self.foreign, created_by=self.other_admin, data=self.data)
        self.assertFalse(EmployeeActivation.objects.filter(user=user, station=self.foreign).exists())

    def test_unowned_inactive_account_cannot_be_claimed(self):
        user = User.objects.create_user(self.data["username"], password=None, is_active=False)
        with self.assertRaises(SetupConflict):
            create_employee_invite(station=self.station, created_by=self.admin, data=self.data)
        self.assertFalse(EmployeeActivation.objects.filter(user=user).exists())

    def test_foreign_admin_form_rejects_pending_username(self):
        user = self.create_revoked_invite()
        self.client.force_login(self.other_admin)
        response = self.client.post(reverse("team_invite_create"), self.data)
        self.assertIn("username", response.context["form"].errors)
        self.assertFalse(EmployeeActivation.objects.filter(user=user, station=self.foreign).exists())

    def test_own_revoked_invite_can_be_reissued_via_form(self):
        user = self.create_revoked_invite()
        self.client.force_login(self.admin)
        response = self.client.post(reverse("team_invite_create"), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["created_user"].pk, user.pk)
        self.assertEqual(EmployeeActivation.objects.filter(user=user).count(), 2)
