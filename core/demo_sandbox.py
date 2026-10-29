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
from urllib.parse import urlencode

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError, connection, models, transaction
from django.db.models.functions import Length
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .demo import DEMO_ACCOUNTS, _seed_content
from .demo_models import DemoSandbox
from .middleware import rate_limit_ip
from .models import Membership, Station, UserProfile
from .task_board import ensure_default_station_tasks

logger = logging.getLogger(__name__)

SESSION_KEY = "demo_sandbox_id"
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
        raise DemoUnavailable(_("Von diesem Anschluss wurden in der letzten Stunde schon viele Demos gestartet. Bitte später erneut versuchen."))


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
    users = {}
    for account in DEMO_ACCOUNTS:
        role_key = account["username"].split("-", 1)[1]
        user = User(
            username=sandbox_username(sandbox, role_key),
            first_name=account["first_name"],
            last_name=account["last_name"],
            is_active=True,
        )
        # Kein Passwort: Die Konten sind nur über den Demo-Einstieg erreichbar.
        user.set_unusable_password()
        user.save()
        Membership.objects.create(user=user, station=station, role=account["role"], is_active=True)
        users[account["username"]] = user
    _seed_content(station, users)
    sandbox.ready_at = timezone.now()
    sandbox.save(update_fields=["ready_at"])
    return sandbox, users


def _enter(request, sandbox: DemoSandbox, user: User):
    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)
    request.session[SESSION_KEY] = sandbox.pk
    # Sitzungs-Cookie endet mit dem Browser; die Demo selbst endet spätestens
    # nach Leerlauf oder Höchstdauer.
    request.session.set_expiry(0)


def start_demo(request):
    """Demo-Wache anlegen, als Master-Admin anmelden und zur Übersicht leiten."""
    try:
        _check_limits(request)
    except DemoUnavailable as exc:
        messages.error(request, str(exc))
        return redirect("login")
    sandbox, users = create_sandbox()
    _enter(request, sandbox, users["demo-admin"])
    return redirect("dashboard")


def switch_role(request, sandbox: DemoSandbox, role_key: str):
    if role_key not in ROLE_KEYS:
        return redirect("dashboard")
    user = User.objects.filter(username=sandbox_username(sandbox, role_key), is_active=True).first()
    if user is not None:
        _enter(request, sandbox, user)
    return redirect("dashboard")


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


def purge_sandbox(sandbox: DemoSandbox) -> int:
    """Demo-Wache mit allen Konten und Einträgen löschen. Gibt die Zeilenzahl zurück.

    Löscht bewusst auch append-only Zeilen (Kaffeekasse, Audit) – aber nur die
    der Demo-Wache und nur, wenn der Datenbank-Benutzer das darf.
    """
    station_ids = [sandbox.station_id]
    with transaction.atomic():
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


def purge_expired() -> int:
    purged = 0
    for sandbox in list(expired_sandboxes().select_related("station")):
        purge_sandbox(sandbox)
        purged += 1
    return purged


def landing_after_demo(reason: str = "ende") -> str:
    return f"{reverse('landing')}?{urlencode({'demo': reason})}"


