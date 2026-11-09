"""Gemeinsame Prüfung für Bild- und PDF-Anhänge.

Jeder Bild-Anhang (Übergabe, auch Fotos nachgetragener Papiereinträge,
Pinnwand, Neuigkeiten, Mangel) wird vor dem Speichern aus den decodierten
Bildpunkten neu als JPEG geschrieben: Ohne EXIF, GPS-Position, Kamera,
Aufnahmezeit, XMP oder Kommentare. Lässt sich ein Bild nicht neu schreiben,
wird es abgelehnt statt im Original gespeichert. PDFs werden nur geprüft.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from PIL import Image, ImageOps, UnidentifiedImageError
from django.utils.translation import gettext, gettext_lazy as _

from .api.wachalltag import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    attachment_is_valid,
)

UPLOAD_ERROR_TYPE = _("Erlaubt sind JPEG, PNG, WebP und PDF.")
UPLOAD_ERROR_SIZE = _("Datei darf maximal 5 MiB groß sein.")
UPLOAD_ERROR_INVALID = _("Datei ist kein gültiges Bild und kein lesbares PDF.")
UPLOAD_ERROR_REENCODE = _(
    "Das Bild konnte nicht ohne Metadaten gespeichert werden. Bitte ein anderes Foto wählen."
)
UPLOAD_ERROR_MISSING = _("Bitte eine Datei auswählen.")


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


# Angaben, die ein frisch von Pillow geschriebenes JPEG von sich aus trägt.
_PLAIN_JPEG_INFO = {"jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi", "progressive", "progression"}


def image_has_metadata(raw: bytes) -> bool | None:
    """Trägt das Bild Metadaten (EXIF, XMP, ICC, Kommentar) oder ist es kein JPEG?

    Liest nur den Kopf der Datei. ``None``: kein lesbares Bild (dann gibt es
    auch keine lesbaren Metadaten; die Ansichten nehmen so etwas nicht an).
    """
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format != "JPEG":
                return True
            if set(image.info) - _PLAIN_JPEG_INFO:
                return True
            return bool(image.getexif())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def jpeg_filename(name: str) -> str:
    """Dateiname mit Endung .jpg (der Inhalt ist nach dem Neuschreiben JPEG)."""
    stem = PurePath(name or "foto").stem or "foto"
    return f"{stem}.jpg"[:180]


@dataclass(frozen=True)
class PreparedUpload:
    """Geprüfter Anhang, bereit zum Speichern (Bilder ohne Metadaten)."""

    name: str
    content_type: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)


def read_upload(upload):
    """Liest eine Datei, prüft Typ, Größe und Inhalt, entfernt Bild-Metadaten.

    Rückgabe: ``(PreparedUpload, fehler)`` – genau einer der beiden Werte ist
    gesetzt. Ein Bild, das sich nicht neu schreiben lässt, wird abgelehnt.
    """
    if upload is None:
        return None, gettext(UPLOAD_ERROR_MISSING)
    if upload.content_type not in ALLOWED_ATTACHMENT_TYPES:
        return None, gettext(UPLOAD_ERROR_TYPE)
    if upload.size > MAX_ATTACHMENT_BYTES:
        return None, gettext(UPLOAD_ERROR_SIZE)
    raw = upload.read()
    if not attachment_is_valid(raw, upload.content_type):
        return None, gettext(UPLOAD_ERROR_INVALID)
    name = (upload.name or "datei")[:180]
    if upload.content_type == "application/pdf":
        return PreparedUpload(name=name, content_type="application/pdf", data=raw), None
    try:
        clean = normalize_image_to_jpeg(raw)
    except ValueError:
        return None, gettext(UPLOAD_ERROR_REENCODE)
    return PreparedUpload(name=jpeg_filename(name), content_type="image/jpeg", data=clean), None


def read_uploads(files, limit=8):
    """Prüft mehrere Dateien; liefert (liste, fehler) mit höchstens ``limit`` Einträgen."""
    files = [item for item in (files or []) if item is not None]
    if not files:
        return [], None
    if len(files) > limit:
        return [], gettext("Es sind höchstens %(limit)s Anhänge möglich.") % {"limit": limit}
    ready = []
    for upload in files:
        prepared, error = read_upload(upload)
        if error:
            return [], error
        ready.append(prepared)
    return ready, None
