"""Öffentliche Demo: eine eigene Demo-Wache je Besuch (docs/DEMO.md).

Wer sich mit „Demo“ / „Demo“ anmeldet, bekommt eine neue Wache mit
Musterdaten und fünf Demo-Konten (eines je Rolle). Andere Besucher sehen
davon nichts, weil jede fachliche Abfrage an die Wache gebunden ist.

Abmelden beendet die Demo sofort: Die Konten werden gesperrt und – soweit die
Datenbankrechte des Web-Prozesses das erlauben – gleich gelöscht. Sonst und
nach Leerlauf oder Höchstdauer löscht ``purge_demo_sandboxes`` (mit den
Rechten des Datenbank-Eigentümers) alles, was zu der Wache gehört.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError, connection, models, transaction
from django.db.models import Exists, OuterRef
from django.db.models.functions import Length
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import demo_stats
from .demo import DEMO_ACCOUNTS, DEMO_COLLEAGUES, _seed_content
from .demo_models import DemoSandbox
from .middleware import rate_limit_ip
from .models import Membership, Station, UserProfile
from .task_board import ensure_default_station_tasks

logger = logging.getLogger(__name__)

SESSION_KEY = "demo_sandbox_id"
# Fortschritt des Rundgangs; wird nach jeder Änderung (POST) neu bestimmt.
TOUR_SESSION_KEY = "demo_tour"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
DEMO_CREDENTIAL = "demo"
STATION_NAME = "Demo-Wache Musterstadt"
# Rollen in der Reihenfolge, in der sie im Demo-Banner stehen.
ROLE_KEYS = tuple(account["username"].split("-", 1)[1] for account in DEMO_ACCOUNTS)
# Bereiche, die über die eigene Demo-Wache hinaus wirken (Impressum der ganzen
# Installation, öffentliche Links, Geräte, E-Mail-Einladungen).
BLOCKED_URL_NAMES = frozenset({
    "legal_settings",
    "display_token_create",
    "terminal_admin",
    "team_invite_create",
    "feedback_inbox",
    "feedback_status",
    "feedback_delete",
    # Würde Konten außerhalb der Demo-Wache hereinholen oder verändern.
    "team_create",
    "membership_mfa_reset",
    # App-Zugänge überdauern die Sitzung und umgehen die Grenzen unten.
    "api_tokens_manage",
    "mobile_setup_qr",
    "terminal_pair",
    "terminal_pair_qr",
})

# Abmelden und Rollenwechsel bleiben auch nach dem Änderungslimit möglich.
WRITE_EXEMPT_URL_NAMES = frozenset({"logout", "demo_switch_role"})


class DemoUnavailable(Exception):
    """Gerade kann keine neue Demo starten (zu viele aktiv oder zu viele Versuche)."""


def sandbox_enabled() -> bool:
    return bool(getattr(settings, "DEMO_SANDBOX", False))


def is_demo_credentials(username, password) -> bool:
    return (
        sandbox_enabled()
        and (username or "").strip().lower() == DEMO_CREDENTIAL
        and (password or "").strip().lower() == DEMO_CREDENTIAL
    )


def idle_limit() -> timedelta:
    return timedelta(minutes=max(1, settings.DEMO_SANDBOX_IDLE_MINUTES))


def max_lifetime() -> timedelta:
    return timedelta(minutes=max(1, settings.DEMO_SANDBOX_MAX_MINUTES))


def ends_at(sandbox: DemoSandbox):
    """Spätester Zeitpunkt, zu dem die Demo endet."""
    return sandbox.created_at + max_lifetime()


def is_expired(sandbox: DemoSandbox, now=None) -> bool:
    now = now or timezone.now()
    return (
        sandbox.ended_at is not None
        or sandbox.last_seen_at < now - idle_limit()
        or sandbox.created_at < now - max_lifetime()
    )


def active_sandboxes():
    now = timezone.now()
    return DemoSandbox.objects.filter(
        ended_at__isnull=True,
        last_seen_at__gte=now - idle_limit(),
        created_at__gte=now - max_lifetime(),
    )


def expired_sandboxes():
    now = timezone.now()
    return DemoSandbox.objects.filter(
        models.Q(ended_at__isnull=False)
        | models.Q(last_seen_at__lt=now - idle_limit())
        | models.Q(created_at__lt=now - max_lifetime())
    )


def sandbox_username(sandbox: DemoSandbox, role_key: str) -> str:
    return f"demo-{sandbox.token}-{role_key}"


def sandbox_user_ids(station_ids) -> list[int]:
    """Konten, die in einer Demo-Wache entstanden sind und nur dort Mitglied sind.

    Ältere Konten bleiben unangetastet, auch wenn sie in eine Demo-Wache
    geraten sind; ebenso Staff- und Superuser-Konten. Nur so kann ein Besuch
    nie ein Konto der Installation sperren oder löschen.
    """
    station_ids = list(station_ids)
    candidates = set(
        Membership.objects.filter(
            station_id__in=station_ids,
            user__date_joined__gte=models.F("station__demo_sandbox__created_at"),
            user__is_staff=False,
            user__is_superuser=False,
        ).values_list("user_id", flat=True)
    )
    elsewhere = set(
        Membership.objects.filter(user_id__in=candidates).exclude(station_id__in=station_ids)
        .values_list("user_id", flat=True)
    )
    return sorted(candidates - elsewhere)


def _client_key(request) -> str:
    raw = f"{settings.RATELIMIT_KEY_SALT}:{rate_limit_ip(request)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _check_limits(request) -> None:
    if active_sandboxes().count() >= settings.DEMO_SANDBOX_MAX_ACTIVE:
        raise DemoUnavailable(_("Gerade laufen sehr viele Demos. Bitte in ein paar Minuten erneut versuchen."))
    key = f"demo-sandbox:{_client_key(request)}"
    cache.add(key, 0, timeout=3600)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)
        count = 1
    if count > settings.DEMO_SANDBOX_PER_IP_HOUR:
        raise DemoUnavailable(_(
            "Von diesem Anschluss wurden in der letzten Stunde schon viele Demos gestartet. "
            "In spätestens einer Stunde geht es wieder – bis dahin zeigt die Vorführung alle Funktionen ohne Anmeldung."
        ))


@transaction.atomic
def create_sandbox() -> tuple[DemoSandbox, dict[str, User]]:
    """Neue Demo-Wache mit Musterdaten und einem Konto je Rolle anlegen."""
    token = secrets.token_hex(4)
    while DemoSandbox.objects.filter(token=token).exists():
        token = secrets.token_hex(4)
    station = Station.objects.create(
        name=STATION_NAME,
        slug=f"demo-{token}",
        calendar_enabled=True,
        birthdays_enabled=True,
        coffee_enabled=True,
        tasks_enabled=True,
        chat_enabled=True,
        holidays_enabled=True,
        checklists_enabled=True,
        is_active=True,
    )
    sandbox = DemoSandbox.objects.create(station=station, token=token)
    ensure_default_station_tasks(station)
    # Ein Konto je Rolle plus ein paar Kolleginnen und Kollegen ohne Zugang,
    # damit Team, Lesebestätigungen und Kaffeekasse nach einer echten Wache
    # aussehen. Kein Passwort: erreichbar nur über den Demo-Einstieg.
    accounts = [(account["username"].split("-", 1)[1], account) for account in DEMO_ACCOUNTS]
    accounts += [(colleague["key"], colleague) for colleague in DEMO_COLLEAGUES]
    new_users = []
    for key, account in accounts:
        user = User(
            username=sandbox_username(sandbox, key),
            first_name=account["first_name"],
            last_name=account["last_name"],
            is_active=True,
        )
        user.set_unusable_password()
        new_users.append(user)
    created = User.objects.bulk_create(new_users)
    if any(user.pk is None for user in created):  # Datenbank ohne RETURNING
        created = list(User.objects.filter(username__in=[user.username for user in new_users]))
    by_name = {user.username: user for user in created}
    users = {}
    memberships = []
    for key, account in accounts:
        user = by_name[sandbox_username(sandbox, key)]
        memberships.append(Membership(
            user=user, station=station, role=account.get("role", Membership.Role.MEMBER), is_active=True,
        ))
        users[account.get("username") or f"demo-{key}"] = user
    Membership.objects.bulk_create(memberships)
    _seed_content(station, users, marker="", fresh=True)
    sandbox.ready_at = timezone.now()
    sandbox.save(update_fields=["ready_at"])
    return sandbox, users


def current_role_key(request, sandbox: DemoSandbox) -> str:
    """Rolle des Demo-Kontos, mit dem der Besuch gerade angemeldet ist."""
    prefix = f"demo-{sandbox.token}-"
    username = getattr(request.user, "username", "")
    return username[len(prefix):] if username.startswith(prefix) else ""


def home_for_role(role_key: str) -> str:
    """Startseite der Rolle: Auditoren haben keine Übersicht, nur das Audit-Log."""
    return "audit_log" if role_key == "audit" else "dashboard"


def _local_url(request, url: str) -> str | None:
    """Nur Pfade dieser Installation als Rücksprungziel zulassen."""
    if not url or not url_has_allowed_host_and_scheme(url, {request.get_host()}, require_https=request.is_secure()):
        return None
    parts = urlsplit(url)
    if not parts.path.startswith("/"):
        return None
    try:
        if resolve(parts.path).url_name in BLOCKED_URL_NAMES:
            return None
    except Resolver404:
        return None
    return parts.path + (f"?{parts.query}" if parts.query else "") + (f"#{parts.fragment}" if parts.fragment else "")


def _enter(request, sandbox: DemoSandbox, user: User):
    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)
    request.session[SESSION_KEY] = sandbox.pk
    # Sitzungs-Cookie endet mit dem Browser; die Demo selbst endet spätestens
    # nach Leerlauf oder Höchstdauer.
    request.session.set_expiry(0)


def start_demo(request):
    """Demo-Wache anlegen, als Master-Admin anmelden und zur Übersicht leiten."""
    current = getattr(request, "demo_sandbox", None)
    if current is not None:
        # Schon in einer Demo: dort weitermachen statt eine zweite anzulegen
        # (zählt auch nicht gegen die Grenze je Anschluss).
        return redirect(home_for_role(current_role_key(request, current)))
    try:
        _check_limits(request)
    except DemoUnavailable as exc:
        messages.error(request, str(exc))
        return redirect("login")
    sandbox, users = create_sandbox()
    demo_stats.record_start()
    _enter(request, sandbox, users["demo-admin"])
    return redirect("dashboard")


def switch_role(request, sandbox: DemoSandbox, role_key: str, next_url: str = ""):
    if role_key not in ROLE_KEYS:
        return redirect(home_for_role(current_role_key(request, sandbox)))
    user = User.objects.filter(username=sandbox_username(sandbox, role_key), is_active=True).first()
    if user is None:
        return redirect(home_for_role(current_role_key(request, sandbox)))
    # Gleicher Besuch, gleiche Demo-Wache: Das CSRF-Geheimnis bleibt, damit
    # Formulare in anderen offenen Tabs (Abmelden, Rollenwechsel) gültig bleiben.
    csrf_secret = request.META.get("CSRF_COOKIE")
    _enter(request, sandbox, user)
    if csrf_secret:
        request.META["CSRF_COOKIE"] = csrf_secret
    target = _local_url(request, next_url) if role_key != "audit" else None
    return redirect(target or home_for_role(role_key))


def sandbox_for_user(user) -> DemoSandbox | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return DemoSandbox.objects.filter(station__memberships__user_id=user.pk).first()


def end_sandbox(sandbox: DemoSandbox) -> None:
    """Demo beenden: Konten sofort sperren, dann möglichst gleich löschen."""
    now = timezone.now()
    DemoSandbox.objects.filter(pk=sandbox.pk, ended_at__isnull=True).update(ended_at=now)
    User.objects.filter(pk__in=sandbox_user_ids([sandbox.station_id])).update(is_active=False)
    if not can_purge_here():
        return
    try:
        purge_sandbox(sandbox)
    except DatabaseError:
        # Der Web-Prozess darf append-only Tabellen nicht löschen (Postgres-
        # Rechte). Dann räumt purge_demo_sandboxes in Kürze auf.
        logger.info("Demo %s beendet; Löschung folgt durch purge_demo_sandboxes.", sandbox.token)


def _reverse_index() -> dict:
    """Ziel-Modell → Liste (Modell, Fremdschlüssel), die darauf zeigen."""
    index: dict = {}
    for model in apps.get_models(include_auto_created=True):
        for field in model._meta.concrete_fields:
            if field.many_to_one or field.one_to_one:
                index.setdefault(field.related_model, []).append((model, field))
    return index


def _referencing_rows(station_ids, user_ids) -> dict:
    """Alle Zeilen, die direkt oder über andere Zeilen auf die Demo zeigen."""
    index = _reverse_index()
    collected: dict = {Station: set(station_ids), User: set(user_ids)}
    frontier = {model: set(pks) for model, pks in collected.items() if pks}
    while frontier:
        next_frontier: dict = {}
        for target, target_pks in frontier.items():
            for model, field in index.get(target, ()):
                if field.target_field.primary_key:
                    values = list(target_pks)
                else:
                    values = list(target._base_manager.filter(pk__in=list(target_pks))
                                  .values_list(field.target_field.attname, flat=True))
                found = set()
                for start in range(0, len(values), 500):
                    found |= set(
                        model._base_manager.filter(**{f"{field.attname}__in": values[start:start + 500]})
                        .values_list("pk", flat=True)
                    )
                new = found - collected.setdefault(model, set())
                if new:
                    collected[model] |= new
                    next_frontier.setdefault(model, set()).update(new)
        frontier = next_frontier
    return {model: pks for model, pks in collected.items() if pks}


def can_purge_here() -> bool:
    """Darf der aktuelle Datenbank-Benutzer auch append-only Tabellen löschen?"""
    if connection.vendor != "postgresql":
        return True
    with connection.cursor() as cursor:
        cursor.execute("SELECT has_table_privilege(current_user, 'core_auditevent', 'DELETE')")
        return bool(cursor.fetchone()[0])


def _delete_files(model, pks) -> None:
    file_fields = [f for f in model._meta.concrete_fields if isinstance(f, models.FileField)]
    if not file_fields:
        return
    for row in model._base_manager.filter(pk__in=list(pks)).only(*[f.attname for f in file_fields]):
        for field in file_fields:
            stored = getattr(row, field.attname)
            if stored:
                transaction.on_commit(lambda f=stored: f.storage.delete(f.name))


def _delete_login_records(usernames) -> None:
    """Anmeldeprotokolle (django-axes, mit IP-Adresse) der Demo-Konten löschen."""
    usernames = list(usernames)
    if not usernames:
        return
    for model_name in ("AccessAttempt", "AccessLog", "AccessFailureLog"):
        try:
            model = apps.get_model("axes", model_name)
        except LookupError:
            continue
        model._base_manager.filter(username__in=usernames).delete()


def sandbox_upload_bytes(sandbox: DemoSandbox) -> int:
    """Belegter Speicher für Anhänge und Profilbilder einer Demo-Wache."""
    total = 0
    for model in apps.get_models():
        fields = {field.name: field for field in model._meta.concrete_fields}
        if "station" in fields and "size" in fields and isinstance(fields.get("data"), models.BinaryField):
            total += model._base_manager.filter(station_id=sandbox.station_id).aggregate(
                total=models.Sum("size"))["total"] or 0
    total += UserProfile.objects.filter(
        user__station_memberships__station_id=sandbox.station_id, avatar__isnull=False,
    ).aggregate(total=models.Sum(Length("avatar")))["total"] or 0
    return total


def write_refusal(request, sandbox: DemoSandbox) -> str | None:
    """Grund, warum diese Änderung in der Demo abgelehnt wird – sonst None.

    Ein Besuch darf höchstens DEMO_SANDBOX_MAX_WRITES Änderungen schicken und
    höchstens DEMO_SANDBOX_MAX_UPLOAD_MB an Dateien ablegen. Das reicht für
    jeden Rundgang, hält aber Skripte davon ab, die Datenbank zu füllen.
    """
    budget = settings.DEMO_SANDBOX_MAX_WRITES
    if budget > 0:
        key = f"demo-sandbox-writes:{sandbox.token}"
        timeout = int((max_lifetime() + timedelta(minutes=10)).total_seconds())
        cache.add(key, 0, timeout=timeout)
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=timeout)
            count = 1
        if count > budget:
            return _("Diese Demo hat ihr Limit an Änderungen erreicht. Melde dich ab und starte einfach eine neue Demo.")
    if request.META.get("CONTENT_TYPE", "").startswith("multipart/form-data"):
        try:
            incoming = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            incoming = 0
        limit = settings.DEMO_SANDBOX_MAX_UPLOAD_MB * 1024 * 1024
        if sandbox_upload_bytes(sandbox) + incoming > limit:
            return _("Der Speicher dieser Demo ist voll (höchstens %(mb)s MB Dateien). Starte eine neue Demo, um weitere Dateien hochzuladen.") % {
                "mb": settings.DEMO_SANDBOX_MAX_UPLOAD_MB,
            }
    return None


def purge_stations(station_ids) -> int:
    """Demo-Wachen mit allen Konten und Einträgen löschen. Gibt die Zeilenzahl zurück.

    Löscht bewusst auch append-only Zeilen (Kaffeekasse, Audit) – aber nur die
    der Demo-Wachen und nur, wenn der Datenbank-Benutzer das darf. Mehrere
    Wachen auf einmal teilen sich einen Durchlauf durch die Fremdschlüssel.
    """
    station_ids = list(station_ids)
    if not station_ids:
        return 0
    with transaction.atomic():
        demo_stats.record_purge(sandbox)
        user_ids = sandbox_user_ids(station_ids)
        _delete_login_records(User.objects.filter(pk__in=user_ids).values_list("username", flat=True))
        rows = _referencing_rows(station_ids, user_ids)
        total = 0
        for model, pks in rows.items():
            _delete_files(model, pks)
            pk_list = list(pks)
            for start in range(0, len(pk_list), 500):
                total += model._base_manager.filter(pk__in=pk_list[start:start + 500])._raw_delete(connection.alias)
    return total


def purge_sandbox(sandbox: DemoSandbox) -> int:
    return purge_stations([sandbox.station_id])


# Wachen je Transaktion: begrenzt Sperrdauer und Größe eines Durchlaufs.
PURGE_BATCH = 25


def purge_station_batches(station_ids) -> int:
    """Wachen stapelweise löschen; ein fehlerhafter Stapel hält die übrigen nicht auf.

    Scheitert ein Stapel, wird er Wache für Wache wiederholt, damit nur die
    betroffene Demo-Wache liegen bleibt (und im Log steht).
    """
    station_ids = list(station_ids)
    purged = 0
    for start in range(0, len(station_ids), PURGE_BATCH):
        chunk = station_ids[start:start + PURGE_BATCH]
        try:
            purge_stations(chunk)
            purged += len(chunk)
            continue
        except DatabaseError:
            logger.warning("Demo-Purge im Stapel fehlgeschlagen, einzeln wiederholen: %s", chunk)
        for station_id in chunk:
            try:
                purge_stations([station_id])
                purged += 1
            except DatabaseError:
                logger.exception("Demo-Wache %s konnte nicht gelöscht werden.", station_id)
    return purged


def purge_expired() -> int:
    return purge_station_batches(expired_sandboxes().order_by("pk").values_list("station_id", flat=True))


def purge_all() -> int:
    return purge_station_batches(DemoSandbox.objects.order_by("pk").values_list("station_id", flat=True))


def landing_after_demo(reason: str = "ende") -> str:
    return f"{reverse('landing')}?{urlencode({'demo': reason})}"


class DemoSandboxMiddleware:
    """Hängt die Demo-Wache an den Request, beendet abgelaufene Demos und
    sperrt Bereiche, die über die eigene Demo-Wache hinaus wirken."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.demo_sandbox = None
        before = None
        if sandbox_enabled() and request.user.is_authenticated:
            sandbox = self._sandbox(request)
            if sandbox is not None:
                now = timezone.now()
                if is_expired(sandbox, now):
                    end_sandbox(sandbox)
                    logout(request)
                    return redirect(landing_after_demo("abgelaufen"))
                if sandbox.last_seen_at < now - timedelta(seconds=60):
                    DemoSandbox.objects.filter(pk=sandbox.pk).update(last_seen_at=now)
                request.demo_sandbox = sandbox
                if request.method not in SAFE_METHODS:
                    # Nur eine Änderung kann den Rundgang voranbringen.
                    before = tour_state(request, sandbox)
                    request.session.pop(TOUR_SESSION_KEY, None)
        response = self.get_response(request)
        if before is not None and request.user.is_authenticated and 300 <= response.status_code < 400:
            _celebrate_progress(request, request.demo_sandbox, before)
        return response

    @staticmethod
    def _sandbox(request):
        sandbox_id = request.session.get(SESSION_KEY)
        if sandbox_id is False:
            # Für diese Sitzung schon geprüft: kein Demo-Konto.
            return None
        if sandbox_id is not None:
            sandbox = DemoSandbox.objects.filter(
                pk=sandbox_id, station__memberships__user_id=request.user.pk,
            ).first()
            if sandbox is not None:
                return sandbox
        sandbox = sandbox_for_user(request.user)
        request.session[SESSION_KEY] = sandbox.pk if sandbox is not None else False
        return sandbox

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        sandbox = request.demo_sandbox
        if sandbox is None:
            return None
        name = match.url_name if match else None
        if name in BLOCKED_URL_NAMES:
            messages.info(request, _("Dieser Bereich ist in der Demo gesperrt, weil er über die eigene Demo-Wache hinaus wirkt."))
            return self._back(request, sandbox)
        if request.method == "POST" and name not in WRITE_EXEMPT_URL_NAMES:
            refusal = write_refusal(request, sandbox)
            if refusal:
                messages.error(request, refusal)
                return self._back(request, sandbox)
        return None

    @staticmethod
    def _back(request, sandbox):
        """Zurück zur vorigen Seite der Installation, sonst zur Startseite der Rolle."""
        back = _local_url(request, request.META.get("HTTP_REFERER", ""))
        if back:
            return redirect(back)
        return redirect(home_for_role(current_role_key(request, sandbox)))