class DemoSandboxMiddleware:
    """Hängt die Demo-Wache an den Request, beendet abgelaufene Demos und
    sperrt Bereiche, die über die eigene Demo-Wache hinaus wirken."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.demo_sandbox = None
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
        return self.get_response(request)

    @staticmethod
    def _sandbox(request):
        sandbox_id = request.session.get(SESSION_KEY)
        if sandbox_id is not None:
            sandbox = DemoSandbox.objects.filter(pk=sandbox_id).first()
            if sandbox is not None and Membership.objects.filter(
                station_id=sandbox.station_id, user_id=request.user.pk
            ).exists():
                return sandbox
        sandbox = sandbox_for_user(request.user)
        if sandbox is not None:
            request.session[SESSION_KEY] = sandbox.pk
        return sandbox

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        sandbox = request.demo_sandbox
        if sandbox is None:
            return None
        name = match.url_name if match else None
        if name in BLOCKED_URL_NAMES:
            messages.info(request, _("Dieser Bereich ist in der Demo gesperrt, weil er über die eigene Demo-Wache hinaus wirkt."))
            return redirect("dashboard")
        if request.method == "POST" and name not in WRITE_EXEMPT_URL_NAMES:
            refusal = write_refusal(request, sandbox)
            if refusal:
                messages.error(request, refusal)
                back = request.META.get("HTTP_REFERER", "")
                if back and url_has_allowed_host_and_scheme(back, {request.get_host()}, require_https=request.is_secure()):
                    return redirect(back)
                return redirect("dashboard")
        return None


ROLE_LABELS = {account["username"].split("-", 1)[1]: account["label"] for account in DEMO_ACCOUNTS}


def demo_banner(request) -> dict | None:
    """Angaben für das Demo-Banner: Ende der Demo und Rollenwechsel."""
    sandbox = getattr(request, "demo_sandbox", None)
    if sandbox is None:
        return None
    prefix = f"demo-{sandbox.token}-"
    username = getattr(request.user, "username", "")
    return {
        "ends_at": timezone.localtime(ends_at(sandbox)),
        "idle_minutes": settings.DEMO_SANDBOX_IDLE_MINUTES,
        "role": username[len(prefix):] if username.startswith(prefix) else "",
        "roles": [(key, ROLE_LABELS[key]) for key in ROLE_KEYS],
    }


@require_POST
def switch_role_view(request):
    sandbox = getattr(request, "demo_sandbox", None)
    if sandbox is None:
        return redirect("landing")
    return switch_role(request, sandbox, request.POST.get("role", ""))


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
    from .mpg_models import DeviceRoutineCheck
    from .models import CoffeeEntry, HandoverEntry
    from .wachalltag_models import Defect, HandoverAck

    station_id, since = sandbox.station_id, sandbox.ready_at
    steps = [
        {
            "key": "overview",
            "title": _("Übersicht lesen"),
            "text": _("Oben steht, was die Schicht wissen muss: dringende Übergaben, fällige Fristen, knappes Material."),
            "url": reverse("dashboard"),
            "done": True,
        },
        {
            "key": "handover",
            "title": _("Übergabe für die nächste Schicht anlegen"),
            "text": _("Zum Beispiel „Sauerstoff RTW 2 fast leer“, Dringlichkeit „Dringend“."),
            "url": reverse("handover_create"),
            "done": HandoverEntry.objects.filter(station_id=station_id, created_at__gt=since).exists(),
        },
        {
            "key": "ack",
            "title": _("Als Kollegin quittieren"),
            "text": _("Oben im Banner zur Rolle „Mitglied“ wechseln und eine Übergabe als gelesen bestätigen."),
            "url": reverse("handover_list"),
            "done": HandoverAck.objects.filter(station_id=station_id, created_at__gt=since).exists(),
        },
        {
            "key": "device",
            "title": _("Medizingerät prüfen"),
            "text": _("Ein Gerät öffnen und die Funktionskontrolle eintragen – so entsteht nebenbei der Nachweis für die nächste Prüfung."),
            "url": reverse("mpg_dashboard"),
            "done": DeviceRoutineCheck.objects.filter(station_id=station_id, checked_at__gt=since).exists(),
        },
        {
            "key": "defect",
            "title": _("Mangel melden"),
            "text": _("Etwas ist kaputt? Mangel mit Frist und verantwortlicher Person anlegen."),
            "url": reverse("defect_create_web"),
            "done": Defect.objects.filter(station_id=station_id, created_at__gt=since).exists(),
        },
        {
            "key": "coffee",
            "title": _("Kaffeekasse bezahlen"),
            "text": _("„Ich habe bezahlt“ antippen – der Monat ist sofort abgehakt, ganz ohne Zettel."),
            "url": reverse("coffee"),
            "done": CoffeeEntry.objects.filter(
                station_id=station_id, kind=CoffeeEntry.Kind.PAYMENT, created_at__gt=since,
            ).exists(),
        },
    ]
    done = sum(1 for step in steps if step["done"])
    next_step = next((step for step in steps if not step["done"]), None)
    return {"steps": steps, "done": done, "total": len(steps), "complete": next_step is None, "next": next_step}
