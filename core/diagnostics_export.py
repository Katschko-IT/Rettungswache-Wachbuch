import os
import re
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from core.diagnostics_models import ErrorEvent
from core.version import APP_VERSION

SUPPORT_EXPORT_FIELDS = (
    "occurred_at",
    "correlation_id",
    "route_name",
    "category",
    "http_status",
    "app_version",
)

BUILD_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _get_build_commit() -> str | None:
    raw = os.getenv("APP_BUILD_COMMIT", "").strip()
    if BUILD_COMMIT_RE.match(raw):
        return raw
    return None


def _check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "erreichbar"
    except Exception:
        return "nicht erreichbar"


def _check_migrations() -> tuple[str, str]:
    applied_str = "nicht ermittelbar"
    unapplied_str = "nicht ermittelbar"

    try:
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
        applied_str = str(len(applied))
    except Exception:
        applied_str = "nicht ermittelbar"

    try:
        executor = MigrationExecutor(connection)
        leaf_nodes = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(leaf_nodes)
        if not plan:
            unapplied_str = "keine"
        else:
            unapplied_str = ", ".join(
                f"{migration.app_label}.{migration.name}" for migration, _ in plan
            )
    except Exception:
        unapplied_str = "nicht ermittelbar"

    return applied_str, unapplied_str


def _check_cache() -> str:
    try:
        backend_path = settings.CACHES["default"]["BACKEND"]
        backend_name = backend_path.split(".")[-1]
        if not backend_name:
            return "nicht ermittelbar"
        persistence = "dauerhaft" if "redis" in backend_path.lower() else "nicht dauerhaft"
        return f"{backend_name} ({persistence})"
    except Exception:
        return "nicht ermittelbar"


def support_filename(now=None) -> str:
    if now is None:
        now = timezone.now()
    local_now = timezone.localtime(now) if timezone.is_aware(now) else now
    return f"wachbuch-support-{local_now.strftime('%Y%m%d-%H%M%S')}.txt"


def retained_error_events(*, station, now=None, limit=None):
    if station is None or getattr(station, "pk", None) is None:
        raise ValueError("Ein gültiger Stationsbezug ist zwingend erforderlich.")
    if now is None:
        now = timezone.now()
    retention_days = int(getattr(settings, "ERROR_EVENT_RETENTION_DAYS", 30))
    cutoff = now - timedelta(days=retention_days)
    queryset = ErrorEvent.objects.filter(
        station=station,
        occurred_at__gte=cutoff,
    ).order_by("-occurred_at", "-id")
    if limit is not None:
        queryset = queryset[:int(limit)]
    return queryset


def build_support_report(*, station, now=None) -> str:
    if station is None or getattr(station, "pk", None) is None:
        raise ValueError("Ein gültiger Stationsbezug ist zwingend erforderlich.")

    if now is None:
        now = timezone.now()

    local_now = timezone.localtime(now) if timezone.is_aware(now) else now
    created_iso = local_now.isoformat()

    commit = _get_build_commit()
    build_commit_str = commit if commit is not None else "nicht hinterlegt"

    db_status = _check_database()
    applied_migrations, unapplied_migrations = _check_migrations()
    cache_status = _check_cache()

    retention_days = int(getattr(settings, "ERROR_EVENT_RETENTION_DAYS", 30))
    export_limit = int(getattr(settings, "ERROR_EVENT_EXPORT_LIMIT", 200))

    events = retained_error_events(station=station, now=now, limit=export_limit)

    lines = [
        "Wachbuch – Supportbericht",
        f"Erstellt: {created_iso}",
        f"Wache: {station.name}",
        f"Produktversion: {APP_VERSION}",
        f"Build-Kennung: {build_commit_str}",
        f"Datenbank: {db_status}",
        f"Angewendete Migrationen: {applied_migrations}",
        f"Offene Migrationen: {unapplied_migrations}",
        f"Zwischenspeicher: {cache_status}",
        f"Aufbewahrung Fehlerereignisse: {retention_days} Tage (technische Richtlinie)",
        "",
        f"Bereinigte Fehlerereignisse (max. {export_limit}, nur diese Wache)",
        "Zeitpunkt | Korrelations-ID | Route | Kategorie | HTTP-Status | Softwareversion",
    ]

    for event in events:
        local_occurred = (
            timezone.localtime(event.occurred_at)
            if timezone.is_aware(event.occurred_at)
            else event.occurred_at
        )
        occurred_iso = local_occurred.isoformat()
        category_display = event.get_category_display()
        lines.append(
            f"{occurred_iso} | {event.correlation_id} | {event.route_name} | "
            f"{category_display} | {event.http_status} | {event.app_version}"
        )

    return "\n".join(lines) + "\n"