def _role_label(role) -> str:
    return Membership.Role(role).label


# Rollen im Banner, mit Vornamen: „Mitglied (Mara)“ – der Rundgang spricht von Mara.
ROLE_ACCOUNTS = {account["username"].split("-", 1)[1]: account for account in DEMO_ACCOUNTS}


def demo_banner(request) -> dict | None:
    """Angaben für das Demo-Banner: Ende der Demo und Rollenwechsel."""
    sandbox = getattr(request, "demo_sandbox", None)
    if sandbox is None:
        return None
    return {
        "ends_at": timezone.localtime(ends_at(sandbox)),
        "idle_minutes": settings.DEMO_SANDBOX_IDLE_MINUTES,
        "role": current_role_key(request, sandbox),
        "roles": [
            (key, _role_label(ROLE_ACCOUNTS[key]["role"]), ROLE_ACCOUNTS[key]["first_name"]) for key in ROLE_KEYS
        ],
    }


@require_POST
def switch_role_view(request):
    sandbox = getattr(request, "demo_sandbox", None)
    if sandbox is None:
        return redirect("landing")
    return switch_role(request, sandbox, request.POST.get("role", ""), request.POST.get("next", ""))


def demo_notice(request) -> str:
    """Hinweis auf der Startseite nach dem Ende einer Demo."""
    if not sandbox_enabled():
        return ""
    reason = request.GET.get("demo", "")
    if reason == "ende":
        return _("Deine Demo ist beendet. Alle Eingaben und die Demo-Wache wurden gelöscht.")
    if reason == "abgelaufen":
        return _("Deine Demo ist abgelaufen und wurde gelöscht. Mit „Demo“ / „Demo“ startest du eine neue.")
    return ""


