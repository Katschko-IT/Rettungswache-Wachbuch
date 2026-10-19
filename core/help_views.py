"""Produkthilfe (offline) und geschuetzte System-/Versionsseite.

Hilfe: angemeldete Mitglieder sehen die mitgelieferten Produktartikel in ihrer
Sprache. Die Artikel stammen ausschliesslich aus dem kuratierten Manifest
``core/help_data/articles.json``; es gibt keinen frei waehlbaren Dateipfad.

System: nur Wachenadministration. Es werden ausschliesslich minimale,
serverseitige Read-only-Pruefungen angezeigt (DB-Ping, Migrationssummary,
Cachetyp). Keine Shell-, Git- oder Dockeraufrufe, keine externen HTTP-Aufrufe,
keine Umgebungsvariablen, Pfade oder Rohlogs.
"""

from __future__ import annotations

import os
import re

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .access import membership_required
from .help import HelpContentError, get_article, get_articles, manifest_revision, search
from .i18n import request_language
from .models import Membership

_BUILD_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_MAX_QUERY_LENGTH = 120


def build_commit() -> str | None:
    """Liefert die Build-/Commitkennung nur bei syntaktisch gueltigem Hexwert."""
    raw = (os.getenv("APP_BUILD_COMMIT") or "").strip()
    if not raw or not _BUILD_COMMIT_RE.fullmatch(raw):
        return None
    return raw.lower()


def _database_status() -> dict[str, object]:
    """Minimaler Read-only-Ping; Fehlertexte werden nicht nach aussen gegeben."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        reachable = True
    except Exception:  # noqa: BLE001 - Diagnose darf die Seite nicht abbrechen
        reachable = False
    return {"reachable": reachable}


def _migration_status() -> dict[str, object]:
    """Zaehlt angewendete Migrationen und nennt offene Blattknoten."""
    try:
        recorder = MigrationRecorder(connection)
        applied = set(recorder.applied_migrations())
        loader = MigrationExecutor(connection).loader
        leaves = sorted(loader.graph.leaf_nodes())
        pending = [f"{app}.{name}" for app, name in leaves if (app, name) not in applied]
        return {"applied": len(applied), "pending": pending, "available": True}
    except Exception:  # noqa: BLE001
        return {"applied": None, "pending": [], "available": False}


def _cache_status() -> dict[str, object]:
    config = settings.CACHES.get("default", {})
    backend = str(config.get("BACKEND", ""))
    durable = "redis" in backend.lower()
    return {
        "backend": backend.rsplit(".", 1)[-1] or "unbekannt",
        "durable": durable,
        "location": str(config.get("LOCATION", "")),
    }


@require_GET
@never_cache
@membership_required()
def help_index(request: HttpRequest) -> HttpResponse:
    language = request_language(request)
    raw_query = (request.GET.get("q") or "")[:_MAX_QUERY_LENGTH]
    query = raw_query.strip()
    try:
        results = search(query, language) if query else []
        articles = get_articles(language)
        revision = manifest_revision()
    except HelpContentError:
        results, articles, revision = [], [], ""
    return render(request, "core/help_index.html", {
        "help_articles": articles,
        "help_results": results,
        "help_query": query,
        "help_language": language,
        "help_revision": revision,
        "app_version": settings.APP_VERSION,
        "build_commit": build_commit(),
    })


@require_GET
@never_cache
@membership_required()
def help_article(request: HttpRequest, slug: str) -> HttpResponse:
    language = request_language(request)
    try:
        article = get_article(slug, language)
        revision = manifest_revision()
    except HelpContentError:
        article, revision = None, ""
    if article is None:
        raise Http404("Hilfeartikel nicht gefunden")
    return render(request, "core/help_article.html", {
        "article": article,
        "help_language": language,
        "help_revision": revision,
        "app_version": settings.APP_VERSION,
        "build_commit": build_commit(),
    })


@require_GET
@never_cache
@membership_required({Membership.Role.ADMIN})
def system_status(request: HttpRequest) -> HttpResponse:
    return render(request, "core/system_status.html", {
        "app_version": settings.APP_VERSION,
        "build_commit": build_commit(),
        "database": _database_status(),
        "migrations": _migration_status(),
        "cache": _cache_status(),
        "help_revision": manifest_revision(),
        "release_hint": {
            "version": settings.APP_VERSION,
            "installation": "manuelle Installation durch die Betreiber",
            "automatic_updates": False,
        },
    })
