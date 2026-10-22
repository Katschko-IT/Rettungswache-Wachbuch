from django.contrib.auth.views import LoginView
from django.shortcuts import redirect

from core.i18n import apply_login_language
from core.mfa import mfa_enabled, mfa_required, user_has_confirmed_mfa
from core.qr_login import is_qr_login_enabled
from core.setup_wizard import setup_pending
from core.webauthn_auth import webauthn_enabled


class PasswordLoginView(LoginView):
    """Password login with optional TOTP/Passkey second step."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["webauthn_enabled"] = webauthn_enabled()
        context["qr_login_enabled"] = is_qr_login_enabled(self.request)
        context["setup_pending"] = setup_pending()
        return context

    def form_valid(self, form):
        user = form.get_user()
        if mfa_enabled() and user_has_confirmed_mfa(user):
            self.request.session["mfa_pending_user_id"] = user.pk
            self.request.session["mfa_next"] = self.get_redirect_url()
            self.request.session["mfa_failures"] = 0
            return redirect("mfa_verify")
        response = super().form_valid(form)
        if mfa_enabled() and mfa_required() and not user_has_confirmed_mfa(user):
            return apply_login_language(self.request, user, redirect("mfa_setup"))
        return apply_login_language(self.request, user, response)