# --- Rundgang „Dein erster Schichtwechsel“ ------------------------------------

TOUR_FLAGS = ("handover", "ack", "device", "defect", "coffee")
# Gerät, an dem Schritt 4 die Funktionskontrolle zeigt (core/demo_modules.py).
TOUR_DEVICE_SLUG = "demo-defi-rtw1"


def _tour_flags(sandbox: DemoSandbox) -> dict:
    """Welche Schritte erledigt sind – eine Abfrage für alle fünf."""
    from .mpg_models import DeviceRoutineCheck
    from .models import CoffeeEntry, HandoverEntry
    from .wachalltag_models import Defect, HandoverAck

    since = sandbox.ready_at
    station = OuterRef("pk")
    row = Station.objects.filter(pk=sandbox.station_id).annotate(
        handover=Exists(HandoverEntry.objects.filter(station=station, created_at__gt=since)),
        ack=Exists(HandoverAck.objects.filter(station=station, created_at__gt=since)),
        device=Exists(DeviceRoutineCheck.objects.filter(station=station, checked_at__gt=since)),
        defect=Exists(Defect.objects.filter(station=station, created_at__gt=since)),
        coffee=Exists(CoffeeEntry.objects.filter(
            station=station, kind=CoffeeEntry.Kind.PAYMENT, created_at__gt=since,
        )),
    ).values(*TOUR_FLAGS).first() or {}
    return {key: bool(row.get(key)) for key in TOUR_FLAGS}


