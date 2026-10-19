from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Membership, Station


class PrivacyNavigationTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Test",
            slug="wache-test",
            calendar_enabled=True,
        )
        self.user = User.objects.create_user(
            username="testmember@example.org",
            password="testpassword123",
            first_name="Alex",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )

    def test_anonymous_get_datenschutz_status_200(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/privacy.html")

    def test_public_nav_presence_and_active_state(self):
        # 1. On /datenschutz/
        response_privacy = self.client.get(reverse("privacy"))
        self.assertEqual(response_privacy.status_code, 200)
        self.assertContains(response_privacy, 'class="footer-links"')
        self.assertContains(response_privacy, f'href="{reverse("privacy")}" aria-current="page"')
        self.assertContains(response_privacy, f'href="{reverse("vorfuehrung")}"')
        self.assertNotContains(response_privacy, f'href="{reverse("vorfuehrung")}" aria-current="page"')

        # 2. On /vorfuehrung/
        response_demo = self.client.get(reverse("vorfuehrung"))
        self.assertEqual(response_demo.status_code, 200)
        self.assertContains(response_demo, 'class="footer-links"')
        self.assertContains(response_demo, f'href="{reverse("vorfuehrung")}" aria-current="page"')
        self.assertContains(response_demo, f'href="{reverse("privacy")}"')
        self.assertNotContains(response_demo, f'href="{reverse("privacy")}" aria-current="page"')

        # 3. On /anmelden/ (login)
        response_login = self.client.get(reverse("login"))
        self.assertEqual(response_login.status_code, 200)
        self.assertContains(response_login, 'class="footer-links"')
        self.assertNotContains(response_login, f'href="{reverse("privacy")}" aria-current="page"')
        self.assertNotContains(response_login, f'href="{reverse("vorfuehrung")}" aria-current="page"')

        # 4. On landing page /
        response_landing = self.client.get(reverse("landing"))
        self.assertEqual(response_landing.status_code, 200)
        self.assertContains(response_landing, 'class="footer-links"')

    def test_ten_anchors_present_and_consistent(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="toc"')

        expected_anchors = [
            "verantwortung",
            "verbindungsdaten",
            "demokonten",
            "cookies",
            "hosting",
            "sicherheit",
            "loeschung",
            "rechte",
            "dienstbetrieb",
            "aenderungen",
        ]

        for anchor in expected_anchors:
            # Check TOC link
            self.assertContains(
                response,
                f'href="#{anchor}"',
                msg_prefix=f"TOC link href='#{anchor}' missing in privacy.html",
            )
            # Check target section id
            self.assertContains(
                response,
                f'id="{anchor}"',
                msg_prefix=f"Target section id='{anchor}' missing in privacy.html",
            )

    def test_cookie_facts_truthfulness(self):
        # Default settings test
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, settings.SESSION_COOKIE_NAME)
        self.assertContains(response, settings.CSRF_COOKIE_NAME)
        self.assertContains(response, f"{settings.SESSION_COOKIE_AGE} Sekunden")
        self.assertContains(response, f"{settings.CSRF_COOKIE_AGE} Sekunden")

        # Dynamic setting: SESSION_COOKIE_SECURE=False
        with self.settings(SESSION_COOKIE_SECURE=False):
            res_insecure = self.client.get(reverse("privacy"))
            self.assertContains(
                res_insecure,
                "<li><strong>Secure:</strong> False (Übertragung nicht auf HTTPS beschränkt)</li>",
            )

        # Dynamic setting: SESSION_COOKIE_HTTPONLY=False
        with self.settings(SESSION_COOKIE_HTTPONLY=False):
            res_sess_httponly_false = self.client.get(reverse("privacy"))
            self.assertContains(
                res_sess_httponly_false,
                "<li><strong>HttpOnly:</strong> False (für JavaScript lesbar)</li>",
            )

        # Dynamic setting: CSRF_COOKIE_HTTPONLY=False (critical trap verification)
        with self.settings(CSRF_COOKIE_HTTPONLY=False):
            res_csrf_httponly_false = self.client.get(reverse("privacy"))
            self.assertContains(
                res_csrf_httponly_false,
                "<li><strong>HttpOnly:</strong> False (für JavaScript lesbar)</li>",
            )

        # Dynamic setting: CSRF_COOKIE_HTTPONLY=True
        with self.settings(CSRF_COOKIE_HTTPONLY=True):
            res_csrf_httponly_true = self.client.get(reverse("privacy"))
            self.assertContains(
                res_csrf_httponly_true,
                "<li><strong>HttpOnly:</strong> True (für clientseitige Skripte unzugänglich)</li>",
            )

        # Both insecure: check that Secure: True is completely absent
        with self.settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False):
            res_both_insecure = self.client.get(reverse("privacy"))
            self.assertNotContains(res_both_insecure, "Secure:</strong> True")

        # Dynamic setting: CSRF_USE_SESSIONS=True (no separate CSRF cookie)
        with self.settings(CSRF_USE_SESSIONS=True):
            res_csrf_sessions = self.client.get(reverse("privacy"))
            self.assertContains(res_csrf_sessions, "CSRF_USE_SESSIONS=True")
            self.assertContains(res_csrf_sessions, "kein separates CSRF-Cookie")
            self.assertNotContains(res_csrf_sessions, f"{settings.CSRF_COOKIE_NAME} (Name:")

        # Dynamic setting: SESSION_EXPIRE_AT_BROWSER_CLOSE=True
        with self.settings(SESSION_EXPIRE_AT_BROWSER_CLOSE=True):
            res_browser_close = self.client.get(reverse("privacy"))
            self.assertContains(res_browser_close, "SESSION_EXPIRE_AT_BROWSER_CLOSE=True")
            self.assertContains(res_browser_close, "Sitzungscookie ohne persistentes Ablaufdatum")
            self.assertContains(res_browser_close, "Browser-Sitzungswiederherstellung")

        # Exact custom seconds
        with self.settings(SESSION_COOKIE_AGE=7201, CSRF_COOKIE_AGE=172801):
            res_custom_age = self.client.get(reverse("privacy"))
            self.assertContains(res_custom_age, "7201 Sekunden")
            self.assertContains(res_custom_age, "172801 Sekunden")
            self.assertNotContains(res_custom_age, "(2 Stunden)")
            self.assertNotContains(res_custom_age, "(2 Tage)")

    def test_no_unsafe_rendering(self):
        with self.settings(
            SESSION_COOKIE_NAME='<script>alert("xss")</script>',
            SESSION_COOKIE_SAMESITE='"><svg onload=alert(1)>',
        ):
            response = self.client.get(reverse("privacy"))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, '<script>alert("xss")</script>')
            self.assertNotContains(response, '"><svg onload=alert(1)>')
            self.assertContains(response, "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;")

    def test_unset_samesite_is_not_claimed_as_an_attribute(self):
        with self.settings(SESSION_COOKIE_SAMESITE=False, CSRF_COOKIE_SAMESITE=None):
            response = self.client.get(reverse("privacy"))
            self.assertContains(response, "nicht gesetzt (Browserstandard)", count=2)
            self.assertNotContains(response, "SameSite=False")
            self.assertNotContains(response, "SameSite=None")

    def test_demo_status_and_unverified_operational_claims(self):
        with self.settings(DEMO_MODE=False):
            response = self.client.get(reverse("privacy"))
            self.assertContains(response, "nicht im Demo-Modus konfiguriert")
        with self.settings(DEMO_MODE=True):
            response = self.client.get(reverse("privacy"))
            self.assertContains(response, "im Demo-Modus konfiguriert")
            self.assertContains(response, "allein garantiert keinen fiktiven Datenbestand")
        self.assertContains(response, "noch nicht nachgewiesen")
        self.assertContains(response, "keine Aussage, dass alle Felder protokolliert werden")
        self.assertNotContains(response, "Rechenzentren in Deutschland")
        self.assertContains(response, "Art. 77 DSGVO")

    def test_unsafe_method_is_rejected(self):
        self.assertEqual(self.client.post(reverse("privacy")).status_code, 405)

    def test_blocker_warning_always_visible(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Veröffentlichungsblocker: Technische Information unvollständig bis Betreiberfreigabe",
        )
        self.assertContains(response, 'class="privacy-blocker-warning"')

    def test_authenticated_app_nav_unaffected(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        # Authenticated app-nav has 4 items
        self.assertContains(response, 'class="app-nav"')
        self.assertContains(response, '<span>Übersicht</span>')
        self.assertContains(response, '<span>Übergaben')
        self.assertContains(response, '<span>Kalender</span>')
        self.assertContains(response, '<span>Mehr</span>')

        # App nav does not contain privacy link
        self.assertNotContains(response, f'class="app-nav" aria-label="Hauptnavigation">\n      <div class="nav-inner">\n        <a href="{reverse("privacy")}"')

        # Public nav is also present in header for authenticated users
        self.assertContains(response, 'class="footer-links"')
        self.assertContains(response, f'href="{reverse("privacy")}"')
