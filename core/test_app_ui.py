"""Tests für die gemeinsame App-UI-Designschicht der Wachwerk-Unterseiten.

Prüfen das Laden der Base-Shell (Bootstrap lokal, dann app.css, dann die neue
Schicht app-ui.css zuletzt), die ``ww-app``-Varianten im ``body``, erhaltene
Berechtigungen/Rollen der Navigation und die Schreibsicherheit (CSRF,
LogoutPOST, POST-only-Task-Toggle). Laufen auf ``config.test_settings`` mit der
automatisch angelegten Django-Test-Datenbank; es wird keine bestehende DB
angefasst. Keine Netzwerkzugriffe.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Membership, Station

CSS_DIR = Path(settings.BASE_DIR) / "core" / "static" / "core"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class AppUiBaseShellTests(TestCase):
    """Laden, Reihenfolge und Body-Varianten der Base-Shell."""

    def setUp(self):
        self.station = Station.objects.create(
            name="Design-Wache",
            slug="design-wache",
            tasks_enabled=True,
            calendar_enabled=True,
        )
        self.user = User.objects.create_user(
            username="design-member", password="test-password"
        )
        Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )

    def test_stylesheets_load_bootstrap_then_app_then_app_ui(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard")).content.decode("utf-8")

        bootstrap = html.find("core/vendor/bootstrap/bootstrap.min.css")
        app_css = html.find("core/app.css")
        accessibility = html.find("core/accessibility.css")
        crypto = html.find("core/crypto_unlock.css")
        app_ui = html.find("core/app-ui.css")

        for index in (bootstrap, app_css, accessibility, crypto, app_ui):
            self.assertNotEqual(index, -1, "Stylesheet fehlt im <head>")
        self.assertLess(bootstrap, app_css, "Bootstrap muss vor app.css liegen")
        self.assertLess(app_css, app_ui, "app-ui.css muss nach app.css liegen")
        self.assertLess(accessibility, app_ui, "app-ui.css muss nach accessibility.css liegen")
        self.assertLess(crypto, app_ui, "app-ui.css muss nach crypto_unlock.css liegen")
        # app-ui.css ist die letzte allgemeine Designschicht (vor page-spezifisch).
        self.assertLess(app_ui, html.find("</head>"))
        self.assertNotIn("core/app-ui.css", self._landing_html())

    def test_authenticated_body_uses_ww_app_auth(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard")).content.decode("utf-8")
        self.assertIn("ww-app", html)
        self.assertIn("ww-app--auth", html)
        self.assertNotIn("ww-app--anon", html)
        # Bestehende Verträge bleiben erhalten.
        self.assertIn("has-app-nav", html)
        self.assertIn("profile-", html)

    def test_anonymous_body_uses_ww_app_anon(self):
        self.client.logout()
        html = self.client.get(reverse("login")).content.decode("utf-8")
        self.assertIn("ww-app", html)
        self.assertIn("ww-app--anon", html)
        self.assertNotIn("ww-app--auth", html)

    def test_error_page_keeps_ww_app_and_page_error(self):
        self.client.logout()
        response = self.client.get("/diese-seite-gibt-es-nicht/")
        self.assertEqual(response.status_code, 404)
        html = response.content.decode("utf-8")
        self.assertIn("ww-app", html)
        self.assertIn("ww-app--anon", html)
        self.assertIn("page-error", html)

    def _landing_html(self) -> str:
        return self.client.get(reverse("landing")).content.decode("utf-8")


class AppUiStylesheetTests(TestCase):
    """Inhaltliche Leitplanken der neuen Designschicht (keine externen Quellen)."""

    def setUp(self):
        self.css = _read(CSS_DIR / "app-ui.css")

    def test_css_is_local_without_imports_or_external_urls(self):
        self.assertNotIn("@import", self.css)
        self.assertNotIn("http://", self.css)
        self.assertNotIn("https://", self.css)
        for cdn_host in ("cdn.jsdelivr", "cdnjs", "unpkg", "googleapis"):
            self.assertNotIn(cdn_host, self.css.lower())
        self.assertNotIn("innerHTML", self.css)

    def test_css_defines_shared_tokens(self):
        for token in (
            "--ww-radius: 14px",
            "--ww-container: 1120px",
            "--ww-touch: 48px",
            '"Source Sans 3"',
        ):
            self.assertIn(token, self.css)

    def test_css_scopes_to_ww_app_with_auth_variants(self):
        self.assertIn(".ww-app", self.css)
        self.assertIn(".ww-app--auth", self.css)
        self.assertIn(".ww-app--anon", self.css)

    def test_css_respects_accessibility_baseline(self):
        self.assertIn("prefers-reduced-motion: reduce", self.css)
        self.assertIn("prefers-contrast: more", self.css)
        self.assertIn("focus-visible", self.css)

    def test_css_guarantees_hidden_wins_over_flex(self):
        # Das [hidden]-Attribut muss jeden display:flex-Sonderfall überstimmen.
        self.assertIn("[hidden] { display: none !important; }", self.css)
        self.assertIn(".ww-app .install-close", self.css)

    def test_css_preserves_taskboard_and_highcontrast_semantics(self):
        # Die semantischen Bandfarben werden nicht überschrieben.
        for band_color in ("#16a34a", "#b45309", "#0d47a1"):
            self.assertNotIn(f"--band: {band_color}", self.css.replace(" ", " "))


class AppUiTemplateContractTests(TestCase):
    """base.html bleibt CSP-sicher und behält die Sicherheitsverträge."""

    def setUp(self):
        self.source = _read(Path(settings.BASE_DIR) / "templates" / "base.html")

    def test_base_template_has_no_inline_sinks(self):
        self.assertNotIn("|safe", self.source)
        self.assertNotIn("innerHTML", self.source)
        self.assertNotIn(" style=", self.source)
        self.assertNotIn("<script>", self.source)
        self.assertNotIn("http://", self.source)
        self.assertNotIn("https://", self.source)

    def test_base_keeps_csrf_logout_post(self):
        self.assertIn('method="post" action="{% url \'logout\' %}"', self.source)
        self.assertIn("data-clear-cache-on-submit", self.source)
        self.assertIn("{% csrf_token %}", self.source)

    def test_base_keeps_mobile_navigation_four_destinations(self):
        # Regressionsvertrag aus core/test_security_regressions.py bleibt gültig.
        self.assertNotIn("href=\"{% url 'chat' %}\"", self.source)
        self.assertIn("'private_chat' in request.resolver_match.url_name", self.source)

    def test_install_banner_has_real_dismiss_and_x_close(self):
        # Banner startet verborgen (JS des Parents beendet den Zustand).
        self.assertIn('class="install-banner" data-install-banner hidden', self.source)
        # Keine automatische Installationswerbung in der App, kein Später-Reminder.
        self.assertIn("data-install-manual-only", self.source)
        self.assertNotIn(">Später</button>", self.source)
        # Zusätzliches echtes X als type=button mit Barrierefrei-Label.
        self.assertIn(
            'type="button" class="button secondary install-close" data-install-dismiss '
            'aria-label="Installationshinweis schließen"',
            self.source,
        )
        self.assertEqual(self.source.count("data-install-dismiss"), 1)


class AppUiNavigationPermissionTests(TestCase):
    """Rollen- und Modulgrenzen der Navigation bleiben unverändert."""

    def _member_station(self, role, **flags):
        station = Station.objects.create(
            name=f"Wache {role}", slug=f"wache-{role}", **flags
        )
        user = User.objects.create_user(
            username=f"user-{role}", password="test-password"
        )
        Membership.objects.create(user=user, station=station, role=role)
        return user

    def test_four_destinations_present_for_member(self):
        user = self._member_station(
            Membership.Role.MEMBER, calendar_enabled=True
        )
        self.client.force_login(user)
        html = self.client.get(reverse("dashboard")).content.decode("utf-8")
        self.assertIn(f'href="{reverse("dashboard")}"', html)
        self.assertIn(f'href="{reverse("handover_list")}"', html)
        self.assertIn(f'href="{reverse("calendar")}"', html)
        self.assertIn(f'href="{reverse("more")}"', html)

    def test_calendar_destination_only_when_module_enabled(self):
        user = self._member_station(
            Membership.Role.MEMBER, calendar_enabled=False
        )
        self.client.force_login(user)
        html = self.client.get(reverse("dashboard")).content.decode("utf-8")
        self.assertNotIn(f'href="{reverse("calendar")}"', html)

    def test_auditor_navigation_shows_only_audit(self):
        user = self._member_station(Membership.Role.AUDITOR)
        self.client.force_login(user)
        html = self.client.get(reverse("audit_log")).content.decode("utf-8")
        self.assertIn("<span>Audit</span>", html)
        self.assertNotIn(">Übersicht<", html)

    def test_admin_sees_team_management_link(self):
        user = self._member_station(Membership.Role.ADMIN)
        self.client.force_login(user)
        html = self.client.get(reverse("more")).content.decode("utf-8")
        self.assertIn(f'href="{reverse("team")}"', html)


class AppUiWriteSafetyTests(TestCase):
    """Schreibende Endpunkte bleiben CSRF-gebunden und POST-only."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="test-password"
        )
        self.station = Station.objects.create(
            name="Schreib-Wache", slug="schreib-wache", tasks_enabled=True
        )
        Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )

    def test_logout_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        # Erst ein GET holt das CSRF-Cookie (Logout-Formular im Base-Template).
        csrf_client.get(reverse("dashboard"))
        blocked = csrf_client.post(reverse("logout"))
        self.assertEqual(blocked.status_code, 403)

    def test_logout_succeeds_with_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        csrf_client.get(reverse("dashboard"))
        token = csrf_client.cookies["rwsth_csrf"].value
        response = csrf_client.post(reverse("logout"), {"csrfmiddlewaretoken": token})
        self.assertIn(response.status_code, (302, 303))
        self.assertNotIn("_auth_user_id", csrf_client.session)

    def test_task_toggle_is_post_only(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("task_toggle", args=[1]))
        self.assertEqual(response.status_code, 405)

    def test_task_toggle_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        blocked = csrf_client.post(reverse("task_toggle", args=[1]), {"erledigt": "1"})
        self.assertEqual(blocked.status_code, 403)
