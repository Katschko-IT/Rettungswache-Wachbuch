from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ApiToken,
    AuditEvent,
    BirthdayPreference,
    FeedItem,
    HandoverEntry,
    HandoverRevision,
    PinboardNote,
)
from .push import notify_urgent_handover


def audit(actor, station, action, obj, metadata=None):
    return AuditEvent.objects.create(
        actor=actor,
        station=station,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        metadata=metadata or {},
    )


def revoke_api_tokens_for_user(user) -> int:
    """Deactivate all active app tokens for a user (e.g. after password change)."""
    return ApiToken.objects.filter(user=user, is_active=True).update(is_active=False)


# Field names whose values must never appear in auditor-visible metadata.
AUDIT_REDACT_VALUES = frozenset({
    "iban",
    "bic",
    "payment_note",
    "paypal_me_url",
    "wero_link",
    "waste_calendar_url",
})


def structure_changes(before, after, *, redact_values=AUDIT_REDACT_VALUES):
    """Build a safe before/after map for structured fields (no free text)."""
    changes = {}
    for key, old in before.items():
        new = after.get(key)
        if old != new:
            if key in redact_values:
                changes[key] = {"changed": True}
            else:
                changes[key] = {"from": old, "to": new}
    return changes


def handover_snapshot(handover):
    return {
        "category": handover.category,
        "priority": handover.priority,
        "status": handover.status,
        "title": handover.title,
        "details": handover.details,
    }


@transaction.atomic
def create_handover(form, membership):
    handover = form.save(commit=False)
    handover.station = membership.station
    handover.author = membership.user
    handover.save()
    HandoverRevision.objects.create(
        handover=handover,
        version=handover.version,
        snapshot=handover_snapshot(handover),
        changed_by=membership.user,
    )
    audit(membership.user, membership.station, "handover.created", handover, {
        "fields": ["category", "priority", "title", "details"],
    })
    notify_urgent_handover(handover, membership.user)
    return handover


@transaction.atomic
def change_handover_status(handover, status, membership):
    locked = HandoverEntry.objects.select_for_update().get(pk=handover.pk)
    if locked.status == status:
        return locked
    before = {"status": locked.status}
    locked.status = status
    locked.version += 1
    locked.completed_at = timezone.now() if status == HandoverEntry.Status.DONE else None
    locked.save(update_fields=["status", "version", "completed_at", "updated_at"])
    HandoverRevision.objects.create(
        handover=locked,
        version=locked.version,
        snapshot=handover_snapshot(locked),
        changed_by=membership.user,
    )
    audit(membership.user, membership.station, "handover.status_changed", locked, {
        "fields": ["status"],
        "version": locked.version,
        "changes": structure_changes(before, {"status": locked.status}),
    })
    return locked


@transaction.atomic
def update_handover_content(handover, cleaned_data, membership):
    """Controlled content correction: new revision, audit without free-text copies."""
    locked = HandoverEntry.objects.select_for_update().get(pk=handover.pk)
    before = {
        "category": locked.category,
        "priority": locked.priority,
    }
    field_names = []
    for field in ("category", "priority", "title", "details"):
        if field in cleaned_data and getattr(locked, field) != cleaned_data[field]:
            setattr(locked, field, cleaned_data[field])
            field_names.append(field)
    if not field_names:
        return locked
    locked.version += 1
    locked.save(update_fields=[*field_names, "version", "updated_at"])
    HandoverRevision.objects.create(
        handover=locked,
        version=locked.version,
        snapshot=handover_snapshot(locked),
        changed_by=membership.user,
    )
    after = {
        "category": locked.category,
        "priority": locked.priority,
    }
    audit(membership.user, membership.station, "handover.content_updated", locked, {
        "fields": field_names,
        "version": locked.version,
        "changes": structure_changes(before, after),
    })
    if locked.priority == HandoverEntry.Priority.URGENT and "priority" in field_names:
        notify_urgent_handover(locked, membership.user)
    return locked


@transaction.atomic
def acknowledge_handover(handover, user):
    """Übergabe als gelesen quittieren (Web und App). Gibt (Quittung, neu?) zurück."""
    from .wachalltag_models import HandoverAck

    ack, created = HandoverAck.objects.get_or_create(station=handover.station, handover=handover, user=user)
    if created:
        audit(user, handover.station, "handover.acknowledged", handover, {"handover": handover.pk})
    return ack, created


