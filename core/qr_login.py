"""QR-Login service: cryptography, CAS state transitions, rate limiting, and freshness."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import pyotp
import qrcode
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from .auth_session import get_auth_method, get_auth_time
from .mfa import mfa_enabled, mfa_required, totp_plaintext, user_has_confirmed_mfa
from .models import Membership, QrLoginRequest, QrTotpUse, Station, TotpDevice
from .rate_limit import consume
from .services import audit

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

CHECK_WORDS = (
    "ADLER", "ALPEN", "AMSEL", "ANKER", "APFEL", "ATLAS", "BACHE", "BAUM",
    "BERGE", "BIRKE", "BLITZ", "BLUME", "BOGEN", "BUCHE", "DACHS", "DISTEL",
    "DOLDE", "DRACHE", "DOHLE", "DROSSEL", "EICHE", "ELCH", "ENZIAN", "ESCHE",
    "EULE", "FALKE", "FASAN", "FELDER", "FICHTE", "FINKE", "FLUSS", "FOEHRE",
    "FORELLE", "FUCHS", "GINSTER", "GIPFEL", "GLOCKE", "GRANIT", "HABICHT", "HASE",
    "HEIDE", "HERBST", "HIRSCH", "HOLZ", "HORST", "HUEGEL", "IGEL", "INSEL",
    "JASMIN", "KIEFER", "KLEE", "KLIPPE", "KOECHER", "KRANICH", "KUCKUCK", "LAVENDEL",
    "LERCHE", "LIBELLE", "LINDE", "LOEWE", "LUCHS", "MARDER", "MEISE", "MERKUR",
    "MOEWE", "MOOR", "MOOS", "MORGEN", "MURMEL", "NELKE", "OTTER", "PANTHER",
    "PAPAGEI", "PELIKAN", "PFAU", "PFEIL", "PAPPEL", "QUELLE", "RABE", "REGEN",
    "REIHER", "ROBBE", "ROSE", "SALBEI", "SCHILF", "SCHWAN", "SEEADLER", "SILBER",
    "SPECHT", "STEIN", "STERNE", "STORCH", "STURM", "TALWEG", "TANNEN", "TAUBE",
    "TEICH", "TIGER", "TULPE", "UHU", "VEILCHEN", "WALD", "WASSER", "WEIDE",
    "WELLE", "WESPE", "WIESE", "WIND", "WOLKE", "ZEBRA", "ZEISIG", "ZEDER",
    "ZIRBE", "ACHAT", "BASALT", "KIESEL", "KORALLE", "QUARZ", "RUBIN", "SMARAGD",
    "TOPAS", "BERYL", "JASPIS", "OPAL", "METEOR", "KOMET", "POLAR", "AURORA",
)

DEFAULT_RATE_LIMITS = {
    "qr_start": (10, 300),
    "qr_status": (120, 120),
    "qr_approve": (10, 60),
    "qr_exchange": (10, 60),
    "qr_passkey": (10, 60),
}


def get_canonical_origin(request) -> str | None:
    """Return the canonical HTTPS origin, or HTTP if explicitly allowed in tests."""
    allow_insecure = getattr(settings, "QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN", False)
    # request.is_secure() wuerde hier bereits den global konfigurierten
    # SECURE_PROXY_SSL_HEADER auswerten und damit auch ohne TRUSTED_PROXY
    # fail-open gehen. Deshalb zaehlt nur der direkte Transport (WSGI-Scheme)
    # oder ein ausdruecklich vertrauenswuerdiger Proxy.
    direct_secure = request.META.get("wsgi.url_scheme") == "https"
    proto_header = (
        request.META.get("HTTP_X_FORWARDED_PROTO", "")
        if getattr(settings, "TRUSTED_PROXY", False)
        else ""
    )
    forwarded_secure = proto_header.split(",")[0].strip().lower() == "https"
    is_secure = direct_secure or forwarded_secure
    if not is_secure and not allow_insecure:
        return None
    site_url = getattr(settings, "SITE_URL", "").strip().rstrip("/")
    if site_url:
        parsed = urlparse(site_url)
        if parsed.scheme == "https":
            return f"https://{parsed.netloc}"
        if allow_insecure:
            return f"{parsed.scheme}://{parsed.netloc}"
    if is_secure:
        return f"https://{request.get_host()}"
    if allow_insecure:
        return f"http://{request.get_host()}"
    return None


def is_qr_login_enabled(request=None) -> bool:
    """Return True if QR login is enabled and a secure canonical origin is available."""
    if not getattr(settings, "QR_LOGIN_ENABLED", False):
        return False
    if request is not None and get_canonical_origin(request) is None:
        return False
    return True


def check_qr_rate_limit(bucket: str, raw_key: str) -> bool:
    """Multi-worker rate limit check using core.rate_limit."""
    limits = getattr(settings, "QR_LOGIN_RATE_LIMITS", {})
    limit, window = limits.get(bucket, DEFAULT_RATE_LIMITS.get(bucket, (10, 60)))
    return consume(bucket, raw_key, limit=limit, window_seconds=window)


def generate_qr_secret() -> str:
    """256-bit URL-safe secret token."""
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    return hashlib.sha256((secret or "").encode("utf-8")).hexdigest()


def generate_manual_code() -> str:
    """50-bit entropy Crockford Base32 10-char code."""
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(10))


def hash_manual_code(code: str) -> str:
    clean = (code or "").strip().upper()
    return hashlib.sha256(f"manual:{clean}".encode("utf-8")).hexdigest()


def generate_browser_nonce() -> str:
    return secrets.token_urlsafe(32)


def hash_nonce(nonce: str) -> str:
    return hashlib.sha256((nonce or "").encode("utf-8")).hexdigest()


def compute_browser_session_hash(session_key: str, nonce: str) -> str:
    payload = f"{session_key}|{nonce}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_check_word(login_id: uuid.UUID | str, secret_hash: str) -> str:
    """Generate deterministic human-readable check word pair from HMAC."""
    msg = f"{login_id}:{secret_hash}".encode("utf-8")
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    w1 = CHECK_WORDS[digest[0] % len(CHECK_WORDS)]
    w2 = CHECK_WORDS[digest[1] % len(CHECK_WORDS)]
    return f"{w1}-{w2}"


def make_qr_data_uri(content: str) -> str:
    """Generate a PNG data URI for the given content using qrcode locally."""
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def verify_totp_with_time_step(device: TotpDevice, token: str, valid_window: int = 1) -> tuple[bool, int | None]:
    """Verify TOTP token and return (True, time_step) if valid, else (False, None)."""
    token = (token or "").strip().replace(" ", "")
    # isascii(): hmac.compare_digest lehnt Nicht-ASCII-Text mit TypeError ab.
    if not (token.isascii() and token.isdigit()):
        return False, None
    totp = pyotp.TOTP(totp_plaintext(device))
    base_step = totp.timecode(timezone.now())
    for i in range(-valid_window, valid_window + 1):
        step = base_step + i
        if hmac.compare_digest(str(token), str(totp.generate_otp(step))):
            return True, step
    return False, None


def consume_totp_step(user: User, time_step: int) -> bool:
    """Ensure each TOTP time step is consumed exactly once per user."""
    try:
        with transaction.atomic():
            QrTotpUse.objects.create(user=user, time_step=time_step)
        return True
    except IntegrityError:
        return False


def get_approval_freshness(
    request,
    user: User,
    totp_token: str | None = None,
    qr_request: QrLoginRequest | None = None,
) -> tuple[bool, int | None, str]:
    """Verify freshness on the approving device without side effects.

    Returns (ok, totp_step, reason).
    """
    auth_method = get_auth_method(request)
    auth_time = get_auth_time(request)
    now_ts = int(timezone.now().timestamp())
    has_mfa = user_has_confirmed_mfa(user)

    if has_mfa:
        # Option 1: Login session with MFA <= 300 s (QR session never counts)
        if auth_method != "qr" and auth_time is not None:
            age = now_ts - auth_time
            if 0 <= age <= 300:
                return True, None, "session"

        # Option 2: Active TOTP token provided (verify without consuming)
        if totp_token:
            device = TotpDevice.objects.filter(user=user, is_confirmed=True).first()
            if device:
                ok, time_step = verify_totp_with_time_step(device, totp_token)
                if ok and time_step is not None:
                    if not QrTotpUse.objects.filter(user=user, time_step=time_step).exists():
                        return True, time_step, "totp"

        # Option 3: Fresh Passkey reauth on the confirm page <= 300 s
        reauth_user_id = request.session.get("qr_passkey_reauth_user_id")
        reauth_login_id = request.session.get("qr_passkey_reauth_login_id")
        reauth_time = request.session.get("qr_passkey_reauth_time")
        if (
            qr_request is not None
            and reauth_user_id == user.pk
            and str(reauth_login_id) == str(qr_request.pk)
            and isinstance(reauth_time, (int, float))
        ):
            reauth_age = now_ts - int(reauth_time)
            if 0 <= reauth_age <= 300:
                return True, None, "passkey"

        return False, None, "mfa_required"
    else:
        # Non-MFA user: session <= 600 s (QR session never counts)
        if auth_method == "qr" or auth_time is None:
            return False, None, "session_not_fresh"
        age = now_ts - auth_time
        if 0 <= age <= 600:
            return True, None, "session"
        return False, None, "session_expired"


def check_approval_freshness(
    request,
    user: User,
    totp_token: str | None = None,
    qr_request: QrLoginRequest | None = None,
) -> bool:
    """Side-effect-free freshness check for the approving device.

    Der TOTP-Zeitschritt wird hier bewusst NICHT verbraucht: Der Verbrauch
    gehoert atomar in ``approve_qr_request(..., totp_step=...)``, damit
    abgelaufene/terminale Anforderungen und verlorene CAS-Rennen keinen
    Zeitschritt verbrennen (Q3). Aufrufer, die nur pruefen, duerfen den
    zurueckgegebenen Schritt nicht separat konsumieren.
    """
    ok, _totp_step, _reason = get_approval_freshness(
        request, user, totp_token=totp_token, qr_request=qr_request
    )
    return ok


def create_qr_login_request(request, station: Station | None = None) -> tuple[QrLoginRequest, str, str, str, str, str]:
    """Create a new QrLoginRequest, store session binding, and return:
    (qr_request, qr_secret, manual_code, check_word, qr_url, qr_image)
    """
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    origin = get_canonical_origin(request)
    if not origin:
        raise ValueError("Kein gültiger kanonischer Origin verfügbar.")

    station = station or Station.get_default()

    login_id = uuid.uuid4()
    qr_secret = generate_qr_secret()
    secret_hash = hash_secret(qr_secret)

    manual_code = generate_manual_code()
    manual_code_hash = hash_manual_code(manual_code)
    while QrLoginRequest.objects.filter(manual_code_hash=manual_code_hash).exists():
        manual_code = generate_manual_code()
        manual_code_hash = hash_manual_code(manual_code)

    nonce = generate_browser_nonce()
    browser_nonce_hash = hash_nonce(nonce)
    browser_session_hash = compute_browser_session_hash(session_key, nonce)

    # Store nonce in session
    nonces = request.session.get("qr_browser_nonces", {})
    nonces[str(login_id)] = nonce
    request.session["qr_browser_nonces"] = nonces
    request.session.modified = True

    ttl = getattr(settings, "QR_LOGIN_TTL_SECONDS", 120)
    now = timezone.now()
    expires_at = now + timedelta(seconds=ttl)

    check_word = compute_check_word(login_id, secret_hash)

    qr_request = QrLoginRequest.objects.create(
        id=login_id,
        secret_hash=secret_hash,
        manual_code_hash=manual_code_hash,
        browser_session_hash=browser_session_hash,
        browser_nonce_hash=browser_nonce_hash,
        station=station,
        origin=origin,
        state=QrLoginRequest.State.CREATED,
        expires_at=expires_at,
        check_word=check_word,
    )

    qr_url = f"{origin}/anmelden/qr/{login_id}/bestaetigen/#secret={qr_secret}"
    qr_image = make_qr_data_uri(qr_url)

    audit(None, station, "qr_login.created", qr_request, {
        "login_id_prefix": str(login_id)[:8],
        "state": "created",
        "origin_host": urlparse(origin).netloc or origin,
        "station_id": station.pk,
        "role": "",
    })

    return qr_request, qr_secret, manual_code, check_word, qr_url, qr_image


def verify_browser_session(request, qr_request: QrLoginRequest) -> bool:
    """Verify that request comes from the exact browser session that started this QR login."""
    session_key = request.session.session_key
    if not session_key:
        return False
    nonces = request.session.get("qr_browser_nonces", {})
    nonce = nonces.get(str(qr_request.id))
    if not nonce:
        return False
    expected_session_hash = compute_browser_session_hash(session_key, nonce)
    expected_nonce_hash = hash_nonce(nonce)
    return (
        hmac.compare_digest(qr_request.browser_session_hash, expected_session_hash)
        and hmac.compare_digest(qr_request.browser_nonce_hash, expected_nonce_hash)
    )


def verify_secret(qr_request: QrLoginRequest, secret: str | None) -> bool:
    if not secret:
        return False
    return hmac.compare_digest(qr_request.secret_hash, hash_secret(secret))


def verify_possession(qr_request: QrLoginRequest, secret: str | None, manual_code: str | None) -> bool:
    """Verify possession via secret OR manual code."""
    if secret and verify_secret(qr_request, secret):
        return True
    if manual_code:
        provided_hash = hash_manual_code(manual_code)
        if hmac.compare_digest(qr_request.manual_code_hash, provided_hash):
            return True
    return False


def get_external_state(qr_request: QrLoginRequest) -> str:
    """Return external state: pending|approved|denied|expired|revoked|consumed."""
    if qr_request.state in (QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED):
        if timezone.now() >= qr_request.expires_at:
            return "expired"
        return "pending"
    if qr_request.state == QrLoginRequest.State.APPROVED:
        if timezone.now() >= qr_request.expires_at:
            return "expired"
        return "approved"
    return qr_request.state


def mark_scanned_if_created(qr_request: QrLoginRequest) -> bool:
    """Transition CREATED -> SCANNED on initial confirm view if unexpired."""
    now = timezone.now()
    if qr_request.state == QrLoginRequest.State.CREATED and qr_request.expires_at > now:
        updated = QrLoginRequest.objects.filter(
            pk=qr_request.pk,
            state=QrLoginRequest.State.CREATED,
            expires_at__gt=now,
        ).update(state=QrLoginRequest.State.SCANNED)
        if updated:
            qr_request.state = QrLoginRequest.State.SCANNED
            return True
    return False


def approve_qr_request(
    qr_request: QrLoginRequest,
    user: User,
    membership: Membership,
    session_key: str = "",
    totp_step: int | None = None,
) -> bool:
    """Atomically approve QR request."""
    now = timezone.now()
    approved_hash = hash_secret(session_key) if session_key else ""
    try:
        with transaction.atomic():
            updated = QrLoginRequest.objects.filter(
                pk=qr_request.pk,
                state__in=[QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED],
                expires_at__gt=now,
            ).update(
                state=QrLoginRequest.State.APPROVED,
                approved_at=now,
                approved_by=user,
                approved_session_hash=approved_hash,
            )
            if not updated:
                return False
            if totp_step is not None:
                QrTotpUse.objects.create(user=user, time_step=totp_step)
    except IntegrityError:
        return False

    qr_request.state = QrLoginRequest.State.APPROVED
    qr_request.approved_at = now
    qr_request.approved_by = user
    audit(user, qr_request.station, "qr_login.approved", qr_request, {
        "login_id_prefix": str(qr_request.id)[:8],
        "state": "approved",
        "origin_host": urlparse(qr_request.origin).netloc or qr_request.origin,
        "station_id": qr_request.station_id,
        "role": membership.role,
    })
    return True


def deny_qr_request(qr_request: QrLoginRequest, user: User | None = None) -> bool:
    """Atomically deny QR request."""
    now = timezone.now()
    updated = QrLoginRequest.objects.filter(
        pk=qr_request.pk,
        state__in=[QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED],
        expires_at__gt=now,
    ).update(state=QrLoginRequest.State.DENIED)
    if updated:
        qr_request.state = QrLoginRequest.State.DENIED
        audit(user, qr_request.station, "qr_login.denied", qr_request, {
            "login_id_prefix": str(qr_request.id)[:8],
            "state": "denied",
            "origin_host": urlparse(qr_request.origin).netloc or qr_request.origin,
            "station_id": qr_request.station_id,
            "role": "",
        })
        return True
    return False


def exchange_qr_request(qr_request: QrLoginRequest) -> bool:
    """Atomically exchange APPROVED -> CONSUMED."""
    now = timezone.now()
    updated = QrLoginRequest.objects.filter(
        pk=qr_request.pk,
        state=QrLoginRequest.State.APPROVED,
        expires_at__gt=now,
    ).update(
        state=QrLoginRequest.State.CONSUMED,
        consumed_at=now,
    )
    if updated:
        qr_request.state = QrLoginRequest.State.CONSUMED
        qr_request.consumed_at = now
        return True
    return False


def revoke_open_requests_for_user(user: User) -> int:
    """Revoke any open APPROVED requests for this user (e.g. on logout or role change)."""
    now = timezone.now()
    open_requests = list(
        QrLoginRequest.objects.filter(
            approved_by=user,
            state=QrLoginRequest.State.APPROVED,
            expires_at__gt=now,
        )
    )
    count = 0
    for req in open_requests:
        updated = QrLoginRequest.objects.filter(
            pk=req.pk,
            state=QrLoginRequest.State.APPROVED,
        ).update(state=QrLoginRequest.State.REVOKED)
        if updated:
            count += 1
            audit(user, req.station, "qr_login.revoked", req, {
                "login_id_prefix": str(req.id)[:8],
                "state": "revoked",
                "origin_host": urlparse(req.origin).netloc or req.origin,
                "station_id": req.station_id,
                "role": "",
            })
    return count
