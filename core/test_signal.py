"""Signal-Benachrichtigungen über signal-cli-rest-api (ohne Netzwerk, Aufrufe gemockt)."""
from __future__ import annotations

import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import coffee as logic
from core import signal_messenger as signal
from core.coffee_models import CoffeeFund, CoffeeParticipant
from core.models import Membership, Station
from core.notification_models import SignalContact, SignalOutbox, UserNotification

SIGNAL = {"SIGNAL_API_URL": "http://signal:8080", "SIGNAL_NUMBER": "+4915100000000", "SITE_URL": "https://rwsth.de"}
GROUP = "group.V2FjaGVuZ3J1cHBl"


class NumberTests(TestCase):
    def test_normalizes_german_and_international_numbers(self):
        self.assertEqual(signal.normalize_number("0171 234 56 78"), "+491712345678")
        self.assertEqual(signal.normalize_number("0043 664 1234567"), "+436641234567")
        self.assertEqual(signal.normalize_number("+49 (171) 2345-678"), "+491712345678")
        with self.assertRaises(ValueError):
            signal.normalize_number("12")


@override_settings(**SIGNAL)
class SignalFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.station = Station.objects.create(name="RW Nord", slug="rw-nord", signal_group_id=GROUP)
        self.admin = User.objects.create_user("chef", first_name="Wachen", last_name="Leitung")
        self.member = User.objects.create_user("mara", first_name="Mara", last_name="Muster")
        self.cashier = User.objects.create_user("kasse", first_name="Karla")
        for user, role in ((self.admin, Membership.Role.ADMIN), (self.member, Membership.Role.MEMBER),
                           (self.cashier, Membership.Role.CASHIER)):
            Membership.objects.create(user=user, station=self.station, role=role)


class OutboxTests(SignalFixture):
    def test_personal_messages_only_for_verified_numbers(self):
        note = UserNotification.objects.create(station=self.station, user=self.member, kind="coffee_due",
                                               title="T", dedupe_key="k")
        self.assertFalse(signal.enqueue_for_user(note, {"title": "T"}))
        SignalContact.objects.create(user=self.member, number="+491712345678")  # unbestätigt
        self.assertFalse(signal.enqueue_for_user(note, {"title": "T"}))
        SignalContact.objects.filter(user=self.member).update(verified_at=timezone.now())
        self.assertTrue(signal.enqueue_for_user(note, {"title": "Kaffeekasse", "body": "Offen", "url": "/kaffeekasse/"}))
        item = SignalOutbox.objects.get()
        self.assertEqual(item.recipient, "+491712345678")
        self.assertEqual(item.message, "Kaffeekasse\nOffen\nhttps://rwsth.de/kaffeekasse/")

    def test_delivery_retries_with_backoff_and_purges_old_rows(self):
        signal.enqueue(self.station, GROUP, "Hallo")
        now = timezone.now()
        with mock.patch.object(signal, "send", side_effect=signal.SignalError("down")):
            self.assertEqual(signal.deliver_outbox(now=now), 0)
        item = SignalOutbox.objects.get()
        self.assertEqual(item.attempts, 1)
        self.assertGreater(item.next_attempt_at, now)
        with mock.patch.object(signal, "send") as send:
            self.assertEqual(signal.deliver_outbox(now=now), 0)  # noch nicht fällig
            self.assertEqual(signal.deliver_outbox(now=now + timedelta(minutes=3)), 1)
        send.assert_called_once_with([GROUP], "Hallo")
        signal.deliver_outbox(now=now + timedelta(days=31))
        self.assertFalse(SignalOutbox.objects.exists())

    def test_disabled_signal_queues_nothing(self):
        with self.settings(SIGNAL_API_URL=""):
            self.assertFalse(signal.enqueue(self.station, GROUP, "x"))
            self.assertEqual(signal.deliver_outbox(), 0)

    def test_send_posts_v2_payload(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"timestamp":"1"}'
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            signal.send([GROUP], "Test")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "http://signal:8080/v2/send")
        self.assertIn(b'"recipients": ["group.V2FjaGVuZ3J1cHBl"]', request.data)
        self.assertIn(b'"number": "+4915100000000"', request.data)


