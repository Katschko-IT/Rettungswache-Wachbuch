"""Müllkalender: ICS-Datei hochladen als Alternative zur URL."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import Membership, Station, WasteCollection

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//DE
BEGIN:VEVENT
SUMMARY:Restmülltonne
DTSTART;VALUE=DATE:20261020
DTEND;VALUE=DATE:20261021
END:VEVENT
BEGIN:VEVENT
SUMMARY:Biotonne
DTSTART;VALUE=DATE:20261023
DTEND;VALUE=DATE:20261024
END:VEVENT
END:VCALENDAR
"""


class WasteCalendarUploadTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Entsorgung", slug="entsorgung", organization_profile="rescue"
        )
        self.user = User.objects.create_user("waste-admin", password="Waste-Test-12345")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def post(self, **extra):
        data = {
            "name": self.station.name,
            "organization_profile": "rescue",
            "waste_calendar_enabled": "on",
        }
        data.update(extra)
        return self.client.post("/einstellungen/", data)

    def test_upload_creates_collections(self):
        upload = SimpleUploadedFile("abfuhr.ics", ICS.encode(), content_type="text/calendar")
        response = self.post(waste_calendar_file=upload)
        self.assertEqual(response.status_code, 302)
        titles = list(
            WasteCollection.objects.filter(station=self.station).values_list("title", flat=True)
        )
        self.assertEqual(sorted(titles), ["Biotonne", "Restmülltonne"])

    def test_upload_replaces_previous_entries(self):
        WasteCollection.objects.create(
            station=self.station, title="Alt", starts_at="2026-01-01T08:00:00+00:00"
        )
        upload = SimpleUploadedFile("abfuhr.ics", ICS.encode(), content_type="text/calendar")
        self.post(waste_calendar_file=upload)
        titles = list(
            WasteCollection.objects.filter(station=self.station).values_list("title", flat=True)
        )
        self.assertNotIn("Alt", titles)
        self.assertEqual(len(titles), 2)

    def test_upload_without_checkbox_enables_calendar(self):
        upload = SimpleUploadedFile("abfuhr.ics", ICS.encode(), content_type="text/calendar")
        response = self.client.post("/einstellungen/", {
            "name": self.station.name,
            "organization_profile": "rescue",
            "waste_calendar_file": upload,
        })
        self.assertEqual(response.status_code, 302)
        self.station.refresh_from_db()
        self.assertTrue(self.station.waste_calendar_enabled)
        self.assertEqual(WasteCollection.objects.filter(station=self.station).count(), 2)

    def test_enabled_without_source_is_rejected(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ICS-URL oder eine hochgeladene ICS-Datei")
