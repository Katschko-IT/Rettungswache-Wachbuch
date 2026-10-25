"""Impressum, Datenschutz-Information und 2FA-Pflicht aus dem Einrichtungsassistenten."""
from __future__ import annotations

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.mfa import mfa_required
from core.models import AuditEvent, Membership, Station, TotpDevice
from core.privacy_models import DataProtectionOfficer
from core.site_profile import SiteProfile
from core.test_argon_remediation import setup_payload

TOKEN = "SITE-PROFILE-TEST-CODE"


def public_payload(**overrides):
    data = setup_payload(
        public_site="on",
        operator_name="DRK Kreisverband Musterstadt e. V.",
        operator_represented_by="Erika Mustermann (Vorstand)",
        operator_email="info@drk-musterstadt.example",
        operator_phone="+49 541 000000",
        dpo_name="Max Datenschutz",
        dpo_email="datenschutz@drk-musterstadt.example",
        server_location="germany",
        hosting_provider="Beispiel Hosting GmbH, Nürnberg",
        supervisory_authority="Die Landesbeauftragte für den Datenschutz Niedersachsen",
        mfa_required="on",
    )
    data.update(overrides)
    return data


@override_settings(SETUP_BOOTSTRAP_TOKEN=TOKEN, MFA_REQUIRED=False)
class WizardOperatorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": TOKEN})

    def test_public_site_stores_imprint_privacy_and_2fa(self):
        response = self.client.post(reverse("setup_wizard"), public_payload())
        self.assertRedirects(response, reverse("setup_done"), fetch_redirect_response=False)
        profile = SiteProfile.current()
        self.assertEqual(profile.operator_name, "DRK Kreisverband Musterstadt e. V.")
        self.assertEqual(profile.city, "Osnabrück")  # Anschrift der Wache übernommen
        self.assertEqual(profile.email, "info@drk-musterstadt.example")
        self.assertTrue(profile.public_site)
        self.assertTrue(profile.mfa_required)
        self.assertTrue(mfa_required())
        dpo = DataProtectionOfficer.objects.get()
        self.assertTrue(dpo.publish_in_privacy_notice)
        self.assertEqual(dpo.station, Station.objects.get())
        self.assertContains(self.client.get(reverse("setup_done")), "Zwei-Faktor einrichten")

        imprint = self.client.get(reverse("legal_notice"))
        self.assertContains(imprint, "§ 5 Digitale-Dienste-Gesetz")
        self.assertContains(imprint, "Erika Mustermann (Vorstand)")
        self.assertContains(imprint, "49074 Osnabrück")
        self.assertContains(imprint, 'href="/impressum/"')  # Fußbereich

        privacy = self.client.get(reverse("privacy"))
        self.assertContains(privacy, "DRK Kreisverband Musterstadt e. V.")
        self.assertContains(privacy, "Beispiel Hosting GmbH, Nürnberg")
        self.assertContains(privacy, "Landesbeauftragte für den Datenschutz Niedersachsen")
        self.assertContains(privacy, "Max Datenschutz")
        self.assertNotContains(privacy, "Veröffentlichungsblocker: Technische Information")

    def test_public_site_requires_email_and_address(self):
        response = self.client.post(
            reverse("setup_wizard"),
            public_payload(operator_email="", admin_email="", street="", postal_code="", city=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "eine E-Mail-Adresse Pflicht")
        self.assertContains(response, "vollständige Anschrift Pflicht")
        self.assertFalse(Station.objects.exists())

    def test_own_operator_address_overrides_station_address(self):
        self.client.post(reverse("setup_wizard"), public_payload(
            operator_street="Kreisstraße 1", operator_postal_code="49000", operator_city="Kreisstadt",
        ))
        profile = SiteProfile.current()
        self.assertEqual((profile.street, profile.postal_code, profile.city), ("Kreisstraße 1", "49000", "Kreisstadt"))

    def test_dpo_needs_name_and_email(self):
        response = self.client.post(reverse("setup_wizard"), public_payload(dpo_email=""))
        self.assertContains(response, "Name und E-Mail der/des Datenschutzbeauftragten")
        self.assertFalse(Station.objects.exists())

    def test_internal_site_falls_back_to_station_and_admin(self):
        self.client.post(reverse("setup_wizard"), setup_payload())
        profile = SiteProfile.current()
        self.assertEqual(profile.operator_name, "Rettungswache Teststadt")
        self.assertEqual(profile.email, "admin@example.invalid")
        self.assertFalse(profile.public_site)
        self.assertFalse(profile.mfa_required)
        self.assertFalse(mfa_required())
        self.assertFalse(DataProtectionOfficer.objects.exists())

    def test_domain_defaults_to_public_and_2fa(self):
        with self.settings(ALLOWED_HOSTS=["rwsth.de", "10.42.0.1", "testserver"]):
            public = self.client.get(reverse("setup_wizard"), HTTP_HOST="rwsth.de")
            lan = self.client.get(reverse("setup_wizard"), HTTP_HOST="10.42.0.1")
        self.assertContains(public, 'id="id_public_site" checked')
        self.assertContains(public, 'id="id_mfa_required" checked')
        self.assertNotContains(lan, 'id="id_public_site" checked')


@override_settings(MFA_REQUIRED=False)
class SiteProfileAdminTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW Nord", slug="rw-nord", city="Nordstadt")
        self.admin = User.objects.create_user("chef", password="x-test-pass-123")
        self.member = User.objects.create_user("nfs", password="x-test-pass-123")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.member_ship = Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)

    def test_imprint_without_profile_explains_setup(self):
        response = self.client.get(reverse("legal_notice"))
        self.assertContains(response, "noch kein Impressum hinterlegt")
        self.assertContains(self.client.get(reverse("privacy")), "Veröffentlichungsblocker")

    def test_only_admins_edit_legal_settings(self):
        self.client.force_login(self.member)
        self.assertNotEqual(self.client.get(reverse("legal_settings")).status_code, 200)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("legal_settings"))
        self.assertContains(page, "RW Nord")  # Vorschlag aus der Wache
        response = self.client.post(reverse("legal_settings"), {
            "operator_name": "Rettungsdienst Nord gGmbH", "legal_form": "gGmbH", "represented_by": "A. Leitung",
            "street": "Hafenweg 2", "postal_code": "26000", "city": "Nordstadt", "country": "Deutschland",
            "email": "info@rd-nord.example", "register_entry": "Amtsgericht Nordstadt HRB 1",
            "server_location": "germany", "public_site": "on", "mfa_required": "on",
            "dpo_name": "D. Schutz", "dpo_email": "ds@rd-nord.example",
        })
        self.assertRedirects(response, reverse("legal_settings"), fetch_redirect_response=False)
        profile = SiteProfile.current()
        self.assertEqual(profile.updated_by, self.admin)
        self.assertTrue(mfa_required())
        self.assertEqual(DataProtectionOfficer.objects.get(station=self.station).display_name, "D. Schutz")
        self.assertTrue(AuditEvent.objects.filter(action="legal.updated").exists())
        self.assertContains(self.client.get(reverse("legal_notice")), "Amtsgericht Nordstadt HRB 1")

    def test_public_settings_require_contact(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("legal_settings"), {
            "operator_name": "X", "server_location": "station", "public_site": "on", "country": "Deutschland",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "eine E-Mail-Adresse Pflicht")
        self.assertIsNone(SiteProfile.current())

    def test_required_2fa_redirects_to_setup_with_qr(self):
        SiteProfile.objects.create(operator_name="RW Nord", city="Nordstadt", mfa_required=True)
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("mfa_setup"), fetch_redirect_response=False)
        page = self.client.get(reverse("mfa_setup"))
        self.assertContains(page, "data:image/png;base64,")
        self.assertContains(page, "Google Authenticator")
        self.assertIn("no-store", page["Cache-Control"])
        # "no-referrer" würde Chrome beim Absenden "Origin: null" schicken lassen -> CSRF-Fehler.
        self.assertEqual(page["Referrer-Policy"], "same-origin")

    def test_code_from_scanned_qr_activates_2fa(self):
        import pyotp

        self.client.force_login(self.member)
        page = self.client.get(reverse("mfa_setup"))
        self.assertEqual(self.client.get(reverse("mfa_setup")).context["secret"], page.context["secret"])
        code = pyotp.TOTP(page.context["secret"]).now()
        response = self.client.post(reverse("mfa_setup"), {"token": code})
        self.assertRedirects(response, reverse("mfa_setup"), fetch_redirect_response=False)
        self.assertTrue(TotpDevice.objects.get(user=self.member).is_confirmed)

    def test_admin_resets_lost_authenticator(self):
        TotpDevice.objects.create(user=self.member, secret="x", is_confirmed=True)
        self.client.force_login(self.member)
        url = reverse("membership_mfa_reset", args=[self.member_ship.pk])
        self.assertNotEqual(self.client.post(url).status_code, 302)  # keine Admin-Rolle
        self.assertTrue(TotpDevice.objects.filter(user=self.member).exists())
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("membership_update", args=[self.member_ship.pk])), "Zwei-Faktor zurücksetzen")
        self.assertRedirects(self.client.post(url), reverse("membership_update", args=[self.member_ship.pk]),
                             fetch_redirect_response=False)
        self.assertFalse(TotpDevice.objects.filter(user=self.member).exists())
        self.assertTrue(AuditEvent.objects.filter(action="mfa.reset").exists())
