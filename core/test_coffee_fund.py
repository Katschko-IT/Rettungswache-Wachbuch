"""Kaffeekasse mit Monatsbeitrag: Mappe, Kasse, Kassensturz, Sichtbarkeit."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core import coffee as logic
from core.coffee_models import CoffeeCashMovement, CoffeeFund, CoffeeParticipant
from core.models import AuditEvent, CoffeeEntry, Membership, Station
from core.notification_models import UserNotification

MONTH = dt.date(2026, 10, 1)


class CoffeeFixture(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW Nord", slug="rw-nord", iban="DE89 3704 0044 0532 0130 00")
        self.cashier = User.objects.create_user("kasse", first_name="Karla", last_name="Kasse")
        self.admin = User.objects.create_user("chef", first_name="Wachen", last_name="Leitung")
        self.member = User.objects.create_user("mara", first_name="Mara", last_name="Muster")
        self.other = User.objects.create_user("olaf", first_name="Olaf", last_name="Ohnegeld")
        for user, role in ((self.cashier, Membership.Role.CASHIER), (self.admin, Membership.Role.ADMIN),
                           (self.member, Membership.Role.MEMBER), (self.other, Membership.Role.MEMBER)):
            Membership.objects.create(user=user, station=self.station, role=role)
        self.fund = CoffeeFund.objects.create(station=self.station, monthly_fee_cents=500)

    def join(self, user, since):
        return CoffeeParticipant.objects.create(station=self.station, user=user, since=since)

    def pay(self, user, cents, method=CoffeeEntry.Method.CASH):
        return CoffeeEntry.objects.create(
            station=self.station, member=user, amount_cents=cents, reason="Einzahlung",
            kind=CoffeeEntry.Kind.PAYMENT, method=method, created_by=user,
        )


class MonthlyFeeTests(CoffeeFixture):
    def test_fees_are_booked_once_per_month(self):
        self.join(self.member, logic.add_months(MONTH, -2))
        self.assertEqual(logic.ensure_fees(self.station, MONTH), 3)
        self.assertEqual(logic.ensure_fees(self.station, MONTH), 0)
        fees = CoffeeEntry.objects.filter(kind=CoffeeEntry.Kind.FEE).order_by("period")
        self.assertEqual([f.period for f in fees], [dt.date(2026, 8, 1), dt.date(2026, 9, 1), MONTH])
        self.assertTrue(all(f.amount_cents == -500 and f.created_by is None for f in fees))

    def test_payments_settle_oldest_month_first_and_leave_credit(self):
        self.join(self.member, logic.add_months(MONTH, -2))
        logic.ensure_fees(self.station, MONTH)
        self.pay(self.member, 1000)
        status = logic.member_status(self.station, self.member)
        self.assertEqual([m.status for m in status.recent(MONTH, 3)], [logic.OPEN, logic.PAID, logic.PAID])
        self.assertEqual(status.open_cents, 500)
        self.pay(self.member, 1500)
        status = logic.member_status(self.station, self.member)
        self.assertEqual(status.open_cents, 0)
        self.assertEqual(status.credit_cents, 1000)  # zwei Monate im Voraus

    def test_partial_payment_leaves_remaining_amount(self):
        self.join(self.member, MONTH)
        logic.ensure_fees(self.station, MONTH)
        self.pay(self.member, 200)
        month = logic.member_status(self.station, self.member).months[MONTH]
        self.assertEqual((month.status, month.remaining_cents), (logic.OPEN, 300))

    def test_fee_change_does_not_touch_booked_months(self):
        self.join(self.member, logic.add_months(MONTH, -1))
        logic.ensure_fees(self.station, logic.add_months(MONTH, -1))
        self.fund.monthly_fee_cents = 700
        self.fund.save()
        logic.ensure_fees(self.station, MONTH)
        amounts = dict(CoffeeEntry.objects.filter(kind=CoffeeEntry.Kind.FEE).values_list("period", "amount_cents"))
        self.assertEqual(amounts, {logic.add_months(MONTH, -1): -500, MONTH: -700})

    def test_ended_participation_and_former_members_stop_fees(self):
        participant = self.join(self.member, logic.add_months(MONTH, -1))
        participant.until = logic.add_months(MONTH, -1)
        participant.save()
        self.join(self.other, MONTH)
        Membership.objects.filter(user=self.other).update(is_active=False)
        logic.ensure_fees(self.station, logic.add_months(MONTH, 2))
        self.assertEqual(CoffeeEntry.objects.filter(kind=CoffeeEntry.Kind.FEE).count(), 1)

    def test_waiver_settles_exactly_one_month(self):
        self.join(self.member, logic.add_months(MONTH, -1))
        logic.ensure_fees(self.station, MONTH)
        self.client.force_login(self.cashier)
        url = reverse("coffee_waive", args=[self.member.pk, MONTH.isoformat()])
        self.assertRedirects(self.client.post(url, {"reason": "Elternzeit"}), reverse("coffee_book"),
                             fetch_redirect_response=False)
        self.client.post(url, {"reason": "doppelt"})
        self.assertEqual(CoffeeEntry.objects.filter(kind=CoffeeEntry.Kind.WAIVER).count(), 1)
        status = logic.member_status(self.station, self.member)
        self.assertEqual(status.months[MONTH].status, logic.WAIVED)
        self.assertEqual(status.open_cents, 500)  # Vormonat bleibt offen

    def test_corrected_fee_is_not_charged_again(self):
        self.join(self.member, MONTH)
        logic.ensure_fees(self.station, MONTH)
        fee = CoffeeEntry.objects.get(kind=CoffeeEntry.Kind.FEE)
        self.client.force_login(self.cashier)
        self.client.post(reverse("coffee_correct", args=[fee.pk]), {"reason": "falsch eingetragen"})
        correction = CoffeeEntry.objects.get(correction_of=fee)
        self.assertEqual((correction.kind, correction.period, correction.amount_cents), ("fee", MONTH, 500))
        logic.ensure_fees(self.station, MONTH)
        status = logic.member_status(self.station, self.member)
        self.assertEqual((status.open_cents, status.months), (0, {}))


class CoffeeViewTests(CoffeeFixture):
    def setUp(self):
        super().setUp()
        current = logic.month_start(logic.station_today(self.station))
        self.join(self.member, current)
        self.join(self.other, current)
        logic.ensure_fees(self.station)
        self.pay(self.other, 2000)

    def test_member_reports_cash_like_ticking_the_folder(self):
        self.client.force_login(self.member)
        page = self.client.get(reverse("coffee"))
        self.assertContains(page, "Offen")
        self.assertContains(page, "data:image/png;base64,")  # GiroCode
        self.assertContains(page, "Kaffeekasse RW Nord Mara Muster")
        response = self.client.post(reverse("coffee_pay"), {"method": "cash", "amount_eur": "5.00"})
        self.assertRedirects(response, reverse("coffee"), fetch_redirect_response=False)
        entry = CoffeeEntry.objects.get(member=self.member, kind=CoffeeEntry.Kind.PAYMENT)
        self.assertEqual((entry.method, entry.created_by, entry.amount_cents), ("cash", self.member, 500))
        self.assertEqual(logic.member_status(self.station, self.member).open_cents, 0)
        self.assertEqual(logic.pots(self.station).cash_cents, 2500)
        self.assertTrue(AuditEvent.objects.filter(action="coffee.payment_reported").exists())

    def test_quick_amount_prefills_form(self):
        self.client.force_login(self.member)
        page = self.client.get(reverse("coffee_pay") + "?betrag=1500")
        self.assertContains(page, 'value="15.00"')

    def test_members_never_see_other_people(self):
        self.client.force_login(self.member)
        page = self.client.get(reverse("coffee"))
        self.assertNotContains(page, "Olaf")
        self.assertContains(page, "1 von 2 bezahlt")  # ohne Namen
        for name in ("coffee_book", "coffee_ledger", "coffee_create", "coffee_count", "coffee_export",
                     "coffee_settings", "coffee_participants"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_admin_configures_but_sees_no_individual_balances(self):
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(reverse("coffee")), "Olaf")
        for name in ("coffee_book", "coffee_ledger", "coffee_create", "coffee_export"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("coffee_participants")).status_code, 200)
        response = self.client.post(reverse("coffee_settings"), {
            "fund-monthly_fee_eur": "6.00", "fund-reminder_day": "5", "fund-account_holder": "Kaffeekasse RW Nord",
            "ways-iban": "DE89370400440532013000", "ways-bic": "", "ways-paypal_me_url": "", "ways-wero_link": "",
            "ways-payment_note": "",
        })
        self.assertRedirects(response, reverse("coffee"), fetch_redirect_response=False)
        self.fund.refresh_from_db()
        self.assertEqual((self.fund.monthly_fee_cents, self.fund.reminder_day), (600, 5))

    def test_cashier_works_the_folder(self):
        self.client.force_login(self.cashier)
        book = self.client.get(reverse("coffee_book"))
        self.assertContains(book, "Mara Muster")
        self.assertContains(book, "Olaf Ohnegeld")
        self.assertContains(book, "€ bar von Mara Muster erhalten")
        self.client.post(reverse("coffee_cash_received", args=[self.member.pk]))
        self.assertEqual(logic.member_status(self.station, self.member).open_cents, 0)
        self.assertContains(self.client.get(reverse("coffee_ledger") + "?selbst=1"), "Olaf Ohnegeld")

    def test_purchase_count_and_deposit(self):
        self.client.force_login(self.member)
        self.client.post(reverse("coffee_purchase"), {"what": "Kaffeebohnen", "amount_eur": "18.90", "pot": "cash"})
        self.assertEqual(logic.pots(self.station).cash_cents, 2000 - 1890)
        self.assertContains(self.client.get(reverse("coffee_cash")), "Kaffeebohnen")
        self.client.force_login(self.cashier)
        self.client.post(reverse("coffee_count"), {"counted_eur": "1.00", "witness": self.member.pk})
        count = CoffeeCashMovement.objects.get(kind=CoffeeCashMovement.Kind.COUNT)
        self.assertEqual((count.expected_cents, count.counted_cents, count.amount_cents), (110, 100, -10))
        self.assertEqual(logic.pots(self.station).cash_cents, 100)
        self.client.post(reverse("coffee_count"), {"counted_eur": "1.00"})  # stimmt: Differenz 0 wird festgehalten
        self.assertEqual(CoffeeCashMovement.objects.filter(kind="count").count(), 2)
        self.client.post(reverse("coffee_movement"), {"kind": "deposit", "pot": "bank", "amount_eur": "1.00",
                                                      "reason": "zur Bank"})
        pots = logic.pots(self.station)
        self.assertEqual((pots.cash_cents, pots.bank_cents), (0, 100))

    def test_movement_correction_restores_balance(self):
        self.client.force_login(self.member)
        self.client.post(reverse("coffee_purchase"), {"what": "Milch", "amount_eur": "3.00", "pot": "cash"})
        movement = CoffeeCashMovement.objects.get()
        self.client.force_login(self.cashier)
        self.client.post(reverse("coffee_movement_correct", args=[movement.pk]), {"reason": "doppelt"})
        self.assertEqual(logic.pots(self.station).cash_cents, 2000)
        with self.assertRaisesMessage(ValidationError, "Kassenbewegungen dürfen nicht gelöscht werden."):
            movement.delete()

    def test_export_neutralises_formulas(self):
        CoffeeEntry.objects.create(station=self.station, member=self.member, amount_cents=100,
                                   reason="=HYPERLINK(1)", created_by=self.cashier)
        self.client.force_login(self.cashier)
        content = self.client.get(reverse("coffee_export")).content.decode("utf-8")
        self.assertIn("'=HYPERLINK(1)", content)


class CoffeeReminderTests(CoffeeFixture):
    def test_reminds_once_per_month_only_with_open_fee(self):
        today = logic.station_today(self.station)
        self.fund.reminder_day = 1
        self.fund.save()
        self.join(self.member, logic.month_start(today))
        self.join(self.other, logic.month_start(today))
        self.pay(self.other, 500)
        self.assertEqual(logic.remind_open_fees(), 1)
        self.assertEqual(logic.remind_open_fees(), 0)
        note = UserNotification.objects.get()
        self.assertEqual((note.user, note.kind), (self.member, "coffee_due"))
        self.assertIn("5,00", note.body)

    def test_no_reminder_before_reminder_day(self):
        self.fund.reminder_day = 28
        self.fund.save()
        self.join(self.member, logic.month_start(logic.station_today(self.station)))
        with mock.patch.object(logic, "station_today", return_value=dt.date(2026, 10, 3)):
            self.assertEqual(logic.remind_open_fees(), 0)


class GiroCodeTests(TestCase):
    def test_epc_payload_follows_epc069_12(self):
        payload = logic.epc_payload(name="Kaffeekasse RW Nord", iban="de89 3704 0044 0532 0130 00",
                                    amount_cents=1550, text="Kaffeekasse RW Nord Mara Muster")
        self.assertEqual(payload.split("\n"), [
            "BCD", "002", "1", "SCT", "", "Kaffeekasse RW Nord", "DE89370400440532013000", "EUR15.50", "", "",
            "Kaffeekasse RW Nord Mara Muster",
        ])
        self.assertFalse(payload.endswith("\n"))

    def test_epc_payload_without_amount_and_text_ends_after_iban(self):
        payload = logic.epc_payload(name="Kasse", iban="DE89370400440532013000", bic="COBADEFFXXX")
        self.assertEqual(payload, "BCD\n002\n1\nSCT\nCOBADEFFXXX\nKasse\nDE89370400440532013000")


class YearOverviewTests(CoffeeFixture):
    def test_chosen_year_is_clamped(self):
        self.assertEqual(logic.chosen_year("2025", MONTH, 2024), 2025)
        self.assertEqual(logic.chosen_year("1999", MONTH, 2024), 2024)
        self.assertEqual(logic.chosen_year("2099", MONTH, 2024), 2026)
        self.assertEqual(logic.chosen_year("abc", MONTH, None), 2026)

    def test_year_cells_mark_future_and_unpaid_months(self):
        self.join(self.member, dt.date(2026, 9, 1))
        logic.ensure_fees(self.station, MONTH)
        self.pay(self.member, 500)
        cells = logic.year_cells(logic.member_status(self.station, self.member), 2026, MONTH)
        self.assertEqual([c.status for c in cells], ["none"] * 8 + ["paid", "open", "future", "future"])

    def test_cashier_browses_previous_years(self):
        today = logic.station_today(self.station)
        last_year = today.year - 1
        self.join(self.member, dt.date(last_year, 11, 1))
        self.join(self.other, logic.month_start(today))
        logic.ensure_fees(self.station)
        self.pay(self.member, 500)  # tilgt November des Vorjahres
        self.client.force_login(self.cashier)
        page = self.client.get(reverse("coffee_book"))
        self.assertContains(page, f"Jahr {today.year}")
        self.assertContains(page, f"?jahr={last_year}")
        self.assertContains(page, "Olaf Ohnegeld")
        old = self.client.get(reverse("coffee_book") + f"?jahr={last_year}")
        self.assertContains(old, f"Jahr {last_year}")
        self.assertContains(old, "Mara Muster")
        self.assertNotContains(old, "Olaf Ohnegeld")  # erst ab diesem Jahr dabei
        self.assertContains(old, "1/1")  # November: 1 von 1 bezahlt
        self.assertEqual(old.context["rows"][0]["paid_count"], 1)
        member = self.client
        member.force_login(self.member)
        own = member.get(reverse("coffee") + f"?jahr={last_year}")
        self.assertContains(own, f"Meine Monate {last_year}")


@override_settings(EMAIL_HOST="smtp.example.test", SITE_URL="https://rwsth.de", LANGUAGE_CODE="de")
class CoffeeEmailTests(CoffeeFixture):
    def setUp(self):
        super().setUp()
        from django.core import mail

        self.mail = mail
        self.fund.email_reminder = True
        self.fund.reminder_day = 1
        self.fund.account_holder = "Kaffeekasse RW Nord"
        self.fund.save()
        self.member.email = "mara@example.test"
        self.member.save()
        month = logic.month_start(logic.station_today(self.station))
        self.participant = self.join(self.member, month)

    def test_monthly_email_has_girocode_and_iban(self):
        logic.remind_open_fees()
        logic.remind_open_fees()
        self.assertEqual(len(self.mail.outbox), 1)
        message = self.mail.outbox[0]
        self.assertEqual(message.to, ["mara@example.test"])
        self.assertIn("5,00 € offen", message.subject)
        self.assertIn("DE89370400440532013000", message.body)
        self.assertIn("Kaffeekasse RW Nord Mara Muster", message.body)
        self.assertIn("https://rwsth.de/kaffeekasse/", message.body)
        html = message.alternatives[0][0]
        self.assertIn('src="cid:girocode"', html)
        mime = message.message()
        related = mime.get_body(preferencelist=("related",))
        self.assertIsNotNone(related)
        images = [part for part in mime.walk() if part.get("Content-ID") == "<girocode>"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].get_content_type(), "image/png")
        self.assertTrue(images[0].get_content().startswith(b"\x89PNG"))

    def test_opt_out_and_missing_address_skip_email(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("coffee")), "E-Mail-Erinnerung abbestellen")
        self.client.post(reverse("coffee_email_preference"), {})
        self.participant.refresh_from_db()
        self.assertFalse(self.participant.email_reminders)
        logic.remind_open_fees()
        self.assertEqual(self.mail.outbox, [])
        self.assertTrue(UserNotification.objects.filter(user=self.member).exists())  # Posteingang bleibt

    def test_cashier_sends_reminder_once_a_day(self):
        from django.core.cache import cache

        cache.clear()
        logic.ensure_fees(self.station)
        self.client.force_login(self.cashier)
        self.assertContains(self.client.get(reverse("coffee_book")), "Erinnerung per E-Mail an Mara Muster")
        url = reverse("coffee_email_reminder", args=[self.member.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(len(self.mail.outbox), 1)
        self.assertTrue(AuditEvent.objects.filter(action="coffee.reminder_emailed").exists())

    def test_admin_sends_test_email_to_self(self):
        self.admin.email = "chef@example.test"
        self.admin.save()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("coffee_settings")), "Monatliche Erinnerung per E-Mail")
        self.client.post(reverse("coffee_test_email"))
        self.assertEqual(self.mail.outbox[0].to, ["chef@example.test"])
        self.assertIn("Zahlungsangaben", self.mail.outbox[0].subject)

    def test_without_smtp_nothing_is_offered(self):
        with self.settings(EMAIL_HOST=""):
            from core.forms import CoffeeFundForm

            self.assertNotIn("email_reminder", CoffeeFundForm(instance=self.fund).fields)
            logic.remind_open_fees()
            self.assertEqual(self.mail.outbox, [])
