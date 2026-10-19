from io import BytesIO

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .image_privacy import sanitize_defect_image
from .models import Membership, Station
from .wachalltag_models import Defect, DefectAttachment


class DefectImagePrivacyTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Bild", slug="wache-bild")
        self.user = User.objects.create_user(username="fototest", password="not-used-here")
        self.defect = Defect.objects.create(
            station=self.station,
            title="Testmangel",
            created_by=self.user,
        )

    def _jpeg_with_exif(self):
        source = Image.new("RGB", (48, 32), "red")
        exif = Image.Exif()
        exif[0x010E] = "SECRET-DESCRIPTION"
        exif[0x010F] = "SECRET-CAMERA"
        output = BytesIO()
        source.save(output, format="JPEG", quality=92, exif=exif)
        raw = output.getvalue()
        with Image.open(BytesIO(raw)) as check:
            self.assertGreater(len(check.getexif()), 0)
        return raw

    def test_attachment_is_reencoded_without_source_exif(self):
        raw = self._jpeg_with_exif()

        item = DefectAttachment.objects.create(
            defect=self.defect,
            station=self.station,
            filename="beweis.original.jpg",
            content_type="image/jpeg",
            data=raw,
            size=len(raw),
            uploaded_by=self.user,
        )
        item.refresh_from_db()

        stored = bytes(item.data)
        self.assertEqual(item.content_type, "image/jpeg")
        self.assertEqual(item.filename, "beweis.original.jpg")
        self.assertEqual(item.size, len(stored))
        self.assertLessEqual(item.size, 2 * 1024 * 1024)
        with Image.open(BytesIO(stored)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(len(image.getexif()), 0)
            self.assertNotIn("SECRET-DESCRIPTION", repr(image.info))
            self.assertNotIn("SECRET-CAMERA", repr(image.info))

    def test_png_is_normalized_to_metadata_free_jpeg(self):
        source = Image.new("RGBA", (16, 16), (255, 0, 0, 128))
        output = BytesIO()
        source.save(output, format="PNG")
        raw = output.getvalue()

        item = DefectAttachment.objects.create(
            defect=self.defect,
            station=self.station,
            filename="transparent.png",
            content_type="image/png",
            data=raw,
            size=len(raw),
            uploaded_by=self.user,
        )
        item.refresh_from_db()

        self.assertEqual(item.content_type, "image/jpeg")
        self.assertEqual(item.filename, "transparent.jpg")
        with Image.open(BytesIO(bytes(item.data))) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(len(image.getexif()), 0)


class SanitizeDecompressionBombTests(TestCase):
    def test_bomb_is_mapped_to_value_error(self):
        source = Image.new("RGB", (48, 32), "red")
        output = BytesIO()
        source.save(output, format="JPEG", quality=92)
        raw = output.getvalue()

        original_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = 500
        self.addCleanup(lambda: setattr(Image, "MAX_IMAGE_PIXELS", original_limit))

        with self.assertRaises(ValueError):
            sanitize_defect_image(raw)


class DefectWebUploadPrivacyTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Web", slug="wache-web")
        self.user = User.objects.create_user(username="webupload", password="web-password")
        Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.MEMBER,
        )
        self.defect = Defect.objects.create(
            station=self.station,
            title="Webmangel",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        self.url = f"/maengel/{self.defect.pk}/"

    def test_corrupt_image_is_rejected_with_friendly_error(self):
        corrupt = b"\xff\xd8\xff" + b"not-a-real-jpeg" * 32
        upload = SimpleUploadedFile("kaputt.jpg", corrupt, content_type="image/jpeg")

        response = self.client.post(self.url, {"action": "upload", "attachment": upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datei ist kein gültiges Bild und kein lesbares PDF.")
        self.assertEqual(DefectAttachment.objects.count(), 0)

    def test_web_upload_strips_exif_like_api(self):
        source = Image.new("RGB", (48, 32), "blue")
        exif = Image.Exif()
        exif[0x010E] = "SECRET-WEB-DESCRIPTION"
        output = BytesIO()
        source.save(output, format="JPEG", quality=92, exif=exif)
        raw = output.getvalue()
        upload = SimpleUploadedFile("webfoto.jpg", raw, content_type="image/jpeg")

        response = self.client.post(self.url, {"action": "upload", "attachment": upload})

        self.assertEqual(response.status_code, 302)
        item = DefectAttachment.objects.get()
        self.assertEqual(item.content_type, "image/jpeg")
        self.assertEqual(item.filename, "webfoto.jpg")
        with Image.open(BytesIO(bytes(item.data))) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(len(image.getexif()), 0)
            self.assertNotIn("SECRET-WEB-DESCRIPTION", repr(image.info))
