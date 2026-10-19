"""Anhänge bei Übergaben: Bilder und PDFs, wachengebunden und unveränderlich."""
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from core.models import HandoverAttachment, HandoverEntry, Membership, Station

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (40, 30), (30, 80, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


class HandoverAttachmentTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Anhang", slug="anhang")
        self.other = Station.objects.create(name="Fremd", slug="fremd")
        self.user = User.objects.create_user("att-user", password="Att-Test-12345")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.handover = HandoverEntry.objects.create(
            station=self.station,
            author=self.user,
            category=HandoverEntry.Category.STATION,
            priority=HandoverEntry.Priority.NORMAL,
            title="Fahrzeug 1",
            details="Tank leer",
        )
        self.client.force_login(self.user)
        self.url = f"/uebergaben/{self.handover.pk}/"

    def upload(self, name, content, content_type):
        return self.client.post(self.url, {
            "action": "upload",
            "attachment": SimpleUploadedFile(name, content, content_type=content_type),
        })

    def test_pdf_upload_is_stored(self):
        response = self.upload("bericht.pdf", PDF, "application/pdf")
        self.assertEqual(response.status_code, 302)
        attachment = HandoverAttachment.objects.get(handover=self.handover)
        self.assertEqual(attachment.content_type, "application/pdf")
        self.assertTrue(attachment.filename.endswith(".pdf"))
        self.assertEqual(bytes(attachment.data), PDF)

    def test_jpeg_upload_is_stored(self):
        response = self.upload("foto.jpg", jpeg_bytes(), "image/jpeg")
        self.assertEqual(response.status_code, 302)
        attachment = HandoverAttachment.objects.get(handover=self.handover)
        self.assertTrue(attachment.filename.endswith(".jpg"))

    def test_fake_pdf_is_rejected(self):
        response = self.upload("boese.pdf", b"<html>kein pdf</html>", "application/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HandoverAttachment.objects.filter(handover=self.handover).exists())

    def test_other_type_is_rejected(self):
        response = self.upload("tool.exe", b"MZ...", "application/octet-stream")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HandoverAttachment.objects.exists())

    def test_download_is_station_bound(self):
        self.upload("bericht.pdf", PDF, "application/pdf")
        attachment = HandoverAttachment.objects.get()
        self.assertEqual(self.client.get(f"/uebergaben/anhaenge/{attachment.pk}/").status_code, 200)

        stranger = User.objects.create_user("stranger", password="Stranger-12345")
        Membership.objects.create(user=stranger, station=self.other, role=Membership.Role.MEMBER)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(f"/uebergaben/anhaenge/{attachment.pk}/").status_code, 404)

    def test_attachment_cannot_be_changed(self):
        self.upload("bericht.pdf", PDF, "application/pdf")
        attachment = HandoverAttachment.objects.get()
        attachment.filename = "anders.pdf"
        with self.assertRaises(Exception):
            attachment.save()