def _ack_target(sandbox: DemoSandbox) -> str:
    """Übergabe für Schritt 3: die eigene aus Schritt 2, sonst die dringendste."""
    from .models import HandoverEntry

    handovers = HandoverEntry.objects.filter(station_id=sandbox.station_id).exclude(
        status=HandoverEntry.Status.DONE,
    )
    target = (
        handovers.filter(created_at__gt=sandbox.ready_at).order_by("-created_at").first()
        or handovers.filter(priority=HandoverEntry.Priority.URGENT).order_by("-created_at").first()
        or handovers.order_by("-created_at").first()
    )
    return reverse("handover_detail", args=[target.pk]) if target else reverse("handover_list")


def tour_state(request, sandbox: DemoSandbox, *, refresh: bool = False) -> dict:
    """Fortschritt aus der Sitzung; neu bestimmt nach jeder Änderung.

    Fortschritt entsteht nur durch eigene Änderungen (POST) des Besuchs; die
    Middleware verwirft den gespeicherten Stand dann. Normale Seitenaufrufe
    kosten so keine zusätzliche Abfrage.
    """
    state = None if refresh else request.session.get(TOUR_SESSION_KEY)
    if not isinstance(state, dict) or set(state.get("flags", {})) != set(TOUR_FLAGS):
        flags = _tour_flags(sandbox)
        state = {"flags": flags, "ack_url": "" if flags["ack"] else _ack_target(sandbox)}
        request.session[TOUR_SESSION_KEY] = state
    return state


