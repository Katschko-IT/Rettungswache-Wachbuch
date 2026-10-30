from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.templatetags.static import static
from django.urls import include, path
from django.utils.functional import lazy
from django.views.generic import RedirectView

from core import account_views, community_views, qr_login_views, secure_views
from core.auth_views import PasswordLoginView
from core.views import (
    bad_request,
    healthz,
    mfa_disable,
    mfa_setup,
    mfa_verify,
    offline,
    page_not_found,
    permission_denied,
    legal_notice,
    privacy_notice,
    rate_limited,
    server_error,
    service_worker,
    web_manifest,
)

def admin_login(request, extra_context=None):
    """Django-Admin nur über die normale Anmeldung (mit zweitem Faktor).

    Die eigene Anmeldeseite des Django-Admins kennt weder TOTP noch Passkeys;
    sie würde den zweiten Faktor umgehen.
    """
    from django.contrib.auth.views import redirect_to_login
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import redirect
    from django.urls import reverse

    if request.user.is_authenticated:
        if admin.site.has_permission(request):
            return redirect("admin:index")
        raise PermissionDenied
    return redirect_to_login(reverse("admin:index"), reverse("login"))


admin.site.login = admin_login

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler429 = "core.views.rate_limited"
handler500 = "core.views.server_error"


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    # Browser fragen /favicon.ico ungefragt ab; ohne Route entstehen 404-Logzeilen.
    path("favicon.ico", RedirectView.as_view(url=lazy(static, str)("core/icons/icon-192.png"), permanent=True)),
    path("manifest.webmanifest", web_manifest, name="web_manifest"),
    path("service-worker.js", service_worker, name="service_worker"),
    path("offline/", offline, name="offline"),
    path("datenschutz/", privacy_notice, name="privacy"),
    path("impressum/", legal_notice, name="legal_notice"),
    path("anmelden/", PasswordLoginView.as_view(), name="login"),
    path("registrieren/", community_views.register, name="register"),
    path("konto/", community_views.account_home, name="account_home"),
    path("konto/avatar/<int:user_id>/", community_views.avatar_image, name="avatar_image"),
    path("konto/crypto/", secure_views.crypto_setup, name="crypto_setup"),
    path("konto/crypto/bundle.json", secure_views.crypto_bundle, name="crypto_bundle"),
    path("anmelden/mfa/", mfa_verify, name="mfa_verify"),
    path("anmelden/passkey/optionen/", account_views.passkey_login_options, name="passkey_login_options"),
    path("anmelden/passkey/pruefen/", account_views.passkey_login_verify, name="passkey_login_verify"),
    path("anmelden/mfa/passkey/optionen/", account_views.passkey_mfa_options, name="passkey_mfa_options"),
    path("anmelden/mfa/passkey/pruefen/", account_views.passkey_mfa_verify, name="passkey_mfa_verify"),
    path("konto/mfa/", mfa_setup, name="mfa_setup"),
    path("konto/mfa/deaktivieren/", mfa_disable, name="mfa_disable"),
    path("konto/mfa/passkey/optionen/", account_views.passkey_register_options, name="passkey_register_options"),
    path("konto/mfa/passkey/pruefen/", account_views.passkey_register_verify, name="passkey_register_verify"),
    path("konto/mfa/passkey/<int:pk>/entfernen/", account_views.passkey_delete, name="passkey_delete"),
    path("konto/api/", account_views.api_tokens_manage, name="api_tokens_manage"),
    path("konto/api/mobile-qr.png", account_views.mobile_setup_qr, name="mobile_setup_qr"),
    path("anmelden/qr/", qr_login_views.qr_login_wait, name="qr_login_wait"),
    path("anmelden/qr/start/", qr_login_views.qr_login_start, name="qr_login_start"),
    path("anmelden/qr/eingeben/", qr_login_views.qr_login_manual, name="qr_login_manual"),
    path("anmelden/qr/<uuid:login_id>/", qr_login_views.qr_login_wait, name="qr_login_wait_id"),
    path("anmelden/qr/<uuid:login_id>/status/", qr_login_views.qr_login_status, name="qr_login_status"),
    path("anmelden/qr/<uuid:login_id>/bestaetigen/", qr_login_views.qr_login_confirm, name="qr_login_confirm"),
    path("anmelden/qr/<uuid:login_id>/bestaetigen/passkey/optionen/", qr_login_views.qr_login_passkey_options, name="qr_login_passkey_options"),
    path("anmelden/qr/<uuid:login_id>/bestaetigen/passkey/pruefen/", qr_login_views.qr_login_passkey_verify, name="qr_login_passkey_verify"),
    path("anmelden/qr/<uuid:login_id>/ablehnen/", qr_login_views.qr_login_deny, name="qr_login_deny"),
    path("anmelden/qr/<uuid:login_id>/exchange/", qr_login_views.qr_login_exchange, name="qr_login_exchange"),
    path("abmelden/", qr_login_views.QrLogoutView.as_view(), name="logout"),
    path("django-admin/", admin.site.urls),
    path("api/v1/", include("core.api.urls")),
    path("", include("core.urls")),
]
