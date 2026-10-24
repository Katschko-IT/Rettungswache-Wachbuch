"""Wiederholungen wie in einer Kalender-App plus freie Aufgabenfarbe."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.display import display_payload
from core.forms import StationTaskForm
from core.models import Membership, Station, StationTask
from core.task_board import day_board


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


class TaskUrgencyTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Urgency", slug="urgency")
        self.today = date(2026, 10, 22)

    def test_urgency_levels_and_labels(self):
        # 10 Tage im Voraus -> ok (grün)
        task_ok = StationTask.objects.create(
            station=self.station,
            title="TÜV Prüfung",
            due_date=self.today + timedelta(days=10),
        )
        urg_ok = task_ok.get_urgency(self.today)
        self.assertEqual(urg_ok["level"], "ok")
        self.assertEqual(urg_ok["days_left"], 10)
        self.assertEqual(urg_ok["badge_class"], "urgency-ok")
        self.assertEqual(urg_ok["label"], "Noch 10 Tage")

        # 4 Tage im Voraus -> warning (gelb)
        task_warn = StationTask.objects.create(
            station=self.station,
            title="Lagerbestand prüfen",
            due_date=self.today + timedelta(days=4),
        )
        urg_warn = task_warn.get_urgency(self.today)
        self.assertEqual(urg_warn["level"], "warning")
        self.assertEqual(urg_warn["badge_class"], "urgency-warning")
        self.assertEqual(urg_warn["label"], "Fällig in 4 Tagen")

        # 2 Tage im Voraus -> critical (rot)
        task_crit2 = StationTask.objects.create(
            station=self.station,
            title="Desinfektion",
            due_date=self.today + timedelta(days=2),
        )
        urg_crit2 = task_crit2.get_urgency(self.today)
        self.assertEqual(urg_crit2["level"], "critical")
        self.assertEqual(urg_crit2["label"], "In 2 Tagen fällig")

        # Morgen fällig -> critical (rot)
        task_morgen = StationTask.objects.create(
            station=self.station,
            title="EKG Eichung",
            due_date=self.today + timedelta(days=1),
        )
        urg_morgen = task_morgen.get_urgency(self.today)
        self.assertEqual(urg_morgen["level"], "critical")
        self.assertEqual(urg_morgen["label"], "Morgen fällig!")

        # Heute fällig -> critical (rot)
        task_heute = StationTask.objects.create(
            station=self.station,
            title="Verbandkasten auffüllen",
            due_date=self.today,
        )
        urg_heute = task_heute.get_urgency(self.today)
        self.assertEqual(urg_heute["level"], "critical")
        self.assertEqual(urg_heute["label"], "Heute fällig!")

        # 1 Tag überfällig -> overdue (dunkelrot)
        task_over1 = StationTask.objects.create(
            station=self.station,
            title="Feuerlöscher prüfen",
            due_date=self.today - timedelta(days=1),
        )
        urg_over1 = task_over1.get_urgency(self.today)
        self.assertEqual(urg_over1["level"], "overdue")
        self.assertEqual(urg_over1["label"], "Seit 1 Tag überfällig!")

        # 5 Tage überfällig -> overdue (dunkelrot)
        task_over5 = StationTask.objects.create(
            station=self.station,
            title="Akku tauschen",
            due_date=self.today - timedelta(days=5),
        )
        urg_over5 = task_over5.get_urgency(self.today)
        self.assertEqual(urg_over5["level"], "overdue")
        self.assertEqual(urg_over5["label"], "Seit 5 Tagen überfällig!")

        # Ohne Fälligkeit -> none
        task_none = StationTask.objects.create(
            station=self.station,
            title="Fahrzeug wischen",
        )
        urg_none = task_none.get_urgency(self.today)
        self.assertEqual(urg_none["level"], "none")
        self.assertFalse(urg_none["has_due"])

    def test_form_validation_due_date_before_start_date(self):
        form = StationTaskForm(data={
            "title": "Ungültig",
            "band": "daily",
            "repeat": "daily",
            "start_date": "2026-10-25",
            "due_date": "2026-10-20",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("due_date", form.errors)

    def test_form_auto_sets_start_date_from_due_date_for_once(self):
        form = StationTaskForm(data={
            "title": "Einmalig mit Frist",
            "band": "extra",
            "repeat": "once",
            "repeat_interval": "1",
            "due_date": "2026-10-28",
            "sort_order": "100",
            "is_active": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["start_date"], date(2026, 10, 28))

    def test_day_board_sorting_by_urgency(self):
        # 4 Aufgaben im selben Band anlegen
        task_normal = StationTask.objects.create(
            station=self.station,
            title="Z Routine",
            band=StationTask.Band.DAILY,
            sort_order=10,
        )
        task_ok = StationTask.objects.create(
            station=self.station,
            title="B In 10 Tagen",
            band=StationTask.Band.DAILY,
            due_date=self.today + timedelta(days=10),
            sort_order=20,
        )
        task_crit = StationTask.objects.create(
            station=self.station,
            title="A Heute fällig",
            band=StationTask.Band.DAILY,
            due_date=self.today,
            sort_order=30,
        )
        task_over = StationTask.objects.create(
            station=self.station,
            title="C Überfällig",
            band=StationTask.Band.DAILY,
            due_date=self.today - timedelta(days=1),
            sort_order=40,
        )

        board = day_board(self.station, self.today)
        titles = [item["task"].title for item in board["groups"][StationTask.Band.DAILY]]
        # Erwartete Reihenfolge: Überfällig (C) -> Kritisch (A) -> OK (B) -> Normal (Z)
        self.assertEqual(titles[0], "C Überfällig")
        self.assertEqual(titles[1], "A Heute fällig")
        self.assertEqual(titles[2], "B In 10 Tagen")
        self.assertEqual(titles[3], "Z Routine")

    def test_display_data_collects_urgent_tasks(self):
        self.station.tasks_enabled = True
        self.station.save()
        StationTask.objects.create(
            station=self.station,
            title="Wichtiges Audit",
            # display_payload rechnet mit dem echten Datum, nicht mit self.today.
            due_date=timezone.localdate() + timedelta(days=1),
        )
        data = display_payload(self.station)
        self.assertIn("tasks", data)
        self.assertEqual(data["tasks"]["urgent_count"], 1)
        self.assertEqual(data["tasks"]["urgent_items"][0]["title"], "Wichtiges Audit")
        self.assertEqual(data["tasks"]["urgent_items"][0]["level"], "critical")