def build_tour(request, sandbox: DemoSandbox, state: dict) -> dict:
    flags = state["flags"]
    role = current_role_key(request, sandbox)
    steps = [
        {
            "key": "overview",
            "title": _("Übersicht lesen"),
            "short": _("Übersicht lesen"),
            "text": _("Oben steht, was die Schicht wissen muss: dringende Übergaben, fällige Fristen, knappes Material."),
            "url": reverse("dashboard"),
            "done": True,
        },
        {
            "key": "handover",
            "title": _("Übergabe für die nächste Schicht anlegen"),
            "short": _("Übergabe anlegen"),
            "text": _("Das Formular ist schon ausgefüllt: „Sauerstoff RTW 83-2 fast leer“, Dringlichkeit „Dringend“. Einfach speichern."),
            "url": f"{reverse('handover_create')}?vorlage=sauerstoff",
            "done": flags["handover"],
        },
        {
            "key": "ack",
            "title": _("Als Kollegin quittieren"),
            "short": _("Als Kollegin quittieren"),
            "text": _("Als Mara (Mitglied) die Übergabe öffnen und „Gelesen – quittieren“ antippen. Den Rollenwechsel erledigt der Rundgang."),
            "url": state.get("ack_url") or reverse("handover_list"),
            "role": "mitglied",
            "done": flags["ack"],
        },
        {
            "key": "device",
            "title": _("Medizingerät prüfen"),
            "short": _("Gerät prüfen"),
            "text": _("Beim Defibrillator von RTW 83-1 die Funktionskontrolle bestätigen – so entsteht nebenbei der Nachweis für die nächste Prüfung."),
            "url": reverse("mpg_device_detail", args=[TOUR_DEVICE_SLUG]),
            "done": flags["device"],
        },
        {
            "key": "defect",
            "title": _("Mangel melden"),
            "short": _("Mangel melden"),
            "text": _("Etwas ist kaputt? Mangel mit Frist und verantwortlicher Person anlegen."),
            "url": reverse("defect_create_web"),
            "done": flags["defect"],
        },
        {
            "key": "coffee",
            "title": _("Kaffeekasse bezahlen"),
            "short": _("Kaffeekasse bezahlen"),
            "text": _("„Ich habe bezahlt“ antippen – der offene Monat ist sofort abgehakt, ganz ohne Zettel."),
            "url": reverse("coffee_pay"),
            "done": flags["coffee"],
        },
    ]
    here = request.get_full_path()
    for number, step in enumerate(steps, start=1):
        step["number"] = number
        # Schon am Ziel des Schritts: Das Banner verweist nicht auf sich selbst.
        step["here"] = step["url"] == here
        wanted = step.get("role") or ("admin" if role == "audit" else "")
        # Schritt braucht eine andere Rolle: Der Knopf wechselt sie gleich mit.
        step["switch_role"] = wanted if wanted and wanted != role else ""
        step["role_label"] = _role_label(ROLE_ACCOUNTS[wanted]["role"]) if step["switch_role"] else ""
    done = sum(1 for step in steps if step["done"])
    next_step = next((step for step in steps if not step["done"]), None)
    return {
        "steps": steps,
        "done": done,
        "total": len(steps),
        "complete": next_step is None,
        "next": next_step,
        "role": role,
    }


