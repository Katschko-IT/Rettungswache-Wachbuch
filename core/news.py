"""Neuigkeiten: Leserschaft, Quittungen und automatische Archivierung."""
from __future__ import annotations

from django.utils import timezone

from .models import Membership, NewsAcknowledgement, NewsPost


def news_audience_ids(station):
    """Alle aktiven Mitglieder, die eine Neuigkeit lesen müssen.

    Ohne Auditor und ohne das Dienstkonto „Wachenterminal“: Lesebestätigungen
    sind persönlich (AGENTS.md §4).
    """
    from .terminal_models import StationTerminalCode

    service_ids = StationTerminalCode.objects.filter(station=station).values_list("service_user_id", flat=True)
    return set(
        Membership.objects.filter(station=station, is_active=True)
        .exclude(role=Membership.Role.AUDITOR)
        .exclude(user_id__in=service_ids)
        .values_list("user_id", flat=True)
    )


def acknowledgement_status(post):
    """Wie viele der Leserschaft haben quittiert?"""
    audience = news_audience_ids(post.station)
    acknowledged = set(
        NewsAcknowledgement.objects.filter(post=post).values_list("user_id", flat=True)
    )
    read = len(audience & acknowledged)
    total = len(audience)
    return {
        "read": read,
        "total": total,
        "missing": sorted(audience - acknowledged),
        "complete": total > 0 and read >= total,
    }


def acknowledge(post, user):
    """Quittiert eine Neuigkeit und archiviert sie, wenn alle gelesen haben."""
    NewsAcknowledgement.objects.get_or_create(post=post, user=user)
    status = acknowledgement_status(post)
    if status["complete"] and post.archived_at is None:
        post.archived_at = timezone.now()
        post.save(update_fields=["archived_at"])
    return status


def archive_if_complete(post):
    """Nach Neueintritt/Austritt prüfen, ob die Neuigkeit ins Archiv gehört."""
    status = acknowledgement_status(post)
    if status["complete"] and post.archived_at is None:
        post.archived_at = timezone.now()
        post.save(update_fields=["archived_at"])
    return status


def active_posts(station):
    return NewsPost.objects.filter(station=station, archived_at__isnull=True)


def archived_posts(station):
    return NewsPost.objects.filter(station=station, archived_at__isnull=False)
