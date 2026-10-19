"""Kalender führt alle Quellen zusammen: Termine, Feiertage, Müll, Geburtstage."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.holidays import station_agenda
from core.models import BirthdayPreference, CalendarEvent, Station


class AgendaMixTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Agenda", slug="agenda")
        self.user = User.objects.create_user("agenda-user", password="Agenda-Test-12345")
        self.user.first_name = "Alex"
        self.user.save()

    def test_visible_birthday_appears(self):
        today = timezone.localdate()
        BirthdayPreference.objects.create(
            user=self.user,
            station=self.station,
            day=today.day,
            month=today.month,
            is_visible=True,
        )
        agenda = station_agenda(self.station, [], past_days=1, future_days=30)
        birthdays = [item for item in agenda if item.kind == "birthday"]
        self.assertEqual(len(birthdays), 1)
        self.assertIn("Alex", birthdays[0].title)

    def test_hidden_birthday_is_not_shown(self):
        today = timezone.localdate()
        BirthdayPreference.objects.create(
            user=self.user,
            station=self.station,
            day=today.day,
            month=today.month,
            is_visible=False,
        )
        agenda = station_agenda(self.station, [])
        self.assertFalse([item for item in agenda if item.kind == "birthday"])

    def test_event_and_birthday_are_both_listed(self):
        now = timezone.now()
        CalendarEvent.objects.create(
            station=self.station,
            title="Fahrzeugübergabe",
            starts_at=now + timedelta(hours=2),
            ends_at=now + timedelta(hours=3),
            created_by=self.user,
        )
        today = timezone.localdate()
        BirthdayPreference.objects.create(
            user=self.user,
            station=self.station,
            day=today.day,
            month=today.month,
            is_visible=True,
        )
        events = CalendarEvent.objects.filter(station=self.station)
        kinds = {item.kind for item in station_agenda(self.station, events)}
        self.assertIn("event", kinds)
        self.assertIn("birthday", kinds)
