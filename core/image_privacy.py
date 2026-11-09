from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import HandoverAttachment, NewsAttachment, PinboardAttachment
from .wachalltag_models import DefectAttachment

MAX_SANITIZED_BYTES = 2 * 1024 * 1024


def sanitize_defect_image(raw: bytes) -> bytes:
    """Return a fresh metadata-free JPEG made only from decoded pixels.

    EXIF orientation is applied before metadata is discarded. Re-encoding is
    intentionally server-side so Web, mobile and older clients receive the same
    privacy guarantee. The output is bounded to the existing 2 MiB domain
    limit; very large/high-entropy images are progressively resized.
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
            else:
                rgb = oriented.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError("Bild konnte für den Datenschutz nicht neu codiert werden.") from exc

    # Fresh pixel-only image: no EXIF/GPS/XMP/text/ICC objects are copied.
    # paste() avoids materialising a second Python list for every source pixel.
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)

    quality_steps = (88, 82, 76, 70, 64, 58, 52)
    current = clean
    for _ in range(8):
        for quality in quality_steps:
            output = BytesIO()
            current.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
            encoded = output.getvalue()
            if encoded and len(encoded) <= MAX_SANITIZED_BYTES:
                return encoded
        width, height = current.size
        if width <= 640 and height <= 640:
            break
        current.thumbnail(
            (max(640, int(width * 0.85)), max(640, int(height * 0.85))),
            Image.Resampling.LANCZOS,
        )

    raise ValueError("Datenschutzbereinigtes Bild überschreitet weiterhin 2 MiB.")


@receiver(pre_save, sender=DefectAttachment, dispatch_uid="sanitize_defect_attachment_privacy")
def sanitize_defect_attachment(sender, instance: DefectAttachment, **kwargs):
    if not instance.data:
        return
    # PDFs werden nicht neu gerendert; ihre Prüfung passiert bei der Annahme.
    if instance.content_type == "application/pdf":
        return
    sanitized = sanitize_defect_image(bytes(instance.data))
    instance.data = sanitized
    instance.size = len(sanitized)
    instance.content_type = "image/jpeg"


def _strip_metadata_before_save(instance) -> None:
    """Zweite Sicherung für Anhänge, die nicht über ``read_upload`` kommen.

    Die Ansichten schreiben Bilder schon beim Annehmen neu (core/attachments.py).
    Trägt ein lesbares Bild beim Speichern trotzdem Metadaten (anderer
    Codepfad, Import), wird es hier neu geschrieben; geht das nicht, schlägt
    das Speichern fehl, statt das Original abzulegen. Nicht lesbare Daten
    tragen keine lesbaren Metadaten und bleiben unverändert.
    """
    from .attachments import image_has_metadata, normalize_image_to_jpeg

    if not instance.data or instance.content_type == "application/pdf":
        return
    raw = bytes(instance.data)
    if not image_has_metadata(raw):
        return
    clean = normalize_image_to_jpeg(raw)
    instance.data = clean
    instance.size = len(clean)
    instance.content_type = "image/jpeg"
    # Model.save() hat die Endung schon aus dem alten Typ gebildet (läuft vor
    # diesem Signal); der Inhalt ist jetzt JPEG, also auch der Name.
    stem = (instance.filename or "anhang").rsplit(".", 1)[0].strip(" .") or "anhang"
    instance.filename = f"{stem[:170]}.jpg"


@receiver(pre_save, sender=HandoverAttachment, dispatch_uid="strip_handover_attachment_metadata")
@receiver(pre_save, sender=PinboardAttachment, dispatch_uid="strip_pinboard_attachment_metadata")
@receiver(pre_save, sender=NewsAttachment, dispatch_uid="strip_news_attachment_metadata")
def strip_attachment_metadata(sender, instance, **kwargs):
    _strip_metadata_before_save(instance)
