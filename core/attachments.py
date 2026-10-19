"""Gemeinsame Prüfung für Bild- und PDF-Anhänge."""
from __future__ import annotations

from .api.wachalltag import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    attachment_is_valid,
)

UPLOAD_ERROR_TYPE = "Erlaubt sind JPEG, PNG, WebP und PDF."
UPLOAD_ERROR_SIZE = "Datei darf maximal 5 MiB groß sein."
UPLOAD_ERROR_INVALID = "Datei ist kein gültiges Bild und kein lesbares PDF."


def read_upload(upload):
    """Liest eine Datei und prüft Typ, Größe und Inhalt.

    Rückgabe: ``(rohdaten, fehler)`` – genau einer der beiden Werte ist gesetzt.
    """
    if upload is None:
        return None, "Bitte eine Datei auswählen."
    if upload.content_type not in ALLOWED_ATTACHMENT_TYPES:
        return None, UPLOAD_ERROR_TYPE
    if upload.size > MAX_ATTACHMENT_BYTES:
        return None, UPLOAD_ERROR_SIZE
    raw = upload.read()
    if not attachment_is_valid(raw, upload.content_type):
        return None, UPLOAD_ERROR_INVALID
    return raw, None


def read_uploads(files, limit=8):
    """Prüft mehrere Dateien; liefert (liste, fehler) mit höchstens ``limit`` Einträgen."""
    files = [item for item in (files or []) if item is not None]
    if not files:
        return [], None
    if len(files) > limit:
        return [], f"Es sind höchstens {limit} Anhänge möglich."
    ready = []
    for upload in files:
        raw, error = read_upload(upload)
        if error:
            return [], error
        ready.append((upload, raw))
    return ready, None
