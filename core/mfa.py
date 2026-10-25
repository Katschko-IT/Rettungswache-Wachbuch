import pyotp
from django.conf import settings
from django.utils import timezone

from .crypto_at_rest import decrypt_secret, encrypt_secret
from .models import TotpDevice, WebAuthnCredential
from .webauthn_auth import user_has_passkey, webauthn_enabled


def mfa_enabled():
    return bool(getattr(settings, "MFA_ENABLED", True))


def mfa_required():
    """Pflicht per Umgebung (MFA_REQUIRED) oder durch den Betreiber im Assistenten/Einstellungen."""
    if getattr(settings, "MFA_REQUIRED", False):
        return True
    from .site_profile import site_mfa_required

    return site_mfa_required()


def user_has_confirmed_mfa(user):
    """True if the user has at least one confirmed second factor (TOTP and/or Passkey)."""
    if TotpDevice.objects.filter(user=user, is_confirmed=True).exists():
        return True
    if webauthn_enabled() and user_has_passkey(user):
        return True
    return False


def user_has_totp(user):
    return TotpDevice.objects.filter(user=user, is_confirmed=True).exists()


def totp_plaintext(device):
    """Return the TOTP shared secret in plaintext (decrypts AES-GCM envelope if needed)."""
    return decrypt_secret(device.secret)


def provisioning_uri(device, issuer=None):
    issuer = issuer or settings.APP_NAME
    return pyotp.TOTP(totp_plaintext(device)).provisioning_uri(
        name=user_label(device.user),
        issuer_name=issuer,
    )


def user_label(user):
    return user.get_username()


def create_pending_device(user):
    secret = pyotp.random_base32()
    device, _ = TotpDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret": encrypt_secret(secret),
            "is_confirmed": False,
            "confirmed_at": None,
        },
    )
    return device


def pending_device(user):
    """Unbestätigtes Gerät weiterverwenden: der Schlüssel muss zwischen QR-Anzeige und Bestätigung gleich bleiben."""
    device = TotpDevice.objects.filter(user=user, is_confirmed=False).first()
    return device or create_pending_device(user)


def verify_totp(device, token):
    token = (token or "").strip().replace(" ", "")
    if not token.isdigit():
        return False
    totp = pyotp.TOTP(totp_plaintext(device))
    return totp.verify(token, valid_window=1)


def confirm_device(device, token):
    if not verify_totp(device, token):
        return False
    device.is_confirmed = True
    device.confirmed_at = timezone.now()
    device.save(update_fields=["is_confirmed", "confirmed_at"])
    return True


def disable_device(user):
    TotpDevice.objects.filter(user=user).delete()


def disable_all_mfa(user):
    disable_device(user)
    WebAuthnCredential.objects.filter(user=user).delete()