def demo_tour(request) -> dict | None:
    """Demo-Rundgang „Dein erster Schichtwechsel“: sechs kurze Aufgaben.

    Ein Schritt gilt als erledigt, sobald in der Demo-Wache nach dem Anlegen
    der Musterdaten (``ready_at``) der passende Eintrag entstanden ist. Der
    erste Schritt ist bewusst schon erledigt – der Blick auf die Übersicht
    passiert beim Einstieg.
    """
    sandbox = getattr(request, "demo_sandbox", None)
    if sandbox is None:
        return None
    return build_tour(request, sandbox, tour_state(request, sandbox))


def _celebrate_progress(request, sandbox: DemoSandbox, before: dict) -> None:
    """Nach einer Änderung: geschafften Schritt bestätigen und den nächsten nennen."""
    if sandbox is None:
        return
    state = tour_state(request, sandbox, refresh=True)
    newly = [key for key in TOUR_FLAGS if state["flags"][key] and not before.get("flags", {}).get(key)]
    if not newly:
        return
    tour = build_tour(request, sandbox, state)
    if tour["complete"]:
        messages.success(request, _(
            "Rundgang geschafft – alle %(total)s Schritte erledigt! Auf der Übersicht siehst du, was dabei entstanden ist."
        ) % {"total": tour["total"]})
        return
    finished = next(step for step in tour["steps"] if step["key"] == newly[-1])
    messages.success(request, _(
        "Rundgang: Schritt %(number)s von %(total)s geschafft. Als Nächstes: %(next)s – oben im Banner geht es weiter."
    ) % {"number": finished["number"], "total": tour["total"], "next": tour["next"]["title"]})


TOUR_HANDOVER_TEMPLATES = {
    "sauerstoff": lambda: {
        "category": "material",
        "priority": "urgent",
        "title": _("Sauerstoff RTW 83-2 fast leer"),
        "details": _("Reserveflasche im RTW 83-2 unter 50 bar. Bitte vor Schichtbeginn tauschen – volle Flaschen stehen im Zentrallager."),
    },
}


def tour_form_initial(request) -> dict:
    """Vorbelegung für das Übergabeformular aus dem Rundgang (nur in der Demo)."""
    if getattr(request, "demo_sandbox", None) is None:
        return {}
    template = TOUR_HANDOVER_TEMPLATES.get(request.GET.get("vorlage", ""))
    return template() if template else {}
