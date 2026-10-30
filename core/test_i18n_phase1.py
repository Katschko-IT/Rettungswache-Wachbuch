"""Tests fuer das I18N-Fundament (Etappe i18n-1A)."""

import ast
import gettext
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from core.errors import label_for_code
from core.models import Membership, Station, UserProfile


class I18nFoundationTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache 1",
            slug="wache-1",
        )
        self.user = User.objects.create_user(
            username="sani@example.org",
            password="test-password-12345",
            first_name="Sam",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )

    def test_settings_contract(self):
        """1. Settings-Vertrag: LANGUAGE_CODE == 'de', LANGUAGES, LOCALE_PATHS, Middleware."""
        self.assertEqual(settings.LANGUAGE_CODE, "de")
        lang_codes = [code for code, _ in settings.LANGUAGES]
        self.assertIn("de", lang_codes)
        self.assertIn("en", lang_codes)
        self.assertTrue(
            any("locale" in str(path) for path in settings.LOCALE_PATHS),
            "LOCALE_PATHS muss 'locale' enthalten.",
        )
        middleware = list(settings.MIDDLEWARE)
        session_idx = middleware.index("django.contrib.sessions.middleware.SessionMiddleware")
        locale_idx = middleware.index("django.middleware.locale.LocaleMiddleware")
        common_idx = middleware.index("django.middleware.common.CommonMiddleware")
        self.assertEqual(
            locale_idx,
            session_idx + 1,
            "LocaleMiddleware muss direkt nach SessionMiddleware stehen.",
        )
        self.assertEqual(
            common_idx,
            locale_idx + 1,
            "CommonMiddleware muss direkt nach LocaleMiddleware stehen.",
        )

    def test_mo_files_load_and_contain_core_translations(self):
        """2. .mo laedt: GNUTranslations oeffnet beide Dateien; 'Anmelden' -> 'Sign in' vorhanden."""
        de_mo = settings.BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "django.mo"
        en_mo = settings.BASE_DIR / "locale" / "en" / "LC_MESSAGES" / "django.mo"
        self.assertTrue(de_mo.is_file(), f"{de_mo} fehlt.")
        self.assertTrue(en_mo.is_file(), f"{en_mo} fehlt.")

        with de_mo.open("rb") as fp:
            de_trans = gettext.GNUTranslations(fp)
        with en_mo.open("rb") as fp:
            en_trans = gettext.GNUTranslations(fp)

        self.assertIsNotNone(de_trans)
        self.assertIsNotNone(en_trans)
        self.assertEqual(en_trans.gettext("Anmelden"), "Sign in")
        self.assertEqual(de_trans.gettext("Anmelden"), "Anmelden")

    def test_login_page_language_cookie_and_accept_language(self):
        """3. Login-Seite: Cookie wachbuch_language=en -> Englisch; ohne Cookie -> Deutsch."""
        client_en = Client()
        client_en.cookies["wachbuch_language"] = "en"
        response_en = client_en.get(reverse("login"))
        self.assertEqual(response_en.status_code, 200)
        self.assertContains(response_en, 'lang="en"')
        self.assertContains(response_en, "Sign in")

        client_de = Client()
        response_de = client_de.get(reverse("login"), HTTP_ACCEPT_LANGUAGE="de")
        self.assertEqual(response_de.status_code, 200)
        self.assertContains(response_de, 'lang="de"')
        self.assertContains(response_de, "Anmelden")

    def test_fallback_unsupported_language_and_unknown_msgid(self):
        """4. Fallback: Accept-Language: fr -> Deutsch; unbekannter msgid bleibt deutsch/unveraendert."""
        client_fr = Client()
        response_fr = client_fr.get(reverse("login"), HTTP_ACCEPT_LANGUAGE="fr")
        self.assertEqual(response_fr.status_code, 200)
        self.assertContains(response_fr, 'lang="de"')
        self.assertContains(response_fr, "Anmelden")

        with translation.override("en"):
            unbekannt = "Unbekannter Text der nicht im Katalog existiert"
            self.assertEqual(translation.gettext(unbekannt), unbekannt)

    def test_language_switch_endpoint(self):
        """5. Sprachwechsel: POST mit CSRF setzt Cookie & redirectet; GET -> 405; ohne CSRF -> 403; open redirect abgewiesen."""
        strict_client = Client(enforce_csrf_checks=True)

        # GET -> 405
        get_res = strict_client.get(reverse("set_language"))
        self.assertEqual(get_res.status_code, 405)

        # POST ohne CSRF -> 403
        no_csrf_res = strict_client.post(reverse("set_language"), {"language": "en"})
        self.assertEqual(no_csrf_res.status_code, 403)

        # CSRF-Token holen via GET
        login_res = strict_client.get(reverse("login"))
        csrf_token = login_res.cookies["rwsth_csrf"].value

        # POST mit CSRF -> Cookie gesetzt und Redirect
        post_res = strict_client.post(
            reverse("set_language"),
            {"language": "en", "next": "/uebergaben/"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(post_res.status_code, 302)
        self.assertEqual(post_res["Location"], "/uebergaben/")
        self.assertIn("wachbuch_language", post_res.cookies)
        self.assertEqual(post_res.cookies["wachbuch_language"].value, "en")

        # Open Redirect: next=https://evil.example/ -> wird auf '/' verworfen
        evil_res = strict_client.post(
            reverse("set_language"),
            {"language": "de", "next": "https://evil.example/"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(evil_res.status_code, 302)
        self.assertEqual(evil_res["Location"], "/")

        # Ungueltige Sprache -> 400
        invalid_res = strict_client.post(
            reverse("set_language"),
            {"language": "klingon"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(invalid_res.status_code, 400)

    @override_settings(
        LANGUAGE_COOKIE_SECURE=True,
        LANGUAGE_COOKIE_HTTPONLY=True,
        LANGUAGE_COOKIE_SAMESITE="Lax",
        LANGUAGE_COOKIE_AGE=31_536_000,
    )
    def test_language_cookie_flags_are_hardened(self):
        """5b. Sprachcookie: HttpOnly, SameSite=Lax, Secure, Path=/, ein Jahr; Content-Language/Vary gesetzt."""
        client = Client(enforce_csrf_checks=True)
        csrf_token = client.get(reverse("login")).cookies["rwsth_csrf"].value
        response = client.post(
            reverse("set_language"),
            {"language": "en"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        cookie = response.cookies["wachbuch_language"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["path"], "/")
        self.assertEqual(cookie["max-age"], 31_536_000)
        self.assertEqual(response["Content-Language"], "en")
        self.assertIn("Cookie", response["Vary"])

    def test_language_switch_preserves_session(self):
        """6. Sprachwechsel veraendert die Session nicht: Session-Key und Items identisch."""
        client = Client()
        client.force_login(self.user)
        # Dashboard aufrufen um Session vollstaendig zu etablieren
        client.get(reverse("dashboard"))

        session_key_before = client.session.session_key
        session_items_before = dict(client.session.items())

        response = client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("dashboard")},
        )
        self.assertEqual(response.status_code, 302)

        client.get(reverse("dashboard"))
        self.assertEqual(client.session.session_key, session_key_before)
        self.assertEqual(dict(client.session.items()), session_items_before)
        self.assertEqual(reverse("handover_list"), "/uebergaben/")

    def test_user_profile_language_preference_on_login(self):
        """7. Praeferenz: profile.language='en', Login ohne Cookie -> englisch; explizites de bleibt erhalten."""
        profile = UserProfile.for_user(self.user)
        profile.language = "en"
        profile.save()

        # Login ohne Sprachcookie -> Sprache wird uebernommen
        client = Client()
        login_res = client.post(
            reverse("login"),
            {"username": "sani@example.org", "password": "test-password-12345"},
        )
        self.assertEqual(login_res.status_code, 302)
        self.assertIn("wachbuch_language", login_res.cookies)
        self.assertEqual(login_res.cookies["wachbuch_language"].value, "en")

        # Explizites Cookie 'de' vorhanden -> darf nicht ueberschrieben werden
        client_with_de = Client()
        client_with_de.cookies["wachbuch_language"] = "de"
        login_de_res = client_with_de.post(
            reverse("login"),
            {"username": "sani@example.org", "password": "test-password-12345"},
        )
        self.assertEqual(login_de_res.status_code, 302)
        cookie_header = login_de_res.cookies.get("wachbuch_language")
        # Entweder kein neues Set-Cookie oder weiterhin 'de'
        if cookie_header:
            self.assertEqual(cookie_header.value, "de")

    def test_label_for_code_translations(self):
        """8. label_for_code('validation_error') liefert unter en Englisch, unter de 'Ungültige Anfrage.'."""
        with translation.override("en"):
            self.assertEqual(label_for_code("validation_error"), "Invalid request.")
        with translation.override("de"):
            self.assertEqual(label_for_code("validation_error"), "Ungültige Anfrage.")

    def test_no_ascii_transliterations_in_errors_and_waste_sync(self):
        """9. Keine ASCII-Umschrift mehr: 'Ungueltige', 'Muellkalender', 'ungueltig', 'Groessenlimit' nicht in Fehlermeldungen."""
        errors_path = settings.BASE_DIR / "core" / "errors.py"
        errors_content = errors_path.read_text(encoding="utf-8")
        self.assertNotIn("Ungueltige", errors_content)

        waste_sync_path = settings.BASE_DIR / "core" / "waste_sync.py"
        tree = ast.parse(waste_sync_path.read_text(encoding="utf-8"))

        value_error_messages = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                func_name = getattr(node.exc.func, "id", None)
                if func_name == "ValueError" and node.exc.args:
                    first_arg = node.exc.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        value_error_messages.append(first_arg.value)
                    elif isinstance(first_arg, ast.JoinedStr):
                        value_error_messages.append(
                            "".join(
                                part.value
                                for part in first_arg.values
                                if isinstance(part, ast.Constant)
                            )
                        )

        self.assertTrue(len(value_error_messages) > 0)
        forbidden_substrings = (
            "Muellkalender",
            "ungueltig",
            "Groessenlimit",
            "aufgeloest",
            "ueberschreitet",
        )
        for msg in value_error_messages:
            for forbidden in forbidden_substrings:
                self.assertNotIn(
                    forbidden,
                    msg,
                    f"ASCII-Umschrift '{forbidden}' in ValueError gefunden: {msg}",
                )

    def test_login_page_page_own_english_texts(self):
        """10. Login-Seite enthaelt unter en eigene englische Texte und unter de deutsche."""
        client_en = Client()
        client_en.cookies["wachbuch_language"] = "en"
        response_en = client_en.get(reverse("login"))
        self.assertEqual(response_en.status_code, 200)
        self.assertContains(response_en, "Personal access")
        self.assertContains(response_en, "Sign in")
        self.assertContains(response_en, "Privacy and cookie information")

        client_de = Client()
        client_de.cookies["wachbuch_language"] = "de"
        response_de = client_de.get(reverse("login"))
        self.assertEqual(response_de.status_code, 200)
        self.assertContains(response_de, "Persönlicher Zugang")
        self.assertContains(response_de, "Anmelden")
        self.assertContains(response_de, "Datenschutz- und Cookie-Informationen")

    def test_form_errors_in_english(self):
        """11. Formularfehler auf Englisch: Login und SetupWizard liefern englische Pflichtfeldmeldungen."""
        client_en = Client()
        client_en.cookies["wachbuch_language"] = "en"
        response_login = client_en.post(reverse("login"), {})
        self.assertEqual(response_login.status_code, 200)
        self.assertContains(response_login, "This field is required.")
        self.assertNotContains(response_login, "Dieses Feld ist ein Pflichtfeld.")

        with translation.override("en"):
            from core.forms import SetupWizardForm

            setup_form = SetupWizardForm({})
            self.assertFalse(setup_form.is_valid())
            self.assertIn("station_name", setup_form.errors)
            self.assertEqual(
                setup_form.errors["station_name"],
                ["This field is required."],
            )

    def test_error_pages_in_english_and_german(self):
        """12. Fehlerseiten: 404 mit Sprachcookie en liefert englische Texte, de liefert deutsche."""
        client_en = Client()
        client_en.cookies["wachbuch_language"] = "en"
        res_404_en = client_en.get("/nicht-vorhandene-seite-404/")
        self.assertEqual(res_404_en.status_code, 404)
        self.assertContains(res_404_en, "Not found.", status_code=404)
        self.assertContains(res_404_en, "The requested page does not exist or has been moved.", status_code=404)
        self.assertContains(res_404_en, "To home page", status_code=404)
        self.assertContains(
            res_404_en,
            "Need help? Contact the management or administrator of your station and give them the correlation ID.",
            status_code=404,
        )
        self.assertNotContains(res_404_en, "logbook support", status_code=404)

        client_de = Client()
        client_de.cookies["wachbuch_language"] = "de"
        res_404_de = client_de.get("/nicht-vorhandene-seite-404/")
        self.assertEqual(res_404_de.status_code, 404)
        self.assertContains(res_404_de, "Nicht gefunden.", status_code=404)
        self.assertContains(res_404_de, "Die angeforderte Seite existiert nicht oder wurde verschoben.", status_code=404)
        self.assertContains(res_404_de, "Zur Startseite", status_code=404)

    def test_catalog_parity(self):
        """13. Katalogparitaet: de und en haben dieselben msgids, en hat keine leeren/fuzzy msgstrs."""
        from scripts.i18n_catalog import parse_po

        de_entries = parse_po(settings.BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "django.po")
        en_entries = parse_po(settings.BASE_DIR / "locale" / "en" / "LC_MESSAGES" / "django.po")

        de_ids = {e["msgid"] for e in de_entries if e["msgid"]}
        en_ids = {e["msgid"] for e in en_entries if e["msgid"]}
        self.assertEqual(de_ids, en_ids, "msgids in de und en Katalogen muessen identisch sein.")

        for e in en_entries:
            if e["msgid"]:
                self.assertTrue(
                    bool(e["msgstr"].strip()),
                    f"Leerer msgstr im englischen Katalog bei: {e['msgid']}",
                )
                self.assertFalse(
                    e["fuzzy"],
                    f"Fuzzy msgstr im englischen Katalog bei: {e['msgid']}",
                )

    def test_no_mixed_content_on_english_login_page(self):
        """14. Keine Mischseite: gerenderte englische Login-Seite enthaelt keine deutschen Schluesselmarker."""
        client_en = Client()
        client_en.cookies["wachbuch_language"] = "en"
        response = client_en.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        german_markers = (
            "Persönlicher Zugang",
            "Datenschutz- und Cookie-Informationen",
            "Neues Konto registrieren",
            "Passkey verwenden",
        )
        for marker in german_markers:
            self.assertNotIn(
                marker,
                content,
                f"Deutscher Marker '{marker}' fälschlicherweise auf englischer Login-Seite gefunden.",
            )

    def test_language_switch_without_login_on_setup(self):
        """15. Sprachwechsel ohne Login auf /setup/: Cookie gesetzt, /setup/ laedt auf Englisch ohne 500."""
        with self.settings(SETUP_BOOTSTRAP_TOKEN="bootstrap-token-test-123"):
            client = Client(enforce_csrf_checks=True)
            login_res = client.get(reverse("login"))
            csrf_token = login_res.cookies["rwsth_csrf"].value

            post_res = client.post(
                reverse("set_language"),
                {"language": "en", "next": reverse("setup_wizard")},
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertEqual(post_res.status_code, 302)
            self.assertEqual(post_res["Location"], reverse("setup_wizard"))
            self.assertEqual(post_res.cookies["wachbuch_language"].value, "en")

            setup_res = client.get(reverse("setup_wizard"))
            self.assertIn(setup_res.status_code, (200, 302))
            self.assertNotEqual(setup_res.status_code, 500)
            if setup_res.status_code == 200:
                self.assertContains(setup_res, 'lang="en"')
                self.assertContains(setup_res, "Initial setup")

class I18nContractHardeningTests(TestCase):
    """Zusaetzliche Vertragstests: URLs, Session, Praeferenz, Kataloge, Auswahl-Labels."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Vertrag", slug="wache-vertrag")
        self.user = User.objects.create_user(
            username="vertrag@example.org", password="test-password-12345"
        )
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.ADMIN
        )

    def test_urls_keep_german_slugs_without_language_prefix(self):
        self.assertEqual(reverse("login"), "/anmelden/")
        self.assertEqual(reverse("handover_list"), "/uebergaben/")
        self.assertEqual(reverse("dashboard"), "/uebersicht/")
        self.assertEqual(reverse("qr_login_wait"), "/anmelden/qr/")
        self.assertEqual(reverse("set_language"), "/sprache/")
        for url in (reverse("login"), reverse("handover_list"), reverse("dashboard")):
            self.assertFalse(url.startswith("/de/") or url.startswith("/en/"), url)

    def test_switch_endpoint_rejects_get_and_keeps_profile_on_invalid_input(self):
        profile = UserProfile.for_user(self.user)
        profile.language = "de"
        profile.save()
        client = Client()
        client.force_login(self.user)
        self.assertEqual(client.get(reverse("set_language")).status_code, 405)
        response = client.post(reverse("set_language"), {"language": "xx"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("wachbuch_language", response.cookies)
        profile.refresh_from_db()
        self.assertEqual(profile.language, "de")

    def test_switch_updates_profile_but_keeps_role_and_session(self):
        client = Client()
        client.force_login(self.user)
        client.get(reverse("dashboard"))
        session_key = client.session.session_key
        response = client.post(
            reverse("set_language"), {"language": "en", "next": reverse("dashboard")}
        )
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.language, "en")
        self.assertEqual(
            Membership.objects.get(user=self.user).role, Membership.Role.ADMIN
        )
        self.assertEqual(client.session.session_key, session_key)
        self.assertIn("_auth_user_id", client.session)
        self.assertEqual(client.get(reverse("dashboard")).status_code, 200)

    def test_vary_header_covers_language_and_session(self):
        response = Client().get(reverse("login"))
        vary = response.headers.get("Vary", "")
        self.assertIn("Accept-Language", vary)
        self.assertIn("Cookie", vary)

    def test_profile_preference_wins_over_accept_language(self):
        profile = UserProfile.for_user(self.user)
        profile.language = "de"
        profile.save()
        client = Client()
        response = client.post(
            reverse("login"),
            {"username": "vertrag@example.org", "password": "test-password-12345"},
            HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies["wachbuch_language"].value, "de")

    def test_german_catalog_is_identity_and_english_has_no_open_placeholders(self):
        from scripts.i18n_catalog import parse_po, validate

        de_path = settings.BASE_DIR / "locale" / "de" / "LC_MESSAGES" / "django.po"
        en_path = settings.BASE_DIR / "locale" / "en" / "LC_MESSAGES" / "django.po"
        de_entries = parse_po(de_path)
        for entry in de_entries:
            if entry["msgid"]:
                self.assertEqual(entry["msgstr"], entry["msgid"], entry["msgid"])
        self.assertEqual(validate(parse_po(en_path), en_path, language="en"), [])

    def test_setup_wizard_profile_choices_are_translated(self):
        from core.forms import SetupWizardForm

        with translation.override("en"):
            field = SetupWizardForm().fields["organization_profile"]
            labels = [str(label) for _, label in field.choices]
        self.assertIn("Rescue service", labels)
        self.assertNotIn("Rettungsdienst", labels)

        with translation.override("de"):
            field = SetupWizardForm().fields["organization_profile"]
            labels = [str(label) for _, label in field.choices]
        self.assertIn("Rettungsdienst", labels)
