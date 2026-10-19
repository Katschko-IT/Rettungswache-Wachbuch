"""Die Produktvorführung gehoert auf die oeffentliche Seite, nicht in die App."""
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Membership, Station


class PublicNavTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Nav", slug="nav")
        self.user = User.objects.create_user("nav-user", password="Nav-Test-12345")
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.MEMBER
        )

    def test_guest_sees_demo_link(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/vorfuehrung/"', response.content.decode())

    def test_member_does_not_see_demo_link_in_app(self):
        self.client.force_login(self.user)
        response = self.client.get("/uebergaben/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('href="/vorfuehrung/"', response.content.decode())
