"""Neuigkeiten: Anlegen, Quittieren, automatische Archivierung."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import (
    Membership,
    NewsAcknowledgement,
    NewsAttachment,
    NewsPost,
    Station,
)
from core.news import acknowledge, acknowledgement_status

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class NewsTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="News", slug="news")
        self.admin = User.objects.create_user("news-admin", password="News-Test-12345")
        self.member = User.objects.create_user("news-member", password="News-Test-12345")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.post = NewsPost.objects.create(
            station=self.station, title="Neue Fahrzeugordnung", body="Ab Montag gilt die neue Ordnung.",
            created_by=self.admin,
        )

    def test_audience_and_status(self):
        status = acknowledgement_status(self.post)
        self.assertEqual(status["total"], 2)
        self.assertEqual(status["read"], 0)
        self.assertFalse(status["complete"])

    def test_acknowledge_archives_when_all_read(self):
        self.client.force_login(self.admin)
        response = self.client.post(f"/neuigkeiten/{self.post.pk}/", {"action": "acknowledge"})
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertIsNone(self.post.archived_at)

        self.client.force_login(self.member)
        self.client.post(f"/neuigkeiten/{self.post.pk}/", {"action": "acknowledge"})
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.archived_at)
        self.assertEqual(NewsAcknowledgement.objects.filter(post=self.post).count(), 2)

    def test_archive_is_visible_but_not_active(self):
        acknowledge(self.post, self.admin)
        acknowledge(self.post, self.member)
        self.client.force_login(self.member)
        response = self.client.get("/neuigkeiten/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neue Fahrzeugordnung")
        self.assertContains(response, "Archiviert")

    def test_create_with_pdf_attachment(self):
        self.client.force_login(self.admin)
        upload = SimpleUploadedFile("ordnung.pdf", PDF, content_type="application/pdf")
        response = self.client.post("/neuigkeiten/neu/", {
            "title": "Neue Order",
            "body": "Bitte lesen.",
            "attachment": upload,
        })
        self.assertEqual(response.status_code, 302)
        post = NewsPost.objects.get(title="Neue Order")
        attachment = NewsAttachment.objects.get(post=post)
        self.assertTrue(attachment.filename.endswith(".pdf"))

    def test_member_cannot_create(self):
        self.client.force_login(self.member)
        response = self.client.get("/neuigkeiten/neu/")
        self.assertEqual(response.status_code, 302)

    def test_attachment_is_station_bound(self):
        attachment = NewsAttachment.objects.create(
            post=self.post, station=self.station, filename="x.pdf",
            content_type="application/pdf", data=PDF, size=len(PDF), uploaded_by=self.admin,
        )
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(f"/neuigkeiten/anhaenge/{attachment.pk}/").status_code, 200)

        other = Station.objects.create(name="Fremd", slug="fremd")
        stranger = User.objects.create_user("stranger-news", password="Stranger-12345")
        Membership.objects.create(user=stranger, station=other, role=Membership.Role.MEMBER)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(f"/neuigkeiten/anhaenge/{attachment.pk}/").status_code, 404)
