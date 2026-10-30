"""Regressionen der Review vom 29.10.2026 (Paket C1: Fehler im Kern).

Abfragezahlen und Anhangs-BLOBs prüft ``core.test_query_counts``, die
append-only-Sperren ``core.test_append_only_guards``.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import coffee as logic
from core.coffee_models import CoffeeCashMovement, CoffeeFund
from core.diagnostics_models import ErrorEvent
from core.feedback_models import Feedback
from core.models import (
    CoffeeEntry,
    InstallationSetup,
    Membership,
    NewsAttachment,
    NewsPost,
    Station,
)
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision
from core.test_review_2026_10_24 import _make_token
from core.wachalltag_models import InventoryItem
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StorageLocation


class CoffeeBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW Nord", slug="rw-nord", coffee_enabled=True)
        CoffeeFund.objects.create(station=self.station, monthly_fee_cents=500)
        self.member = User.objects.create_user("mara", first_name="Mara", last_name="Muster")
        self.cashier = User.objects.create_user("kasse", first_name="Karla", last_name="Kasse")
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        Membership.objects.create(user=self.cashier, station=self.station, role=Membership.Role.CASHIER)

    def payments(self):
        return CoffeeEntry.objects.filter(station=self.station, member=self.member, kind=CoffeeEntry.Kind.PAYMENT)


class CoffeeQueryParameterTests(CoffeeBase):
    """``str.isdigit()`` lässt „²“ und andere Ziffern durch, an denen ``int()`` scheitert."""

    def test_odd_digits_do_not_crash_the_coffee_pages(self):
        client = Client(raise_request_exception=False)
        client.force_login(self.cashier)
        cases = [
            (reverse("coffee_pay"), "betrag", "²"),
            (reverse("coffee_pay"), "betrag", "9" * 5000),
            (reverse("coffee_ledger"), "person", "²"),
            (reverse("coffee_ledger"), "person", "9" * 5000),
            (reverse("coffee_ledger"), "person", "99999999999999999999999"),
        ]
        for url, name, value in cases:
            with self.subTest(name=name, value=value[:10]):
                self.assertEqual(client.get(url, {name: value}).status_code, 200)
        self.assertFalse(ErrorEvent.objects.exists())

    def test_ascii_values_still_work(self):
        self.client.force_login(self.cashier)
        self.assertContains(self.client.get(reverse("coffee_pay"), {"betrag": "1500"}), 'value="15.00"')
        entry = CoffeeEntry.objects.create(station=self.station, member=self.member, amount_cents=100,
                                           reason="Einzahlung", created_by=self.cashier)
        page = self.client.get(reverse("coffee_ledger"), {"person": str(self.member.pk)})
        self.assertEqual(list(page.context["page_obj"]), [entry])

    def test_qr_totp_rejects_non_ascii_digits(self):
        from core.qr_login import verify_totp_with_time_step

        self.assertEqual(verify_totp_with_time_step(mock.Mock(), "²²²²²²"), (False, None))


class CoffeeDoubleSubmitTests(CoffeeBase):
    """Doppeltipp auf „Ich habe bezahlt“ bucht im append-only-Kassenbuch nur einmal."""

    def test_second_identical_submit_is_not_booked(self):
        self.client.force_login(self.member)
        data = {"method": "cash", "amount_eur": "5.00", "note": "Oktober"}
        self.client.post(reverse("coffee_pay"), data)
        response = self.client.post(reverse("coffee_pay"), data, follow=True)
        self.assertEqual(self.payments().count(), 1)
        self.assertContains(response, "Diese Zahlung ist schon eingetragen.")

    def test_other_amount_or_later_repeat_is_booked(self):
        self.client.force_login(self.member)
        self.client.post(reverse("coffee_pay"), {"method": "cash", "amount_eur": "5.00"})
        self.client.post(reverse("coffee_pay"), {"method": "cash", "amount_eur": "10.00"})
        self.assertEqual(self.payments().count(), 2)
        later = timezone.now() + logic.SELF_REPORT_REPEAT_WINDOW + dt.timedelta(seconds=1)
        with mock.patch("core.coffee.timezone.now", return_value=later):
            self.client.post(reverse("coffee_pay"), {"method": "cash", "amount_eur": "5.00"})
        self.assertEqual(self.payments().count(), 3)

    def test_app_retry_returns_the_first_entry(self):
        auth = _make_token(self.member, "wb_c1_token_aaaaaaaaaaaaaaaaaaaaa")
        body = json.dumps({"method": "cash", "amount_euros": "5.00"})
        first = self.client.post("/api/v1/kaffeekasse/bezahlt/", data=body, content_type="application/json", **auth)
        again = self.client.post("/api/v1/kaffeekasse/bezahlt/", data=body, content_type="application/json", **auth)
        self.assertEqual((first.status_code, again.status_code), (201, 201))
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual((first.json()["duplicate"], again.json()["duplicate"]), (False, True))
        self.assertEqual(self.payments().count(), 1)


class CoffeeExportTimezoneTests(CoffeeBase):
    def test_export_uses_station_local_time(self):
        utc = dt.datetime(2026, 1, 31, 23, 30, tzinfo=dt.timezone.utc)  # Berlin: 1. Februar, 00:30
        entry = CoffeeEntry.objects.create(station=self.station, member=self.member, amount_cents=100,
                                           reason="Einzahlung", created_by=self.member)
        movement = CoffeeCashMovement.objects.create(station=self.station, kind=CoffeeCashMovement.Kind.PURCHASE,
                                                     amount_cents=-300, reason="Milch", created_by=self.cashier)
        CoffeeEntry.objects.filter(pk=entry.pk).update(created_at=utc)
        CoffeeCashMovement.objects.filter(pk=movement.pk).update(created_at=utc + dt.timedelta(hours=6))
        self.client.force_login(self.cashier)
        csv = self.client.get(reverse("coffee_export")).content.decode("utf-8")
        self.assertIn("2026-02-01 00:30;Person;Mara Muster", csv)
        self.assertIn("2026-02-01 06:30;Kasse", csv)
        self.assertNotIn("2026-01-31 23:30", csv)


@override_settings(FEEDBACK_ENABLED=True)
class FeedbackOperatorTests(TestCase):
    def setUp(self):
        self.home = Station.objects.create(name="Betreiberwache", slug="betrieb")
        self.other = Station.objects.create(name="Wache Nord", slug="wache-nord")
        self.operator = User.objects.create_user("betreiber", password="x" * 16)
        self.foreign_admin = User.objects.create_user("nord-admin", password="x" * 16)
        Membership.objects.create(user=self.operator, station=self.home, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.foreign_admin, station=self.other, role=Membership.Role.ADMIN)
        InstallationSetup.objects.create(pk=1, completed_at=timezone.now(), station=self.home)
        self.entry = Feedback.objects.create(kind="bug", message="Knopf reagiert nicht", email="m@example.org")

    def test_admin_of_another_station_cannot_read_or_delete(self):
        self.client.force_login(self.foreign_admin)
        self.assertEqual(self.client.get(reverse("feedback_inbox")).status_code, 404)
        self.client.post(reverse("feedback_delete", args=[self.entry.pk]))
        self.client.post(reverse("feedback_status", args=[self.entry.pk]), {"status": "done"})
        self.entry.refresh_from_db()  # weder gelöscht noch geändert
        self.assertEqual(self.entry.status, Feedback.Status.NEW)
        self.assertNotContains(self.client.get(reverse("station_settings")), reverse("feedback_inbox"))

    def test_operator_reads_and_sees_the_link(self):
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(reverse("feedback_inbox")), "Knopf reagiert nicht")
        self.assertContains(self.client.get(reverse("station_settings")), reverse("feedback_inbox"))

    def test_without_setup_record_the_default_station_is_the_operator(self):
        InstallationSetup.objects.all().delete()
        self.home.slug = settings.DEFAULT_STATION_SLUG
        self.home.save(update_fields=["slug"])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("feedback_inbox")).status_code, 200)
        self.client.force_login(self.foreign_admin)
        self.assertEqual(self.client.get(reverse("feedback_inbox")).status_code, 404)

    def test_status_redirect_stays_on_this_site(self):
        self.client.force_login(self.operator)
        url = reverse("feedback_status", args=[self.entry.pk])
        client = Client(raise_request_exception=False)
        client.force_login(self.operator)
        for target in ("https://evil.example/phish", "//evil.example/", "javascript:alert(1)"):
            with self.subTest(target=target):
                response = client.post(url, {"status": "done", "next": target})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], reverse("feedback_inbox"))
        response = self.client.post(url, {"status": "done", "next": reverse("feedback_inbox") + "?status=done"})
        self.assertEqual(response["Location"], reverse("feedback_inbox") + "?status=done")


class NewsAttachmentLimitTests(TestCase):
    def test_news_post_accepts_at_most_eight_attachments(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from core.api.wachalltag import MAX_ATTACHMENTS_PER_HANDOVER
        from core.test_append_only_guards import PNG

        station = Station.objects.create(name="Wache News", slug="wache-news")
        admin = User.objects.create_user("news-admin", password="x" * 16)
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        post = NewsPost.objects.create(station=station, title="Neu", body="Text", created_by=admin)
        for n in range(MAX_ATTACHMENTS_PER_HANDOVER):
            NewsAttachment.objects.create(post=post, station=station, filename=f"{n}.png", content_type="image/png",
                                          data=PNG, size=len(PNG), uploaded_by=admin)
        self.client.force_login(admin)
        page = self.client.get(reverse("news_detail", args=[post.pk]))
        self.assertNotContains(page, 'name="attachment"')
        upload = SimpleUploadedFile("neu.png", PNG, content_type="image/png")
        response = self.client.post(reverse("news_detail", args=[post.pk]), {"action": "upload", "attachment": upload},
                                    follow=True)
        self.assertContains(response, "Mehr Anhänge sind nicht möglich.")
        self.assertEqual(post.attachments.count(), MAX_ATTACHMENTS_PER_HANDOVER)


class WarehouseStockTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Lager", slug="wache-lager", warehouse_enabled=True)
        self.user = User.objects.create_user("lager", password="x" * 16)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def test_total_stock_skips_recalled_batches_with_and_without_prefetch(self):
        location = StorageLocation.objects.create(station=self.station, slug="lager", name="Lager")
        item = MedicalItem.objects.create(station=self.station, slug="nacl", name="NaCl")
        for lot, recalled, qty in (("A", False, 4), ("B", True, 7), ("C", False, 2)):
            batch = ItemBatch.objects.create(item=item, station=self.station, batch_number=lot, is_recalled=recalled,
                                             manufacturer_exp_date=timezone.localdate() + dt.timedelta(days=90))
            StockItem.objects.create(station=self.station, item=item, batch=batch, location=location, quantity=qty)
        plain = MedicalItem.objects.get(pk=item.pk)
        prefetched = MedicalItem.objects.prefetch_related("stock_items__batch").get(pk=item.pk)
        empty = MedicalItem.objects.create(station=self.station, slug="leer", name="Leer")
        self.assertEqual((plain.total_stock, prefetched.total_stock, empty.total_stock), (6, 6, 0))

    def test_inventory_items_never_trigger_reorder(self):
        # Das Lager spiegelt Inventarstücke nicht mehr (siehe core.test_review_final_core).
        InventoryItem.objects.create(station=self.station, item_id="rtw-schluessel", label="Fahrzeugschlüssel RTW 1",
                                     kind=InventoryItem.Kind.KEY)
        self.assertNotContains(self.client.get(reverse("warehouse_dashboard")), "Fahrzeugschlüssel RTW 1")
        self.assertFalse(MedicalItem.objects.filter(station=self.station, slug="rtw-schluessel").exists())
        self.assertEqual(self.client.get(reverse("warehouse_reorder_proposal")).context["proposals"], [])


class SopAcknowledgementTests(TestCase):
    def test_prefetched_state_is_bound_to_its_user(self):
        station = Station.objects.create(name="Wache SOP", slug="wache-sop")
        reader = User.objects.create_user("leser")
        other = User.objects.create_user("andere")
        sop = SOPDocument.objects.create(station=station, slug="sop", doc_number="SOP-1", title="SOP",
                                         created_by=reader)
        old = SOPRevision.objects.create(sop=sop, version_label="1.0", content_markdown="Alt")
        new = SOPRevision.objects.create(sop=sop, version_label="2.0", content_markdown="Neu")
        SOPRevision.objects.filter(pk=new.pk).update(created_at=old.created_at)  # gleiche Zeit: höhere ID gewinnt
        SOPReceipt.objects.create(station=station, sop=sop, revision=old, user=reader)
        SOPReceipt.objects.create(station=station, sop=sop, revision=new, user=other)
        [listed] = SOPDocument.list_with_ack_state(SOPDocument.objects.filter(pk=sop.pk), reader)
        fresh = SOPDocument.objects.get(pk=sop.pk)
        self.assertEqual((listed.latest_revision, fresh.latest_revision), (new, new))
        self.assertFalse(listed.user_has_acknowledged(reader))
        self.assertTrue(listed.user_has_acknowledged(other))  # fällt auf eine Abfrage zurück
        self.assertFalse(fresh.user_has_acknowledged(reader))


class InstallGuideCommandTests(TestCase):
    def test_daily_commands_use_the_installed_path(self):
        page = self.client.get(reverse("install_guide")).content.decode()
        for command in ("status", "update", "backup", "restore DATEI", "setup-code"):
            self.assertIn(f"<code>sudo /opt/wachbuch/wachbuch {command}</code>", page)
        self.assertNotIn("<code>wachbuch ", page)


class DeployCheckMessageTests(TestCase):
    def _w102(self):
        from core.checks import privacy_security_deployment_checks

        with mock.patch.dict(os.environ, {"CRYPTO_MASTER_KEY": "11" * 32}, clear=False):
            return [w for w in privacy_security_deployment_checks(None) if w.id == "wachbuch.W102"]

    @override_settings(DEMO_MODE=True, DEMO_SANDBOX=False, MFA_REQUIRED=False)
    def test_shared_demo_names_demo_mode_as_the_cause(self):
        [warning] = self._w102()
        self.assertIn("DEMO_MODE", warning.msg)
        self.assertNotIn("MFA_REQUIRED ist deaktiviert", warning.msg)

    @override_settings(DEMO_MODE=False, DEMO_SANDBOX=False, MFA_REQUIRED=False)
    def test_production_without_mfa_keeps_the_old_hint(self):
        [warning] = self._w102()
        self.assertEqual(warning.msg, "MFA_REQUIRED ist deaktiviert.")


class TableScrollContainerTests(TestCase):
    def test_table_wrappers_contain_screen_reader_text(self):
        # .sr-only ist absolut positioniert; ohne positionierten Scrollbereich
        # verbreitert sie auf dem Handy die ganze Seite (z. B. /lager/nachbestellung/).
        static = Path(settings.BASE_DIR) / "core" / "static" / "core"
        modules = (static / "modules.css").read_text()
        app = (static / "app.css").read_text()
        self.assertIn(".table-responsive { position: relative;", modules)
        self.assertRegex(app, r"\.table-wrap \{\n  position: relative;")
