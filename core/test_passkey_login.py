"""Passkey-Anmeldung: gesperrte Konten werden nicht angemeldet."""
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(WEBAUTHN_ENABLED=True, WEBAUTHN_RP_ID="testserver", WEBAUTHN_ORIGIN="http://testserver")
class PasskeyLoginInactiveUserTests(TestCase):
    def _post(self, user):
        session = self.client.session
        session["webauthn_login_challenge"] = "challenge"
        session.save()
        with patch("core.account_views.verify_authentication", return_value=user):
            return self.client.post(
                reverse("passkey_login_verify"),
                data=json.dumps({"credential": {"id": "x"}}),
                content_type="application/json",
            )

    def test_inactive_account_is_refused(self):
        user = User.objects.create_user("gesperrt", password="ein-langes-Passwort-42", is_active=False)
        response = self._post(user)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_active_account_is_logged_in(self):
        user = User.objects.create_user("aktiv", password="ein-langes-Passwort-42")
        response = self._post(user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
