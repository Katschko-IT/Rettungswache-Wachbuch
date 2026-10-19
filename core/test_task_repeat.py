"""Wiederholungen wie in einer Kalender-App plus freie Aufgabenfarbe."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from core.forms import StationTaskForm
from core.models import Membership, Station, StationTask


class RepeatLogicTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Repeat", slug="repeat")

    def make(self, **kwargs):
        defaults = {"station": self.station, "title": "Probe"}
        defaults.update(kwargs)
        return StationTask.objects.create(**defaults)

    def test_daily_interval_counts_from_start(self):
        task = self.make(
            repeat=StationTask.Repeat.DAILY,
            repeat_interval=3,
            start_date=date(2026, 10, 1),
        )
        self.assertTrue(task.applies_to_date(date(2026, 10, 1)))
        self.assertFalse(task.applies_to_date(date(2026, 10, 2)))
        self.assertTrue(task.applies_to_date(date(2026, 10, 4)))

    def test_weekly_supports_several_weekdays(self):
        task = self.make(
            repeat=StationTask.Repeat.WEEKLY,
            start_date=date(2026, 10, 5),  # Montag
        )
        task.set_weekdays([0, 2, 4])
        task.save()
        self.assertTrue(task.applies_to_date(date(2026, 10, 5)))   # Mo
        self.assertFalse(task.applies_to_date(date(2026, 10, 6)))  # Di
        self.assertTrue(task.applies_to_date(date(2026, 10, 7)))   # Mi

    def test_weekly_interval_two_weeks(self):
        task = self.make(
            repeat=StationTask.Repeat.WEEKLY,
            repeat_interval=2,
            start_date=date(2026, 10, 5),
        )
        task.set_weekdays([0])
        task.save()
        self.assertTrue(task.applies_to_date(date(2026, 10, 5)))
        self.assertFalse(task.applies_to_date(date(2026, 10, 12)))
        self.assertTrue(task.applies_to_date(date(2026, 10, 19)))

    def test_monthly_day_and_short_month(self):
        task = self.make(
            repeat=StationTask.Repeat.MONTHLY,
            month_day=31,
            start_date=date(2026, 1, 31),
        )
        self.assertTrue(task.applies_to_date(date(2026, 2, 28)))
        self.assertFalse(task.applies_to_date(date(2026, 2, 27)))
        self.assertTrue(task.applies_to_date(date(2026, 3, 31)))

    def test_once_only_on_start_date(self):
        task = self.make(repeat=StationTask.Repeat.ONCE, start_date=date(2026, 12, 24))
        self.assertTrue(task.applies_to_date(date(2026, 12, 24)))
        self.assertFalse(task.applies_to_date(date(2026, 12, 25)))

    def test_end_date_stops_repetition(self):
        task = self.make(
            repeat=StationTask.Repeat.DAILY,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 3),
        )
        self.assertTrue(task.applies_to_date(date(2026, 10, 3)))
        self.assertFalse(task.applies_to_date(date(2026, 10, 4)))


class StationTaskFormTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Form", slug="form")
        self.user = User.objects.create_user("form-admin", password="Form-Test-12345")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)

    def test_form_saves_free_color_and_weekdays(self):
        form = StationTaskForm(data={
            "title": "Fenster prüfen",
            "band": "weekday",
            "color": "#ff8800",
            "repeat": "weekly",
            "repeat_interval": "2",
            "weekdays_selected": ["0", "3"],
            "start_date": "2026-10-05",
            "notes": "",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        task = form.save(commit=False)
        task.station = self.station
        task.save()
        self.assertEqual(task.color, "#ff8800")
        self.assertEqual(task.weekday_list(), [0, 3])
        self.assertEqual(task.repeat_interval, 2)

    def test_band_color_clears_custom_color(self):
        form = StationTaskForm(data={
            "title": "Bereichsfarbe",
            "band": "daily",
            "use_band_color": "on",
            "color": "#123456",
            "repeat": "daily",
            "repeat_interval": "1",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["color"], "")

    def test_form_rejects_invalid_color(self):
        form = StationTaskForm(data={
            "title": "X",
            "band": "daily",
            "color": "orange",
            "repeat": "daily",
            "repeat_interval": "1",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("color", form.errors)

    def test_weekly_without_weekday_is_invalid(self):
        form = StationTaskForm(data={
            "title": "X",
            "band": "weekday",
            "repeat": "weekly",
            "repeat_interval": "1",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("weekdays_selected", form.errors)

    def test_once_requires_date(self):
        form = StationTaskForm(data={
            "title": "X",
            "band": "extra",
            "repeat": "once",
            "repeat_interval": "1",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("start_date", form.errors)
