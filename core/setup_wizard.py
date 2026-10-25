"""First-installation bootstrap and one-time employee activation.

Security contract: docs/SETUP-WIZARD-PLAN.md. No function here logs or stores
raw tokens or passwords. All state changes that must happen once use a
conditional UPDATE whose row count decides success, so SQLite and PostgreSQL
share the same single-winner semantics without pretending that SQLite
implements ``SELECT ... FOR UPDATE``.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import EmployeeActivation, InstallationSetup, Membership, Station, UserProfile
from .services import audit

ACTIVATION_TTL_DAYS = 7
ACTIVATION_TOKEN_BYTES = 32


class SetupError(Exception):
    """Base class for setup/activation failures with an HTTP status hint."""

    status = 400


class SetupDisabled(SetupError):
    status = 404


class SetupTokenInvalid(SetupError):
    status = 403


class SetupAlreadyCompleted(SetupError):
    status = 409


class SetupConflict(SetupError):
    """A unique constraint won a race after form validation (clean 409)."""

    status = 409


class ActivationInvalid(SetupError):
    status = 410


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def bootstrap_token() -> str:
    return (getattr(settings, "SETUP_BOOTSTRAP_TOKEN", "") or "").strip()


def normalize_bootstrap_token(raw: str) -> str:
    """Touch-taugliche Eingabe: Leerzeichen, Bindestriche und Groß-/Kleinschreibung zählen nicht.

    ``ABCD-EFGH`` und ``abcd efgh`` sind derselbe Einrichtungscode. Die
    Normalisierung gilt für Eingabe und konfigurierten Wert gleichermaßen.
    """
    return "".join(ch for ch in (raw or "") if not ch.isspace() and ch != "-").casefold()


def bootstrap_fingerprint(raw: str) -> str:
    return hash_token(normalize_bootstrap_token(raw))


def setup_available() -> bool:
    """Fail-closed: without a configured bootstrap secret the wizard does not exist."""
    return bool(bootstrap_token())


def verify_bootstrap_token(raw: str) -> bool:
    expected = bootstrap_token()
    if not expected:
        raise SetupDisabled("Erstinstallation ist nicht konfiguriert.")
    candidate = normalize_bootstrap_token(raw)
    if not candidate:
        return False
    return secrets.compare_digest(hash_token(candidate), bootstrap_fingerprint(expected))


def setup_state() -> InstallationSetup | None:
    return InstallationSetup.objects.filter(pk=1).first()


def setup_completed() -> bool:
    state = setup_state()
    return bool(state and state.completed_at)


def setup_pending() -> bool:
    """Einrichtungscode ist gesetzt und die Wache noch nicht angelegt."""
    return setup_available() and not setup_completed()


def verify_bootstrap_hash(bootstrap_hash: str) -> bool:
    expected = bootstrap_token()
    if not expected:
        raise SetupDisabled("Erstinstallation ist nicht konfiguriert.")
    return bool(bootstrap_hash) and secrets.compare_digest(bootstrap_hash, bootstrap_fingerprint(expected))


def _unclaimed_default_station():
    """Die automatisch angelegte Standardwache, solange sie die einzige und unbenutzt ist."""
    stations = list(Station.objects.select_for_update()[:2])
    if len(stations) != 1:
        return None
    station = stations[0]
    if station.slug != settings.DEFAULT_STATION_SLUG or Membership.objects.filter(station=station).exists():
        return None
    return station


def complete_setup(*, data: dict, raw_token: str | None = None, bootstrap_hash: str | None = None) -> tuple[Station, User]:
    """Create station and bootstrap admin exactly once.

    ``data`` must already be validated by the caller (forms.SetupWizardForm).
    The conditional claim happens before any resource is created; any later
    error rolls the claim back together with the resources.
    """
    if not setup_available():
        raise SetupDisabled("Erstinstallation ist nicht konfiguriert.")
    raw_token = (raw_token or "").strip()
    if bootstrap_hash is not None:
        if not verify_bootstrap_hash(bootstrap_hash):
            raise SetupTokenInvalid("Bootstrap-Token ist ungültig.")
        fingerprint = bootstrap_hash
    elif verify_bootstrap_token(raw_token or ""):
        fingerprint = bootstrap_fingerprint(raw_token)
    else:
        raise SetupTokenInvalid("Bootstrap-Token ist ungültig.")

    now = timezone.now()
    try:
        with transaction.atomic():
            InstallationSetup.objects.get_or_create(pk=1)
            # Row lock is real on PostgreSQL and a documented no-op on SQLite.
            InstallationSetup.objects.select_for_update().filter(pk=1).first()
            claimed = InstallationSetup.objects.filter(pk=1, completed_at__isnull=True).update(
                completed_at=now,
                bootstrap_fingerprint=fingerprint,
            )
            if not claimed:
                raise SetupAlreadyCompleted("Die Erstinstallation ist bereits abgeschlossen.")

            fields = {
                "name": data["station_name"].strip(),
                "organization_profile": data["organization_profile"],
                "employee_count": data.get("employee_count"),
                "street": data.get("street", "").strip(),
                "postal_code": data.get("postal_code", "").strip(),
                "city": data.get("city", "").strip(),
                "timezone_name": data.get("timezone_name") or "Europe/Berlin",
                "weather_enabled": bool(data.get("weather_enabled")),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "traffic_enabled": bool(data.get("traffic_enabled")),
                "traffic_roads": data.get("traffic_roads") or "",
                "traffic_radius_km": data.get("traffic_radius_km") or 25,
                "traffic_warning_areas": data.get("traffic_warning_areas") or "",
            }
            station = _unclaimed_default_station()
            if station is not None:
                # Der Container-Start legt mit „migrate“ eine leere Standardwache
                # an (bootstrap_project). Sie wird übernommen statt daneben eine
                # zweite Wache anzulegen; Slug und Tagesaufgaben-Vorlage bleiben.
                for name, value in fields.items():
                    setattr(station, name, value)
                station.save()
            else:
                station = Station.objects.create(slug=data["slug"], **fields)
            user = User.objects.create_user(
                username=data["admin_username"].strip(),
                password=data["password1"],
                first_name=data.get("admin_first_name", "").strip(),
                last_name=data.get("admin_last_name", "").strip(),
                email=data.get("admin_email", "").strip(),
            )
            UserProfile.for_user(user)
            membership = Membership.objects.create(
                user=user,
                station=station,
                role=Membership.Role.ADMIN,
            )
            state = InstallationSetup.objects.get(pk=1)
            state.station = station
            state.completed_by = user
            state.save(update_fields=["station", "completed_by"])
            audit(user, station, "setup.completed", membership, {
                "fields": ["station", "user", "role"],
                "employee_count": station.employee_count,
                "weather_enabled": station.weather_enabled,
            })
    except IntegrityError as exc:
        # A racing duplicate (normally the username) rolls back the claim and
        # every resource created in the same transaction. Report a clean 409.
        raise SetupConflict(
            "Benutzername oder Stationskürzel ist bereits vergeben."
        ) from exc
    return station, user


INVITABLE_ROLES = frozenset(
    {Membership.Role.MEMBER, Membership.Role.SHIFT_LEAD, Membership.Role.CASHIER}
)


def create_activation(
    *,
    user: User,
    station: Station,
    created_by: User | None,
    ttl_days: int = ACTIVATION_TTL_DAYS,
    role: str = Membership.Role.MEMBER,
):
    """Create a one-time activation; returns ``(activation, raw_token)``."""
    if role not in INVITABLE_ROLES:
        raise ValueError("Unzulässige Einladungsrolle.")
    raw = secrets.token_urlsafe(ACTIVATION_TOKEN_BYTES)
    now = timezone.now()
    try:
        with transaction.atomic():
            # Serialize reissues per account. The row lock is effective on
            # PostgreSQL and a documented no-op on SQLite; the conditional
            # UPDATE keeps the revocation single-winner on both backends.
            User.objects.select_for_update().filter(pk=user.pk).first()
            # An expired-but-not-revoked row still occupies the partial unique
            # constraint. Close it first, in the same transaction as the new
            # token, so a failure cannot leave the account without a usable
            # invitation or with a half-written state.
            EmployeeActivation.objects.filter(
                user=user,
                used_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__lte=now,
            ).update(revoked_at=now)
            activation = EmployeeActivation.objects.create(
                user=user,
                station=station,
                token_hash=hash_token(raw),
                role=role,
                created_by=created_by,
                expires_at=now + timedelta(days=ttl_days),
            )
    except IntegrityError as exc:
        raise SetupConflict(
            "Für dieses Konto ist bereits ein offener Aktivierungslink vorhanden."
        ) from exc
    return activation, raw


def find_activation(raw: str) -> EmployeeActivation | None:
    if not raw:
        return None
    raw = raw.strip()
    return (
        EmployeeActivation.objects.select_related("user", "station")
        .filter(token_hash=hash_token(raw))
        .first()
    )


def consume_activation(raw: str, *, password: str) -> EmployeeActivation:
    """Atomically consume a token, then set the employee-chosen password."""
    activation = find_activation(raw)
    if activation is None:
        raise ActivationInvalid("Aktivierungslink ist ungültig.")
    if not activation.station.is_active:
        raise ActivationInvalid("Aktivierungslink ist ungültig.")
    # A tampered database row must never grant admin/auditor rights.
    invited_role = (
        activation.role if activation.role in INVITABLE_ROLES else Membership.Role.MEMBER
    )
    now = timezone.now()
    with transaction.atomic():
        consumed = EmployeeActivation.objects.filter(
            pk=activation.pk,
            used_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).update(used_at=now)
        if not consumed:
            raise ActivationInvalid("Aktivierungslink ist abgelaufen oder wurde bereits verwendet.")
        user = activation.user
        user.set_password(password)
        user.is_active = True
        user.save(update_fields=["password", "is_active"])
        # The employee may only ever get the membership tied to this token.
        # An existing membership (e.g. a master admin) is never downgraded and
        # a membership at a foreign station is never deactivated or moved.
        membership = Membership.objects.filter(
            user=user, station=activation.station
        ).first()
        if membership is None:
            other_active = Membership.objects.filter(user=user, is_active=True).exists()
            if other_active:
                raise ActivationInvalid(
                    "Dieses Konto ist bereits einer anderen Wache zugeordnet."
                )
            Membership.objects.create(
                user=user,
                station=activation.station,
                role=invited_role,
                is_active=True,
            )
        elif not membership.is_active:
            other_active = (
                Membership.objects.filter(user=user, is_active=True)
                .exclude(pk=membership.pk)
                .exists()
            )
            if other_active:
                raise ActivationInvalid(
                    "Dieses Konto ist bereits einer anderen Wache zugeordnet."
                )
            membership.is_active = True
            membership.save(update_fields=["is_active"])
        # Existing membership keeps its role: activation must not escalate or
        # silently demote a role that an admin assigned deliberately.
        audit(user, activation.station, "activation.completed", activation, {
            "fields": ["used_at", "is_active"],
            "role": invited_role if membership is None else membership.role,
        })
    activation.refresh_from_db()
    return activation


def revoke_activation(activation: EmployeeActivation, *, actor: User | None = None) -> bool:
    now = timezone.now()
    revoked = EmployeeActivation.objects.filter(
        pk=activation.pk, used_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    if revoked:
        audit(actor, activation.station, "activation.revoked", activation, {"fields": ["revoked_at"]})
    return bool(revoked)


def active_activations(station: Station):
    return (
        EmployeeActivation.objects.filter(
            station=station,
            used_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("user", "created_by")
        .order_by("-created_at")
    )


def reusable_pending_invite(user: User | None, station: Station | None = None) -> bool:
    """True only for an own, never-activated invite account without membership.

    Reusing such a row is safe: it has no password, is inactive and belongs to
    no station. Any active account, any usable password or any existing
    membership (even an inactive one at a foreign station) makes reuse a
    takeover and is therefore refused.
    """
    if station is None or user is None or user.is_active or user.has_usable_password():
        return False
    history = EmployeeActivation.objects.filter(user=user)
    if not history.filter(station=station).exists() or history.exclude(station=station).exists():
        return False
    if EmployeeActivation.objects.filter(user=user, used_at__isnull=False).exists():
        # The account was activated at least once; it is not a fresh invite
        # even if an operator later removed the membership.
        return False
    return not Membership.objects.filter(user=user).exists()


def create_employee_invite(*, station: Station, created_by: User, data: dict):
    """Create an inactive account without a password plus its activation token.

    A revoked or expired invitation for the same pending account may be
    reissued; an existing active account is never taken over.
    """
    username = data["username"].strip()
    raw = None
    try:
        with transaction.atomic():
            # Lock and re-read under the transaction so the form validation
            # cannot be bypassed by a concurrent request (TOCTOU).
            existing = (
                User.objects.select_for_update()
                .filter(username__iexact=username)
                .first()
            )
            if existing is None:
                try:
                    user = User.objects.create_user(
                        username=username,
                        password=None,
                        first_name=data.get("first_name", "").strip(),
                        last_name=data.get("last_name", "").strip(),
                    )
                except IntegrityError as exc:
                    # The username was inserted between validation and this
                    # transaction: one controlled conflict, full rollback.
                    raise SetupConflict(
                        "Dieser Benutzername wurde gerade vergeben. Bitte erneut versuchen."
                    ) from exc
                user.set_unusable_password()
                user.is_active = False
                user.save(update_fields=["password", "is_active"])
                UserProfile.for_user(user)
            else:
                if not reusable_pending_invite(existing, station=station):
                    raise SetupConflict("Dieser Benutzername ist bereits vergeben.")
                user = existing
                if EmployeeActivation.objects.filter(
                    user=user,
                    used_at__isnull=True,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                ).exists():
                    # Reuse is only for revoked/expired invitations; an open
                    # link must be revoked deliberately, not silently replaced.
                    raise SetupConflict(
                        "Für dieses Konto ist bereits ein offener Aktivierungslink vorhanden. "
                        "Bitte zuerst widerrufen."
                    )
                changed = []
                for field, key in (("first_name", "first_name"), ("last_name", "last_name")):
                    value = (data.get(key) or "").strip()
                    if value and getattr(user, field) != value:
                        setattr(user, field, value)
                        changed.append(field)
                if changed:
                    user.save(update_fields=changed)
            activation, raw = create_activation(
                user=user,
                station=station,
                created_by=created_by,
                role=data.get("role") or Membership.Role.MEMBER,
            )
            audit(created_by, station, "activation.created", activation, {
                "fields": ["user", "expires_at"],
                "role": activation.role,
            })
    except IntegrityError as exc:
        # create_activation already translates its own constraint conflict;
        # anything reaching here is an unexpected integrity failure, still
        # reported as a controlled form conflict after full rollback.
        raise SetupConflict(
            "Die Einladung konnte nicht gespeichert werden. Bitte erneut versuchen."
        ) from exc
    return user, activation, raw


def activation_url(request, raw: str) -> str:
    from django.urls import reverse

    path = reverse("activate_account", kwargs={"token": raw})
    configured = (getattr(settings, "SITE_URL", "") or "").strip().rstrip("/")
    parsed = urlparse(configured)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{configured}{path}"
    # No canonical origin configured: keep the request origin, but the host is
    # only ever the validated request host (ALLOWED_HOSTS stays restrictive).
    return request.build_absolute_uri(path)


def local_origin_warning(request) -> bool:
    """True when the configured site origin is not https (documented LAN caveat)."""
    return not request.is_secure()
