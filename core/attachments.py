"""Gemeinsame Prüfung für Bild- und PDF-Anhänge."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from .api.wachalltag import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    attachment_is_valid,
)

UPLOAD_ERROR_TYPE = "Erlaubt sind JPEG, PNG, WebP und PDF."
UPLOAD_ERROR_SIZE = "Datei darf maximal 5 MiB groß sein."
UPLOAD_ERROR_INVALID = "Datei ist kein gültiges Bild und kein lesbares PDF."


def normalize_image_to_jpeg(raw: bytes) -> bytes:
    """Return a fresh metadata-free JPEG made only from decoded pixels.

    EXIF orientation is applied before metadata is discarded. Transparent
    images (RGBA, LA, P with transparency) are composited onto a white
    background. The output is saved as JPEG at quality=85 without EXIF.
    """
    try:
        with Image.open(BytesIO(raw)) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            if oriented.mode in {"RGBA", "LA"} or (
                oriented.mode == "P" and "transparency" in oriented.info
            ):
                rgba = oriented.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            elif oriented.mode != "RGB":
                rgb = oriented.convert("RGB")
            else:
                rgb = oriented
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Bild konnte nicht decodiert werden: {exc}") from exc

    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    out = BytesIO()
    clean.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


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