class CoffeeSignalTests(SignalFixture):
    def setUp(self):
        super().setUp()
        self.fund = CoffeeFund.objects.create(station=self.station, monthly_fee_cents=500, reminder_day=1,
                                              signal_group_reminder=True, signal_group_counts=True)
        month = logic.month_start(logic.station_today(self.station))
        CoffeeParticipant.objects.create(station=self.station, user=self.member, since=month)
        CoffeeParticipant.objects.create(station=self.station, user=self.cashier, since=month)

    def test_group_reminder_is_anonymous_and_monthly(self):
        SignalContact.objects.create(user=self.member, number="+491712345678", verified_at=timezone.now())
        logic.remind_open_fees()
        logic.remind_open_fees()
        group = SignalOutbox.objects.get(recipient=GROUP)
        self.assertIn("ist fällig", group.message)
        self.assertIn("0 von 2 haben schon bezahlt", group.message)
        self.assertNotIn("Mara", group.message)
        personal = SignalOutbox.objects.get(recipient="+491712345678")
        self.assertIn("5,00 €", personal.message)
        self.assertEqual(SignalOutbox.objects.count(), 2)

    def test_cash_count_is_announced_without_names(self):
        self.client.force_login(self.cashier)
        self.client.post(reverse("coffee_count"), {"counted_eur": "0.00"})
        message = SignalOutbox.objects.get(recipient=GROUP).message
        self.assertIn("die Kasse stimmt", message)

    def test_fund_form_offers_signal_only_with_group(self):
        from core.forms import CoffeeFundForm

        self.assertIn("signal_group_reminder", CoffeeFundForm(instance=self.fund).fields)
        self.station.signal_group_id = ""
        self.station.save()
        self.fund.refresh_from_db()
        self.assertNotIn("signal_group_reminder", CoffeeFundForm(instance=self.fund).fields)


class SignalAccountViewTests(SignalFixture):
    def test_member_confirms_own_number_with_code(self):
        self.client.force_login(self.member)
        with mock.patch.object(signal, "send") as send:
            self.client.post(reverse("signal_account"), {"action": "number", "number": "0171 2345678"})
        recipients, text = send.call_args[0]
        self.assertEqual(recipients, ["+491712345678"])
        code = re.search(r"\b(\d{6})\b", text).group(1)
        self.client.post(reverse("signal_account"), {"action": "confirm", "code": "000000" if code != "000000" else "111111"})
        self.assertIsNone(SignalContact.objects.get().verified_at)
        self.client.post(reverse("signal_account"), {"action": "confirm", "code": code})
        self.assertIsNotNone(SignalContact.objects.get().verified_at)
        self.client.post(reverse("signal_account"), {"action": "remove"})
        self.assertFalse(SignalContact.objects.exists())

    def test_code_requests_are_rate_limited(self):
        self.client.force_login(self.member)
        with mock.patch.object(signal, "send") as send:
            for _ in range(5):
                self.client.post(reverse("signal_account"), {"action": "number", "number": "0171 2345678"})
        self.assertEqual(send.call_count, 3)

    def test_page_hidden_without_signal(self):
        self.client.force_login(self.member)
        with self.settings(SIGNAL_API_URL=""):
            self.assertEqual(self.client.get(reverse("signal_account")).status_code, 404)


class SignalAdminViewTests(SignalFixture):
    def test_admin_picks_group_known_to_linked_account(self):
        groups = [{"id": GROUP, "name": "Wache Nord", "invite_link": "", "members": 12}]
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("signal_admin")).status_code, 403)
        self.client.force_login(self.admin)
        with mock.patch.object(signal, "is_linked", return_value=True), \
                mock.patch.object(signal, "groups", return_value=groups):
            page = self.client.get(reverse("signal_admin"))
            self.assertContains(page, "Wache Nord")
            self.client.post(reverse("signal_admin"), {"action": "group", "group_id": "group.fremd"})
            self.station.refresh_from_db()
            self.assertEqual(self.station.signal_group_id, GROUP)
            self.client.post(reverse("signal_admin"), {"action": "group", "group_id": ""})
            self.station.refresh_from_db()
            self.assertEqual(self.station.signal_group_id, "")

    def test_unlinked_service_shows_link_qr(self):
        self.client.force_login(self.admin)
        with mock.patch.object(signal, "is_linked", return_value=False), \
                mock.patch.object(signal, "link_qr_png", return_value=b"\x89PNG"):
            self.assertContains(self.client.get(reverse("signal_admin")), "data:image/png;base64,")
        with mock.patch.object(signal, "is_linked", return_value=False), \
                mock.patch.object(signal, "link_qr_png", side_effect=signal.SignalError("offline")):
            self.assertContains(self.client.get(reverse("signal_admin")), "offline")
