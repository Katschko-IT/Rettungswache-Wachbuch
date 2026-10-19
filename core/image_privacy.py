from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from django.db.models.signals import pre_save
from django.dispatch import receiver

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
