"""Abfragezahl der Hauptseiten wächst nicht mit der Datenmenge.

Mit den kleinen Demodaten fielen die N+1-Abfragen nicht auf (Review
2026-10-29, Paket C1). Jede Seite wird darum mit wenigen und mit vielen
Einträgen geladen; die Zahl der Abfragen muss gleich bleiben und unter einer
Obergrenze liegen. Anhangslisten lesen den Dateiinhalt (BinaryField ``data``)
nicht mit.
"""
from __future__ import annotations

import io
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import (
    HandoverAttachment,
    HandoverEntry,
    Membership,
    NewsAcknowledgement,
    NewsAttachment,
    NewsPost,
    PinboardAttachment,
    PinboardNote,
    Station,
)
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision
from core.task_board import ensure_default_station_tasks
from core.wachalltag_models import Defect, DefectAttachment
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StorageLocation


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


PNG = _png()


class QueryCountMixin:
    def queries(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return ctx

    def assert_constant(self, url, grow, *, upper):
        """Abfragen vor und nach ``grow()`` gleich und höchstens ``upper``."""
        self.client.get(url)  # Erstaufruf legt ggf. Standarddaten an
        before = self.queries(url)
        grow()
        after = self.queries(url)
        self.assertEqual(
            len(after), len(before),
            f"{url}: {len(before)} → {len(after)} Abfragen\n" + "\n".join(q["sql"] for q in after.captured_queries),
        )
        self.assertLessEqual(len(after), upper, url)
        return after


class PageQueryCountTests(QueryCountMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.station = Station.objects.create(
            name="Wache Last", slug="wache-last", pinboard_enabled=True, warehouse_enabled=True,
            orga_enabled=True, fleet_enabled=True, mpg_enabled=True, tasks_enabled=True,
        )
        cls.admin = User.objects.create_user("last-admin", password="pw-123456789")
        Membership.objects.create(user=cls.admin, station=cls.station, role=Membership.Role.ADMIN)
        cls.other = User.objects.create_user("last-member", password="pw-123456789")
        Membership.objects.create(user=cls.other, station=cls.station, role=Membership.Role.MEMBER)
        cls.counter = 0

    def setUp(self):
        self.client.force_login(self.admin)

    def _n(self):
        type(self).counter += 1
        return type(self).counter

    def add_sops(self, count):
        for _ in range(count):
            n = self._n()
            sop = SOPDocument.objects.create(
                station=self.station, slug=f"sop-{n}", doc_number=f"SOP-{n}", title=f"SOP {n}",
                created_by=self.admin,
            )
            SOPRevision.objects.create(sop=sop, version_label="1.0", content_markdown="Alt")
            latest = SOPRevision.objects.create(sop=sop, version_label="1.1", content_markdown="Neu")
            if n % 2:
                SOPReceipt.objects.create(station=self.station, sop=sop, revision=latest, user=self.admin)
            SOPReceipt.objects.create(station=self.station, sop=sop, revision=latest, user=self.other)

    def add_items(self, count):
        location, _created = StorageLocation.objects.get_or_create(
            station=self.station, slug="last-lager", defaults={"name": "Lager"},
        )
        for _ in range(count):
            n = self._n()
            item = MedicalItem.objects.create(station=self.station, slug=f"artikel-{n}", name=f"Artikel {n}",
                                              min_stock=10)
            for lot, recalled in (("A", False), ("B", True)):
                batch = ItemBatch.objects.create(
                    item=item, station=self.station, batch_number=f"{lot}{n}", is_recalled=recalled,
                    manufacturer_exp_date=timezone.localdate() + timedelta(days=20 + n),
                )
                StockItem.objects.create(station=self.station, item=item, batch=batch, location=location, quantity=3)

    def test_dashboard(self):
        self.add_sops(1)
        self.add_items(1)
        self.assert_constant(reverse("dashboard"), lambda: (self.add_sops(12), self.add_items(12)), upper=36)

    def test_dashboard_counts_pending_sops_for_the_viewer(self):
        self.add_sops(4)  # zwei davon hat der Admin quittiert
        response = self.client.get(reverse("dashboard"))
        cards = {item["key"]: item for item in response.context["attention_items"] + response.context["calm_items"]}
        self.assertEqual(cards["orga"]["value"], 2)

    def test_orga_dashboard(self):
        self.add_sops(1)
        after = self.assert_constant(reverse("orga_dashboard"), lambda: self.add_sops(15), upper=18)
        # Nur die eigenen Quittungen, nicht die aller Beschäftigten.
        receipt_queries = [q["sql"] for q in after.captured_queries if 'FROM "core_sopreceipt"' in q["sql"]]
        self.assertTrue(receipt_queries)
        self.assertTrue(all('"user_id" = ' in sql for sql in receipt_queries), receipt_queries)

    def test_warehouse_dashboard(self):
        self.add_items(2)
        self.assert_constant(reverse("warehouse_dashboard"), lambda: self.add_items(15), upper=22)

    def test_warehouse_reorder(self):
        self.add_items(2)
        self.assert_constant(reverse("warehouse_reorder_proposal"), lambda: self.add_items(15), upper=13)

    def test_news_index(self):
        def add_posts(count, archived=False):
            for _ in range(count):
                n = self._n()
                post = NewsPost.objects.create(station=self.station, title=f"News {n}", body="Text",
                                               created_by=self.admin)
                NewsAcknowledgement.objects.create(post=post, user=self.admin)
                NewsAttachment.objects.create(post=post, station=self.station, filename="a.png",
                                              content_type="image/png", data=PNG, size=len(PNG),
                                              uploaded_by=self.admin)
                if archived:
                    NewsAcknowledgement.objects.create(post=post, user=self.other)
                    NewsPost.objects.filter(pk=post.pk).update(archived_at=post.created_at)

        add_posts(1)
        add_posts(1, archived=True)
        after = self.assert_constant(
            reverse("news_index"), lambda: (add_posts(10), add_posts(10, archived=True)), upper=15,
        )
        self.assertNotIn('"core_newsattachment"."data"', " ".join(q["sql"] for q in after.captured_queries))
        page = self.client.get(reverse("news_index")).content.decode()
        self.assertIn("mit Anhang", page)
        self.assertIn("1 von 2 gelesen", page)

    def test_pinboard(self):
        def add_notes(count):
            for _ in range(count):
                n = self._n()
                note = PinboardNote.objects.create(station=self.station, title=f"Aushang {n}", body="Text",
                                                   author=self.admin)
                PinboardAttachment.objects.create(note=note, station=self.station, filename=f"plan-{n}.png",
                                                  content_type="image/png", data=PNG, size=len(PNG),
                                                  uploaded_by=self.admin)

        add_notes(1)
        after = self.assert_constant(reverse("pinboard"), lambda: add_notes(10), upper=13)
        self.assertNotIn('"core_pinboardattachment"."data"', " ".join(q["sql"] for q in after.captured_queries))
        self.assertContains(self.client.get(reverse("pinboard")), "plan-")

    def test_ensure_default_tasks_takes_no_lock_once_created(self):
        ensure_default_station_tasks(self.station)
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(ensure_default_station_tasks(self.station), 0)
        self.assertEqual(len(ctx), 1, [q["sql"] for q in ctx.captured_queries])


class AttachmentListsSkipFileContentTests(TestCase):
    """Detailseiten zeigen Name und Größe; der Inhalt bleibt in der Datenbank."""

    @classmethod
    def setUpTestData(cls):
        cls.station = Station.objects.create(name="Wache Anhang", slug="wache-anhang")
        cls.admin = User.objects.create_user("anhang-admin", password="pw-123456789")
        Membership.objects.create(user=cls.admin, station=cls.station, role=Membership.Role.ADMIN)
        cls.handover = HandoverEntry.objects.create(station=cls.station, category="info", title="Ü",
                                                    details="Text", author=cls.admin)
        cls.defect = Defect.objects.create(station=cls.station, title="Mangel", created_by=cls.admin)
        cls.post = NewsPost.objects.create(station=cls.station, title="News", body="Text", created_by=cls.admin)
        common = {"station": cls.station, "filename": "bild.png", "content_type": "image/png",
                  "data": PNG, "size": len(PNG), "uploaded_by": cls.admin}
        HandoverAttachment.objects.create(handover=cls.handover, **common)
        DefectAttachment.objects.create(defect=cls.defect, **common)
        NewsAttachment.objects.create(post=cls.post, **common)

    def setUp(self):
        self.client.force_login(self.admin)

    def assert_no_data_column(self, url, table):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bild")
        sql = " ".join(q["sql"] for q in ctx.captured_queries)
        self.assertIn(f'"{table}"', sql)
        self.assertNotIn(f'"{table}"."data"', sql)

    def test_handover_detail(self):
        self.assert_no_data_column(reverse("handover_detail", args=[self.handover.pk]), "core_handoverattachment")

    def test_defect_detail(self):
        self.assert_no_data_column(reverse("defect_detail_web", args=[self.defect.pk]), "core_defectattachment")

    def test_news_detail(self):
        self.assert_no_data_column(reverse("news_detail", args=[self.post.pk]), "core_newsattachment")

    def test_api_defect_listings(self):
        from core.api.views import DEFAULT_MOBILE_SCOPES, generate_api_token
        from core.models import ApiToken

        raw, token_hash, prefix = generate_api_token()
        ApiToken.objects.create(user=self.admin, label="Test", token_prefix=prefix, token_hash=token_hash,
                                scopes=list(DEFAULT_MOBILE_SCOPES))
        for url in (f"/api/v1/defects/{self.defect.pk}/", f"/api/v1/defects/{self.defect.pk}/attachments/"):
            with self.subTest(url=url), CaptureQueriesContext(connection) as ctx:
                response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {raw}")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIn("bild", response.content.decode())
                self.assertNotIn('"core_defectattachment"."data"', " ".join(q["sql"] for q in ctx.captured_queries))