@transaction.atomic
def clear_birthday_on_exit(user, station, actor):
    """Withdraw birthday visibility and clear day/month when membership ends."""
    preferences = list(
        BirthdayPreference.objects.select_for_update().filter(user=user, station=station)
    )
    cleared = 0
    for preference in preferences:
        if not preference.is_visible and preference.day is None and preference.month is None:
            continue
        before = {
            "is_visible": preference.is_visible,
            "had_date": bool(preference.day and preference.month),
        }
        preference.is_visible = False
        preference.day = None
        preference.month = None
        preference.consented_at = None
        preference.withdrawn_at = timezone.now()
        preference.save(update_fields=[
            "is_visible", "day", "month", "consented_at", "withdrawn_at", "updated_at",
        ])
        audit(actor, station, "birthday.withdrawn_on_exit", preference, {
            "fields": ["is_visible", "day", "month"],
            "changes": structure_changes(before, {"is_visible": False, "had_date": False}),
        })
        cleared += 1
    return cleared


def apply_feed_retention(now=None):
    """Delete feed items not seen within RETENTION_FEED_DAYS. Returns deleted count."""
    days = int(getattr(settings, "RETENTION_FEED_DAYS", 0) or 0)
    if days <= 0:
        return 0
    now = now or timezone.now()
    cutoff = now - timedelta(days=days)
    deleted, _ = FeedItem.objects.filter(last_seen_at__lt=cutoff).delete()
    return deleted


def apply_audit_retention(now=None):
    """
    Optionally purge old audit rows when RETENTION_AUDIT_DAYS > 0.

    Default is 0 (disabled): AuditEvent.delete() is blocked for normal use;
    bulk retention must be intentional and run with owner DB rights.
    """
    days = int(getattr(settings, "RETENTION_AUDIT_DAYS", 0) or 0)
    if days <= 0:
        return 0
    now = now or timezone.now()
    cutoff = now - timedelta(days=days)
    # QuerySet.delete bypasses model.delete(); intended for owner-run retention only.
    deleted, _ = AuditEvent.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def apply_retention(now=None):
    return {
        "feed_items": apply_feed_retention(now=now),
        "audit_events": apply_audit_retention(now=now),
        "push_outbox": apply_pushoutbox_retention(now=now),
        "feedback": _feedback_retention(now),
    }


def _feedback_retention(now):
    from .feedback import apply_feedback_retention

    return apply_feedback_retention(now=now)


def apply_pushoutbox_retention(now=None, days=None):
    """Delete terminal push-outbox rows older than ``days``.

    ``days`` defaults to ``PushOutbox.RETENTION_DAYS`` (30). Returns the
    number of removed rows. ``0`` or a negative value disables retention.
    """
    from .models import PushOutbox

    if days is None:
        days = PushOutbox.RETENTION_DAYS
    days = int(days or 0)
    if days <= 0:
        return 0
    now = now or timezone.now()
    cutoff = now - timedelta(days=days)
    deleted, _ = PushOutbox.objects.filter(
        status__in=[
            PushOutbox.Status.SENT,
            PushOutbox.Status.DISCARDED,
            PushOutbox.Status.FAILED,
        ],
        created_at__lt=cutoff,
    ).delete()
    return deleted


# --- Pinnwand (digitale Aushaenge) -----------------------------------------

@transaction.atomic
def create_pinboard_note(*, station, author, title, body, category):
    note = PinboardNote.objects.create(
        station=station,
        author=author,
        title=title,
        body=body,
        category=category,
    )
    audit(author, station, "pinboard.note_created", note, {
        "fields": ["title", "category"],
    })
    return note


@transaction.atomic
def update_pinboard_note(note, *, actor, title, body, category):
    locked = PinboardNote.objects.select_for_update().get(pk=note.pk)
    locked.title = title
    locked.body = body
    locked.category = category
    locked.save(update_fields=["title", "body", "category", "updated_at"])
    audit(actor, locked.station, "pinboard.note_updated", locked, {
        "fields": ["title", "category"],
    })
    return locked


@transaction.atomic
def set_pinboard_pin(note, *, actor, pinned):
    locked = PinboardNote.objects.select_for_update().get(pk=note.pk)
    if locked.is_pinned == pinned:
        return locked
    locked.is_pinned = pinned
    locked.save(update_fields=["is_pinned", "updated_at"])
    audit(actor, locked.station, "pinboard.note_pinned", locked, {
        "fields": ["is_pinned"],
        "is_pinned": pinned,
    })
    return locked


@transaction.atomic
def archive_pinboard_note(note, *, actor):
    locked = PinboardNote.objects.select_for_update().get(pk=note.pk)
    if locked.is_archived:
        return locked
    locked.is_archived = True
    locked.save(update_fields=["is_archived", "updated_at"])
    audit(actor, locked.station, "pinboard.note_archived", locked, {
        "fields": ["is_archived"],
    })
    return locked
