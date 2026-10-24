from pathlib import Path

from django.http import HttpResponse, JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.utils.html import json_script

from .errors import (
    CORRELATION_ID_PATTERN,
    ERROR_CODES,
    ERROR_CODE_FORBIDDEN,
    ERROR_CODE_NOT_FOUND,
    RESPONSE_CORRELATION_HEADER,
    correlation_id_for_request,
    json_error,
)
from .middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware, csp_connect_src


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TemplateSecurityRegressionTests(SimpleTestCase):
    json_templates = (
        "templates/core/chat.html",
        "templates/core/private_chat_thread.html",
        "templates/core/secure_mail_inbox.html",
        "templates/core/secure_mail_detail.html",
        "templates/core/push_settings.html",
    )

    def source(self, relative_path):
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def test_user_controlled_json_uses_django_json_script(self):
        for relative_path in self.json_templates:
            with self.subTest(template=relative_path):
                source = self.source(relative_path)
                self.assertIn("|json_script:", source)
                self.assertNotIn("|safe", source)

    def test_json_script_escapes_script_tag_breakout(self):
        payload = "</script><img src=x onerror=alert(1)>"
        rendered = str(json_script(payload, "hostile-json"))
        self.assertNotIn(payload, rendered)
        self.assertIn("\\u003C/script\\u003E", rendered)
        self.assertIn("\\u003Cimg", rendered)

    def test_secure_mail_has_no_executable_inline_script(self):
        source = self.source("templates/core/secure_mail_inbox.html")
        self.assertNotIn("<script>", source)
        self.assertNotIn("innerHTML", source)

    def test_json_bridge_loads_before_main_application(self):
        source = self.source("templates/base.html")
        bridge = source.index("core/json_data.js")
        application = source.index("core/app.js")
        self.assertLess(bridge, application)

    def test_vorfuehrung_page_has_no_executable_inline_script_or_style(self):
        source = self.source("templates/core/vorfuehrung.html")
        self.assertNotIn("<script>", source)
        self.assertNotIn("|safe", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn(" style=", source)
        self.assertIn("data-demo-deck", source)

    def test_json_bridge_uses_dom_text_not_html_parsing(self):
        source = self.source("core/static/core/json_data.js")
        self.assertNotIn("innerHTML", source)
        self.assertIn("textContent", source)
        self.assertIn("createElement", source)

    def test_mobile_navigation_keeps_four_primary_destinations(self):
        source = self.source("templates/base.html")
        self.assertNotIn('href="{% url \'chat\' %}"', source)
        self.assertIn("'private_chat' in request.resolver_match.url_name", source)

    def test_high_contrast_follows_system_preference(self):
        source = self.source("core/static/core/accessibility.css")
        self.assertIn("prefers-contrast: more", source)
        self.assertIn("#000000", source)
        self.assertNotIn("innerHTML", source)


class MiddlewareSecurityRegressionTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def middleware_for(self, response):
        return SecurityHeadersMiddleware(lambda _request: response)

    def test_csp_keeps_inline_scripts_disabled(self):
        response = self.middleware_for(HttpResponse("ok"))(self.request)
        policy = response.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("'unsafe-inline'", policy)

    def test_csp_connect_src_uses_push_allowlist_not_any_https(self):
        policy = self.middleware_for(HttpResponse("ok"))(self.request).headers[
            "Content-Security-Policy"
        ]
        connect = next(
            part.strip()
            for part in policy.split(";")
            if part.strip().startswith("connect-src")
        )
        tokens = connect.split()
        self.assertEqual(tokens[0], "connect-src")
        self.assertIn("'self'", tokens)
        self.assertNotIn("https:", tokens)
        self.assertIn("https://fcm.googleapis.com", tokens)
        self.assertIn("https://*.push.apple.com", tokens)
        self.assertIn("https://push.apple.com", tokens)

    def test_csp_connect_src_rejects_unlisted_and_malformed_hosts(self):
        self.assertEqual(
            csp_connect_src({"fcm.googleapis.com", ".push.apple.com"}),
            "'self' https://*.push.apple.com https://fcm.googleapis.com https://push.apple.com",
        )
        self.assertEqual(csp_connect_src({"https://evil.example"}), "'self'")
        self.assertEqual(csp_connect_src({"evil example.com; script-src"}), "'self'")
        self.assertEqual(csp_connect_src(set()), "'self'")

    def test_scheme_relative_redirect_is_rejected(self):
        response = HttpResponse(status=302)
        response.headers["Location"] = "//example.org/path"
        secured = self.middleware_for(response)(self.request)
        self.assertEqual(secured.headers["Location"], "/")

    def test_normal_local_redirect_is_preserved(self):
        response = HttpResponse(status=302)
        response.headers["Location"] = "/uebersicht/"
        secured = self.middleware_for(response)(self.request)
        self.assertEqual(secured.headers["Location"], "/uebersicht/")


class ConcurrencyGuardRegressionTests(SimpleTestCase):
    def test_task_board_locks_stable_rows_before_first_insert(self):
        source = (PROJECT_ROOT / "core/task_board.py").read_text(encoding="utf-8")
        self.assertIn("Station.objects.select_for_update()", source)
        self.assertIn("StationTask.objects.select_for_update()", source)


class ErrorHandlerRegressionTests(SimpleTestCase):
    """Regressionstests fuer R-014 (Fehlerseiten und API-Konsistenz)."""

    def _render(self, response_callable):
        request = RequestFactory().get("/")
        middleware = CorrelationIdMiddleware(response_callable)
        response = middleware(request)
        return response

    def test_correlation_id_is_generated_when_missing(self):
        captured = {}

        def view(request):
            captured["cid"] = getattr(request, "correlation_id", None)
            return HttpResponse("ok")

        response = self._render(view)
        self.assertTrue(captured["cid"])
        self.assertEqual(response[RESPONSE_CORRELATION_HEADER], captured["cid"])
        self.assertRegex(captured["cid"], r"^[A-Za-z0-9_\-]{1,128}$")

    def test_correlation_id_honors_safe_header_value(self):
        request = RequestFactory().get("/", HTTP_X_CORRELATION_ID="client-abc-123")
        cid = correlation_id_for_request(request)
        self.assertEqual(cid, "client-abc-123")

    def test_correlation_id_rejects_hostile_header_value(self):
        # Header mit Zeilenumbruch oder Sonderzeichen darf nicht uebernommen
        # werden (Schutz vor Log-Injection und Header-Smuggling).
        for hostile in ("a\nb", "x y", "<script>", "x" * 200):
            request = RequestFactory().get("/", HTTP_X_CORRELATION_ID=hostile)
            cid = correlation_id_for_request(request)
            self.assertNotEqual(cid, hostile)
            self.assertRegex(cid, CORRELATION_ID_PATTERN)

    def test_json_error_has_canonical_shape_and_correlation_id(self):
        def view(request):
            return json_error(request, ERROR_CODE_FORBIDDEN, message="Nein.", status=403)

        response = self._render(view)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        import json
        body = json.loads(response.content)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], ERROR_CODE_FORBIDDEN)
        self.assertEqual(body["error"]["message"], "Nein.")
        self.assertEqual(body["error"]["correlation_id"], response[RESPONSE_CORRELATION_HEADER])

    def test_error_codes_table_is_stable(self):
        self.assertEqual(set(ERROR_CODES), {
            "validation_error", "auth_required", "forbidden",
            "not_found", "rate_limit", "server_error",
            "mfa_required", "mfa_setup_required",
            "conflict", "payload_too_large", "unsupported_media_type",
            "no_active_membership",
        })
        self.assertEqual(ERROR_CODES["no_active_membership"]["status"], 403)
        self.assertEqual(ERROR_CODES["conflict"]["status"], 409)
        self.assertEqual(ERROR_CODES["payload_too_large"]["status"], 413)
        self.assertEqual(ERROR_CODES["unsupported_media_type"]["status"], 415)
        self.assertEqual(ERROR_CODES["forbidden"]["status"], 403)
        self.assertEqual(ERROR_CODES["not_found"]["status"], 404)
        self.assertEqual(ERROR_CODES["rate_limit"]["status"], 429)
        self.assertEqual(ERROR_CODES["validation_error"]["status"], 400)
        self.assertEqual(ERROR_CODES["auth_required"]["status"], 401)
        self.assertEqual(ERROR_CODES["server_error"]["status"], 500)
        self.assertEqual(ERROR_CODES["mfa_required"]["status"], 403)
        self.assertEqual(ERROR_CODES["mfa_setup_required"]["status"], 403)

    def test_api_path_returns_json_for_404(self):
        client = Client(HTTP_ACCEPT="application/json")
        with override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]):
            response = client.get("/api/v1/does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], ERROR_CODE_NOT_FOUND)
        self.assertTrue(body["error"]["correlation_id"])
        self.assertEqual(
            body["error"]["correlation_id"],
            response[RESPONSE_CORRELATION_HEADER],
        )

    def test_html_path_renders_error_template(self):
        client = Client()
        with override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]):
            response = client.get("/nonexistent-page/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, "error-shell", status_code=404)
        self.assertContains(response, "Korrelations-ID", status_code=404)
        self.assertContains(response, response[RESPONSE_CORRELATION_HEADER], status_code=404)

    def test_error_templates_exist_and_extend_base(self):
        for status, name in [
            (400, "errors/400.html"),
            (403, "errors/403.html"),
            (404, "errors/404.html"),
            (429, "errors/429.html"),
            (500, "errors/500.html"),
        ]:
            source = (PROJECT_ROOT / "templates" / name).read_text(encoding="utf-8")
            with self.subTest(template=name):
                self.assertIn('{% extends "base.html" %}', source)
                self.assertIn("error-shell", source)
                self.assertIn("Korrelations-ID", source)

    def test_handler_routes_are_wired(self):
        source = (PROJECT_ROOT / "config" / "urls.py").read_text(encoding="utf-8")
        for handler in ("handler400", "handler403", "handler404", "handler429", "handler500"):
            with self.subTest(handler=handler):
                self.assertIn(f"{handler} =", source)
                self.assertIn("core.views.", source)

    def test_debug_keeps_django_defaults_in_development(self):
        # In DEBUG=true bleiben die Django-Default-Fehlerseiten aktiv.
        # Das ist der dokumentierte Modus; der Test stellt sicher, dass die
        # Handler nur ausserhalb von DEBUG greifen.
        client = Client()
        with override_settings(DEBUG=True):
            response = client.get("/nonexistent-page/")
        # In DEBUG zeigt Django "Page not found" ohne unser Template.
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("error-shell", response.content.decode("utf-8", errors="ignore"))


class CryptoUnlockDialogTests(SimpleTestCase):
    def test_base_template_contains_accessible_dialog(self):
        source = (PROJECT_ROOT / "templates/base.html").read_text(encoding="utf-8")
        self.assertIn('id="crypto-unlock-dialog"', source)
        self.assertIn('aria-labelledby="crypto-unlock-title"', source)
        self.assertIn('aria-describedby="crypto-unlock-description"', source)
        self.assertIn('role="alert"', source)
        self.assertIn('aria-live="assertive"', source)
        self.assertIn('aria-invalid', source)

    def test_app_js_uses_dialog_instead_of_window_prompt(self):
        source = (PROJECT_ROOT / "core/static/core/app.js").read_text(encoding="utf-8")
        self.assertNotIn("window.prompt", source)
        self.assertIn("requestCryptoUnlock", source)

    def test_crypto_unlock_js_uses_show_modal(self):
        source = (PROJECT_ROOT / "core/static/core/crypto_unlock.js").read_text(encoding="utf-8")
        self.assertIn("showModal", source)
        self.assertIn("aria-invalid", source)
        self.assertIn("Escape", source)
        self.assertIn("requestCryptoUnlock", source)
