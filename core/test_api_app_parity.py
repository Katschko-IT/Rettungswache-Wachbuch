"""Schnittstellen, die die App für Kaffeekasse und Übergaben braucht."""
from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import TestCase

from core import coffee as logic
from core.coffee_models import CoffeeFund, CoffeeParticipant
from core.models import AuditEvent, CoffeeEntry, HandoverEntry, Membership, Station
from core.test_review_2026_10_24 import _make_token


class CoffeeAppApiTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="RW Nord", slug="rw-nord", coffee_enabled=True, iban="DE89 3704 0044 0532 0130 00",
            paypal_me_url="https://paypal.me/kasse",
        )
        CoffeeFund.objects.create(station=self.station, monthly_fee_cents=500, account_holder="Kaffeekasse RW")
        self.user = User.objects.create_user("mara", first_name="Mara", last_name="Muster")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        CoffeeParticipant.objects.create(
            station=self.station, user=self.user, since=logic.month_start(logic.station_today(self.station)),
        )
        self.auth = _make_token(self.user, "wb_parity_token_aaaaaaaaaaaaaaaaa")

    def test_get_includes_own_months_and_payment_ways(self):
        payload = self.client.get("/api/v1/kaffeekasse/", **self.auth).json()
        self.assertTrue(payload["own"]["participant"])
        self.assertEqual(payload["own"]["open_euros"], 5.0)
        self.assertEqual(payload["own"]["months"][0]["status"], "open")
        payment = payload["payment"]
        self.assertEqual(payment["methods"], ["cash", "transfer", "paypal"])
        self.assertEqual(payment["iban"], "DE89370400440532013000")
        self.assertEqual(payment["account_holder"], "Kaffeekasse RW")
        self.assertEqual(payment["transfer_text"], "Kaffeekasse RW Nord Mara Muster")
        self.assertEqual(payment["suggested_euros"], 5.0)

    def test_member_reports_own_payment(self):
        response = self.client.post(
            "/api/v1/kaffeekasse/bezahlt/", data=json.dumps({"method": "cash", "amount_euros": "5.00", "note": "Oktober"}),
            content_type="application/json", **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["own"]["open_euros"], 0.0)
        self.assertEqual(payload["own"]["months"][0]["status"], "paid")
        entry = CoffeeEntry.objects.get(kind=CoffeeEntry.Kind.PAYMENT)
        self.assertEqual((entry.member, entry.created_by, entry.method), (self.user, self.user, "cash"))
        self.assertIn("Oktober", entry.reason)
        self.assertTrue(AuditEvent.objects.filter(action="coffee.payment_reported").exists())

    def test_payment_rejects_unknown_method_and_bad_amount(self):
        for body in ({"method": "wero", "amount_euros": "5"}, {"method": "cash", "amount_euros": "0"},
                     {"method": "cash", "amount_euros": "999"}):
            response = self.client.post("/api/v1/kaffeekasse/bezahlt/", data=json.dumps(body),
                                        content_type="application/json", **self.auth)
            self.assertEqual(response.status_code, 422, body)
        self.assertFalse(CoffeeEntry.objects.filter(kind=CoffeeEntry.Kind.PAYMENT).exists())

    def test_module_off_and_auditor_blocked(self):
        auditor = User.objects.create_user("audit")
        Membership.objects.create(user=auditor, station=self.station, role=Membership.Role.AUDITOR)
        auth = _make_token(auditor, "wb_parity_token_bbbbbbbbbbbbbbbbb")
        body = json.dumps({"method": "cash", "amount_euros": "5"})
        self.assertEqual(self.client.post("/api/v1/kaffeekasse/bezahlt/", data=body,
                                          content_type="application/json", **auth).status_code, 403)
        self.station.coffee_enabled = False
        self.station.save()
        self.assertEqual(self.client.post("/api/v1/kaffeekasse/bezahlt/", data=body,
                                          content_type="application/json", **self.auth).status_code, 404)


class HandoverPaginationTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW", slug="rw")
        self.user = User.objects.create_user("lead")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.auth = _make_token(self.user, "wb_parity_token_ccccccccccccccccc")
        for index in range(5):
            HandoverEntry.objects.create(
                station=self.station, category="station", title=f"Ü{index}", details="x", author=self.user,
            )

    def test_next_links_walk_all_pages(self):
        seen, url = [], "/api/v1/handovers/?limit=2"
        while url:
            payload = self.client.get(url, **self.auth).json()
            self.assertEqual(payload["count"], 5)
            seen += [item["title"] for item in payload["results"]]
            url = payload["next"]
            if url:
                self.assertTrue(url.startswith("/api/v1/handovers/?"))
        self.assertEqual(sorted(seen), [f"Ü{index}" for index in range(5)])

    def test_default_page_keeps_fifty_and_no_next(self):
        payload = self.client.get("/api/v1/handovers/", **self.auth).json()
        self.assertEqual(len(payload["results"]), 5)
        self.assertIsNone(payload["next"])
