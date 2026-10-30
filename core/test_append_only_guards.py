"""Append-only-Tabellen: Ändern und Löschen über das ORM schlagen fehl.

AGENTS.md §4 verlangt append-only für Audit, Kaffeekasse, Checklisten-Abschlüsse
und Übergaberevisionen; dieselbe Regel gilt für Ereignis-, Anhangs- und
Buchungstabellen. Jeder Fall prüft die konkrete Meldung, damit ein anderer
Fehler (etwa ProtectedError durch einen Fremdschlüssel) den fehlenden Schutz
nicht verdeckt. Die Datenbank-Sperre (REVOKE UPDATE, DELETE) prüft
``core.tests`` beim Befehl ``grant_database_access``.
"""
from __future__ import annotations

import io
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.coffee_models import CoffeeCashMovement
from core.models import (
    AuditEvent,
    Checklist,
    ChecklistCompletion,
    CoffeeEntry,
    HandoverAttachment,
    HandoverEntry,
    HandoverRevision,
    Membership,
    NewsAttachment,
    NewsPost,
    PinboardAttachment,
    PinboardNote,
    Station,
)
from core.wachalltag_models import (
    AssetEvent,
    Defect,
    DefectAttachment,
    DefectEvent,
    HandoverAck,
    InventoryEvent,
    InventoryItem,
    StationAsset,
)
from core.warehouse_models import ItemBatch, MedicalItem, StockMovement, StorageLocation
from core.wiki_models import WikiArticle, WikiRevision


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


PNG = _png()


class AppendOnlyGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.station = Station.objects.create(name="Wache Journal", slug="wache-journal")
        cls.user = User.objects.create_user("journal", password="pw-123456789")
        Membership.objects.create(user=cls.user, station=cls.station, role=Membership.Role.ADMIN)
        cls.handover = HandoverEntry.objects.create(
            station=cls.station, category="info", title="Übergabe", details="Text", author=cls.user,
        )
        cls.defect = Defect.objects.create(station=cls.station, title="Mangel", created_by=cls.user)
        cls.asset = StationAsset.objects.create(station=cls.station, asset_id="defi", label="Defi")
        cls.inventory = InventoryItem.objects.create(station=cls.station, item_id="schluessel", label="Schlüssel")
        cls.checklist = Checklist.objects.create(station=cls.station, title="Fahrzeugcheck")
        cls.post = NewsPost.objects.create(station=cls.station, title="Neu", body="Text", created_by=cls.user)
        cls.note = PinboardNote.objects.create(station=cls.station, title="Aushang", body="Text", author=cls.user)
        cls.article = WikiArticle.objects.create(station=cls.station, slug="sop", title="SOP", body="Text")
        cls.item = MedicalItem.objects.create(station=cls.station, slug="kanuele", name="Venenkanüle")
        cls.batch = ItemBatch.objects.create(
            item=cls.item, station=cls.station, batch_number="L1",
            manufacturer_exp_date=timezone.localdate() + timedelta(days=365),
        )
        cls.location = StorageLocation.objects.create(station=cls.station, slug="lager", name="Lager")

    def _attachment(self, model, **parent):
        return model.objects.create(
            station=self.station, filename="bild.png", content_type="image/png", data=PNG, size=len(PNG),
            uploaded_by=self.user, **parent,
        )

    def cases(self):
        """(Name, Fabrik, zu änderndes Feld, Teil der Änderungs- und der Löschmeldung)."""
        changed = "dürfen nicht verändert werden"
        deleted = "dürfen nicht gelöscht werden"
        return [
            ("AuditEvent", lambda: AuditEvent.objects.create(
                actor=self.user, station=self.station, action="test.done", object_type="station"),
             "action", "Audit-Ereignisse " + changed, "Audit-Ereignisse " + deleted),
            ("HandoverRevision", lambda: HandoverRevision.objects.create(
                handover=self.handover, version=99, snapshot={"title": "x"}, changed_by=self.user),
             "snapshot", "Übergaberevisionen " + changed, "Übergaberevisionen " + deleted),
            ("CoffeeEntry", lambda: CoffeeEntry.objects.create(
                station=self.station, member=self.user, amount_cents=100, reason="Einzahlung", created_by=self.user),
             "reason", "Kassenbuchungen " + changed, "Kassenbuchungen " + deleted),
            ("CoffeeCashMovement", lambda: CoffeeCashMovement.objects.create(
                station=self.station, kind=CoffeeCashMovement.Kind.PURCHASE, amount_cents=-300,
                reason="Milch", created_by=self.user),
             "reason", "Kassenbewegungen " + changed, "Kassenbewegungen " + deleted),
            ("ChecklistCompletion", lambda: ChecklistCompletion.objects.create(
                station=self.station, checklist=self.checklist, completed_by=self.user),
             "note", "Checklisten-Abschlüsse " + changed, "Checklisten-Abschlüsse " + deleted),
            ("DefectEvent", lambda: DefectEvent.objects.create(
                defect=self.defect, station=self.station, kind=DefectEvent.Kind.CREATED, actor=self.user),
             "to_status", "Mangel-Ereignisse " + changed, "Mangel-Ereignisse " + deleted),
            ("AssetEvent", lambda: AssetEvent.objects.create(
                asset=self.asset, station=self.station, to_status="oob", actor=self.user),
             "note", "Asset-Ereignisse " + changed, "Asset-Ereignisse " + deleted),
            ("HandoverAck", lambda: HandoverAck.objects.create(
                station=self.station, handover=self.handover, user=self.user),
             "created_at", "Quittierungen " + changed, "Quittierungen " + deleted),
            ("InventoryEvent", lambda: InventoryEvent.objects.create(
                item=self.inventory, station=self.station, action=InventoryEvent.Action.CHECKOUT, actor=self.user),
             "action", "Inventar-Ereignisse " + changed, "Inventar-Ereignisse " + deleted),
            ("DefectAttachment", lambda: self._attachment(DefectAttachment, defect=self.defect),
             "filename", "Mangel-Anhänge " + changed, "Mangel-Anhänge " + deleted),
            ("HandoverAttachment", lambda: self._attachment(HandoverAttachment, handover=self.handover),
             "filename", "Übergabe-Anhänge " + changed, "Übergabe-Anhänge " + deleted),
            ("NewsAttachment", lambda: self._attachment(NewsAttachment, post=self.post),
             "filename", "Anhänge " + changed, "Anhänge " + deleted),
            ("PinboardAttachment", lambda: self._attachment(PinboardAttachment, note=self.note),
             "filename", "Anhänge " + changed, "Anhänge " + deleted),
            ("WikiRevision", lambda: WikiRevision.objects.create(
                article=self.article, number=99, title="SOP", body="Text", edited_by=self.user, app_version="t"),
             "body", "Wiki-Revisionen " + changed, "Wiki-Revisionen " + deleted),
            ("StockMovement", lambda: StockMovement.objects.create(
                station=self.station, item=self.item, batch=self.batch, target_location=self.location,
                quantity=5, kind=StockMovement.Kind.INBOUND, actor=self.user),
             "note", "Materialbuchungen sind revisionssicher und " + changed,
             "Materialbuchungen " + deleted),
        ]

    def test_rows_cannot_be_changed_or_deleted(self):
        for name, factory, field, change_message, delete_message in self.cases():
            with self.subTest(model=name):
                row = factory()
                model = type(row)
                original = model.objects.filter(pk=row.pk).values().get()
                current = getattr(row, field)
                if isinstance(current, dict):
                    setattr(row, field, {**current, "geändert": True})
                elif isinstance(current, int):
                    setattr(row, field, current + 1)
                else:
                    setattr(row, field, f"{current}-geändert")
                with self.assertRaisesMessage(ValidationError, change_message):
                    row.save()
                with self.assertRaisesMessage(ValidationError, delete_message):
                    row.delete()
                self.assertEqual(model.objects.filter(pk=row.pk).values().get(), original)

    def test_every_guarded_model_is_covered(self):
        """Neue append-only-Modelle gehören in die Liste oben."""
        from django.apps import apps

        guarded = set()
        for model in apps.get_app_config("core").get_models():
            delete = model.__dict__.get("delete")
            texts = [c for c in getattr(getattr(delete, "__code__", None), "co_consts", ()) if isinstance(c, str)]
            if any("nicht gelöscht" in text for text in texts):
                guarded.add(model.__name__)
        covered = {case[0] for case in self.cases()}
        self.assertEqual(guarded - covered, set())
        self.assertIn("StockMovement", guarded)
