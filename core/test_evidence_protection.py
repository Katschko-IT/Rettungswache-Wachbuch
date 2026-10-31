"""Nachweise geschützt (0.27): kein Nachweis verschwindet durch das Löschen eines Objekts.

Messbares Ziel der Roadmap: „Kein Nachweis lässt sich durch Löschen eines
Objekts entfernen (Negativtests für alle Nachweis-Tabellen).“ Das Verzeichnis
``core/evidence.py`` listet die Nachweis-Tabellen; die Tests hier lesen es aus,
statt eine eigene Liste zu führen.
"""
from __future__ import annotations

import io
from datetime import timedelta
from io import StringIO

from django.apps import apps
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, models
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.coffee_models import CoffeeCashMovement
from core.evidence import EVIDENCE_MODELS, EVIDENCE_NAME_SUFFIXES, NOT_EVIDENCE
from core.fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
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
from core.mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision
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
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation
from core.wiki_models import WikiArticle, WikiRevision

PW = "ein-langes-Passwort-42"


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


PNG = _png()


def _references(model):
    return [f for f in model._meta.concrete_fields if f.many_to_one or f.one_to_one]


class EvidenceRegistryTests(SimpleTestCase):
    """Das Verzeichnis ist vollständig und jeder Nachweis hängt per PROTECT."""

    def test_registry_names_resolve_and_do_not_overlap(self):
        for label in (*EVIDENCE_MODELS, *NOT_EVIDENCE):
            with self.subTest(label=label):
                self.assertIsNotNone(apps.get_model(label))
        self.assertEqual(set(EVIDENCE_MODELS) & set(NOT_EVIDENCE), set())
        self.assertEqual(len(EVIDENCE_MODELS), len(set(EVIDENCE_MODELS)))
        for label, reason in NOT_EVIDENCE.items():
            self.assertTrue(reason.strip(), label)

    def test_every_evidence_reference_is_protect(self):
        for label in EVIDENCE_MODELS:
            model = apps.get_model(label)
            for field in _references(model):
                with self.subTest(model=label, field=field.name):
                    self.assertIs(field.remote_field.on_delete, models.PROTECT)

    def test_append_only_models_are_registered(self):
        """Ein Modell mit Löschschutz in delete() ist ein Nachweis."""
        guarded = set()
        for model in apps.get_app_config("core").get_models():
            delete = model.__dict__.get("delete")
            texts = [c for c in getattr(getattr(delete, "__code__", None), "co_consts", ()) if isinstance(c, str)]
            if any("nicht gelöscht" in text for text in texts):
                guarded.add(model._meta.label)
        self.assertEqual(guarded - set(EVIDENCE_MODELS), set())
        self.assertLessEqual({"core.MaintenanceLog", "core.DeviceRoutineCheck", "core.SOPRevision"}, guarded)

    def test_evidence_like_models_are_classified(self):
        """Neue Modelle mit nachweisähnlichem Namen müssen eingeordnet werden."""
        unclassified = [
            model._meta.label
            for model in apps.get_app_config("core").get_models()
            if model.__name__.endswith(EVIDENCE_NAME_SUFFIXES)
            and model._meta.label not in EVIDENCE_MODELS
            and model._meta.label not in NOT_EVIDENCE
        ]
        self.assertEqual(unclassified, [])

    def test_mpg_and_fleet_evidence_is_listed(self):
        for label in ("core.MaintenanceLog", "core.DeviceRoutineCheck", "core.DeviceTrainingRecord",
                      "core.VehicleHandover", "core.DisinfectionProtocol", "core.SOPRevision", "core.SOPReceipt",
                      "core.Defect", "core.HandoverRevision", "core.WikiRevision"):
            self.assertIn(label, EVIDENCE_MODELS)


class EvidenceRows:
    """Je Nachweis-Modell eine Zeile, in der jeder Fremdschlüssel gesetzt ist."""

    def build_evidence(self) -> dict:
        self.station = s = Station.objects.create(name="Wache Nachweis", slug="wache-nachweis")
        self.user = u = User.objects.create_user("nachweis", password=PW)
        self.other = o = User.objects.create_user("nachweis-zwei", password=PW)
        Membership.objects.create(user=u, station=s, role=Membership.Role.ADMIN)
        Membership.objects.create(user=o, station=s, role=Membership.Role.MEMBER)

        def attachment(model, **parent):
            return model.objects.create(
                station=s, filename="bild.png", content_type="image/png", data=PNG, size=len(PNG),
                uploaded_by=u, **parent,
            )

        handover = HandoverEntry.objects.create(station=s, category="station", title="Übergabe", details="Text", author=u)
        checklist = Checklist.objects.create(station=s, title="Fahrzeugcheck")
        post = NewsPost.objects.create(station=s, title="Neu", body="Text", created_by=u)
        note = PinboardNote.objects.create(station=s, title="Aushang", body="Text", author=u)
        article = WikiArticle.objects.create(station=s, slug="wiki", title="Wiki", body="Text", created_by=u)
        asset = StationAsset.objects.create(station=s, asset_id="trage", label="Trage", updated_by=u)
        inventory = InventoryItem.objects.create(station=s, item_id="schluessel", label="Schlüssel")
        item = MedicalItem.objects.create(station=s, slug="kanuele", name="Venenkanüle")
        batch = ItemBatch.objects.create(
            item=item, station=s, batch_number="L1", manufacturer_exp_date=timezone.localdate() + timedelta(days=365),
        )
        source = StorageLocation.objects.create(station=s, slug="lager", name="Lager")
        target = StorageLocation.objects.create(station=s, slug="rtw", name="RTW")
        vehicle = Vehicle.objects.create(station=s, slug="rtw-1", call_sign="RTW 1", license_plate="MU-RD 1")
        agent = DisinfectantMaster.objects.create(station=s, name="Wischtücher")
        device = MedicalDevice.objects.create(station=s, slug="defi-1", name="Defi")
        sop = SOPDocument.objects.create(station=s, slug="da-1", doc_number="DA-1", title="Dienstanweisung", created_by=u)
        coffee = CoffeeEntry.objects.create(station=s, member=u, amount_cents=100, reason="Einzahlung", created_by=u)
        cash = CoffeeCashMovement.objects.create(
            station=s, kind=CoffeeCashMovement.Kind.PURCHASE, amount_cents=-300, reason="Milch", created_by=u,
        )
        defect = Defect.objects.create(station=s, title="Mangel", created_by=u, owner=o, medical_device=device)
        revision = SOPRevision.objects.create(sop=sop, version_label="1.0", content_markdown="Text", approved_by=u)
        return {
            "core.AuditEvent": AuditEvent.objects.create(actor=u, station=s, action="test.done", object_type="Station"),
            "core.HandoverEntry": handover,
            "core.HandoverRevision": HandoverRevision.objects.create(
                handover=handover, version=99, snapshot={"title": "x"}, changed_by=u),
            "core.HandoverAck": HandoverAck.objects.create(station=s, handover=handover, user=o),
            "core.HandoverAttachment": attachment(HandoverAttachment, handover=handover),
            "core.NewsAttachment": attachment(NewsAttachment, post=post),
            "core.PinboardAttachment": attachment(PinboardAttachment, note=note),
            "core.ChecklistCompletion": ChecklistCompletion.objects.create(station=s, checklist=checklist, completed_by=u),
            "core.CoffeeEntry": CoffeeEntry.objects.create(
                station=s, member=u, amount_cents=-100, reason="Korrektur", created_by=o, correction_of=coffee),
            "core.CoffeeCashMovement": CoffeeCashMovement.objects.create(
                station=s, kind=CoffeeCashMovement.Kind.PURCHASE, amount_cents=300, reason="Korrektur",
                witness=o, created_by=u, correction_of=cash),
            "core.Defect": defect,
            "core.DefectEvent": DefectEvent.objects.create(
                defect=defect, station=s, kind=DefectEvent.Kind.CREATED, actor=u),
            "core.DefectAttachment": attachment(DefectAttachment, defect=defect),
            "core.AssetEvent": AssetEvent.objects.create(asset=asset, station=s, to_status="oob", actor=u),
            "core.InventoryEvent": InventoryEvent.objects.create(
                item=inventory, station=s, action=InventoryEvent.Action.CHECKOUT, actor=u, holder=o),
            "core.StockMovement": StockMovement.objects.create(
                station=s, item=item, batch=batch, source_location=source, target_location=target, quantity=1,
                kind=StockMovement.Kind.TRANSFER, actor=u),
            "core.WikiRevision": WikiRevision.objects.create(
                article=article, number=99, title="Wiki", body="Text", edited_by=u, app_version="t"),
            "core.VehicleHandover": VehicleHandover.objects.create(
                station=s, vehicle=vehicle, crew_member=u, mileage=10000),
            "core.DisinfectionProtocol": DisinfectionProtocol.objects.create(
                station=s, vehicle=vehicle, performed_by=u, disinfectant=agent),
            "core.MaintenanceLog": MaintenanceLog.objects.create(
                device=device, station=s, kind=MaintenanceLog.Kind.STK, performed_by="Service", created_by=u),
            "core.DeviceRoutineCheck": DeviceRoutineCheck.objects.create(station=s, device=device, performed_by=u),
            "core.DeviceTrainingRecord": DeviceTrainingRecord.objects.create(
                station=s, device=device, trainee=o, instructor="Nora"),
            "core.SOPRevision": revision,
            "core.SOPReceipt": SOPReceipt.objects.create(station=s, sop=sop, revision=revision, user=o),
        }


class ObjectDeletionNegativeTests(EvidenceRows, TestCase):
    """NEGATIV: Jedes Objekt, auf das ein Nachweis zeigt, lässt sich nicht löschen."""

    def setUp(self):
        self.rows = self.build_evidence()

    def test_every_evidence_model_has_a_row_with_all_references_set(self):
        self.assertEqual(set(self.rows), set(EVIDENCE_MODELS))
        for label, row in self.rows.items():
            for field in _references(type(row)):
                with self.subTest(model=label, field=field.name):
                    self.assertIsNotNone(getattr(row, field.attname))

    def test_deleting_any_referenced_object_keeps_the_evidence(self):
        for label, row in self.rows.items():
            model = type(row)
            for field in _references(model):
                target = getattr(row, field.name)
                with self.subTest(model=label, field=field.name, target=type(target).__name__):
                    before = model._base_manager.filter(pk=row.pk).values().get()
                    # Der Weg über den Collector, wie ihn Django-Admin, Demo und
                    # künftiger Code nehmen; model.delete() eigener Schutz ist umgangen.
                    with self.assertRaises(ProtectedError) as raised:
                        type(target)._base_manager.filter(pk=target.pk).delete()
                    self.assertIn(row, raised.exception.protected_objects)
                    self.assertEqual(model._base_manager.filter(pk=row.pk).values().get(), before)
                    self.assertTrue(type(target)._base_manager.filter(pk=target.pk).exists())

    def test_instance_delete_of_objects_is_blocked(self):
        for label in ("core.Vehicle", "core.MedicalDevice", "core.SOPDocument", "core.DisinfectantMaster",
                      "core.HandoverEntry", "core.WikiArticle"):
            model = apps.get_model(label)
            obj = model.objects.get(station=self.station)
            with self.subTest(model=label), self.assertRaises(ProtectedError):
                obj.delete()
            self.assertTrue(model.objects.filter(pk=obj.pk).exists())

    def test_cascading_parents_still_protect_movements(self):
        movement = self.rows["core.StockMovement"]
        # Artikel: Chargen hängen per CASCADE am Artikel, die Buchung per PROTECT an der Charge.
        with self.assertRaises(ProtectedError):
            MedicalItem.objects.filter(pk=movement.item_id).delete()
        # Übergeordneter Lagerort: Unterorte hängen per CASCADE, die Buchung am Unterort.
        parent = StorageLocation.objects.create(station=self.station, slug="halle", name="Fahrzeughalle")
        StorageLocation.objects.filter(pk=movement.target_location_id).update(parent=parent)
        StockItem.objects.create(station=self.station, item=movement.item, batch=movement.batch,
                                 location=movement.target_location, quantity=1)
        with self.assertRaises(ProtectedError):
            StorageLocation.objects.filter(pk=parent.pk).delete()
        self.assertTrue(StockMovement.objects.filter(pk=movement.pk).exists())

    def test_deleting_a_user_with_evidence_is_refused(self):
        with self.assertRaises(ProtectedError):
            User.objects.filter(pk=self.other.pk).delete()
        self.assertTrue(DeviceTrainingRecord.objects.filter(trainee=self.other).exists())


@override_settings(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)
class DemoPurgeStillRemovesEvidenceTests(TestCase):
    """Demo-Wachen werden trotz PROTECT vollständig gelöscht (Eigentümerrechte)."""

    def setUp(self):
        cache.clear()

    def test_demo_station_purge_removes_all_evidence(self):
        from core.demo_sandbox import create_sandbox, purge_sandbox

        sandbox, users = create_sandbox()
        station = sandbox.station
        admin = users["demo-admin"]
        device = MedicalDevice.objects.filter(station=station).first()
        vehicle = Vehicle.objects.filter(station=station).first()
        agent = DisinfectantMaster.objects.filter(station=station).first()
        sop = SOPDocument.objects.filter(station=station).first()
        created = [
            DeviceRoutineCheck.objects.create(station=station, device=device, performed_by=admin),
            MaintenanceLog.objects.create(device=device, station=station, kind=MaintenanceLog.Kind.DGUV,
                                          performed_by="Service", created_by=admin),
            DeviceTrainingRecord.objects.create(station=station, device=device, trainee=admin, instructor="Nora"),
            Defect.objects.create(station=station, title="Gerätemangel", created_by=admin, medical_device=device),
            VehicleHandover.objects.create(station=station, vehicle=vehicle, crew_member=admin, mileage=99999),
            DisinfectionProtocol.objects.create(station=station, vehicle=vehicle, performed_by=admin, disinfectant=agent),
        ]
        revision = SOPRevision.objects.create(sop=sop, version_label="9.9", content_markdown="Neu", approved_by=admin)
        created += [revision, SOPReceipt.objects.create(station=station, sop=sop, revision=revision, user=admin)]
        real = Station.objects.create(name="Echte Wache", slug="echte-wache")
        real_user = User.objects.create_user("echt", password=PW)
        real_device = MedicalDevice.objects.create(station=real, slug="defi-echt", name="Defi")
        real_check = DeviceRoutineCheck.objects.create(station=real, device=real_device, performed_by=real_user)

        purge_sandbox(sandbox)

        self.assertFalse(Station.objects.filter(pk=station.pk).exists())
        for row in created:
            with self.subTest(model=type(row).__name__):
                self.assertFalse(type(row)._base_manager.filter(pk=row.pk).exists())
        for label in EVIDENCE_MODELS:
            model = apps.get_model(label)
            if any(field.name == "station" for field in model._meta.concrete_fields):
                with self.subTest(model=label):
                    self.assertFalse(model._base_manager.filter(station_id=station.pk).exists())
        self.assertTrue(DeviceRoutineCheck.objects.filter(pk=real_check.pk).exists())
        connection.check_constraints()


@override_settings(DEMO_MODE=True, DEMO_SANDBOX=False)
class SharedDemoResetWithProtectTests(TestCase):
    def test_reset_keeps_a_real_defect_on_a_demo_device_without_the_device(self):
        from core.demo_modules import reset_module_demo

        call_command("load_demo_data", stdout=StringIO())
        station = Station.get_default()
        device = MedicalDevice.objects.filter(station=station, slug__startswith="demo-").first()
        reporter = User.objects.create_user("echte-person", password=PW)
        defect = Defect.objects.create(station=station, title="Echter Mangel", created_by=reporter,
                                       medical_device=device)
        reset_module_demo(station)
        self.assertFalse(MedicalDevice.objects.filter(station=station, slug__startswith="demo-").exists())
        defect.refresh_from_db()
        self.assertIsNone(defect.medical_device)
        call_command("load_demo_data", "--reset", stdout=StringIO())
        connection.check_constraints()

    def test_first_seed_sends_no_delete_or_update_to_mpg_evidence(self):
        from core.demo_modules import reset_module_demo

        station = Station.get_default()
        with CaptureQueriesContext(connection) as ctx:
            reset_module_demo(station)
        tables = ("core_maintenancelog", "core_deviceroutinecheck", "core_stockmovement")
        writes = [
            q["sql"] for q in ctx.captured_queries
            if any(table in q["sql"] for table in tables)
            and q["sql"].lstrip().upper().startswith(("DELETE", "UPDATE"))
        ]
        self.assertEqual(writes, [])


class DatabaseRevokeTests(TestCase):
    def test_grant_revokes_update_and_delete_on_mpg_evidence(self):
        from core.test_review_final_core import app_role_read_only_tables

        read_only = app_role_read_only_tables()
        self.assertLessEqual({"core_maintenancelog", "core_deviceroutinecheck", "core_coffeeentry",
                              "core_stockmovement", "core_auditevent"}, read_only)
        # Bewusst noch ohne REVOKE: Die einmalige Bereinigung der Altbestände
        # (0.27) leert IP und Browser der Quittierungen per UPDATE.
        self.assertNotIn("core_sopreceipt", read_only)


class DisinfectantAdminTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Mittel", slug="wache-mittel", fleet_enabled=True)
        self.root = User.objects.create_superuser("root-mittel", "root@example.org", PW)
        self.agent = DisinfectantMaster.objects.create(station=self.station, name="Wischtücher")
        self.client.force_login(self.root)

    def test_admin_offers_no_delete(self):
        response = self.client.get(reverse("admin:core_disinfectantmaster_delete", args=[self.agent.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("admin:core_disinfectantmaster_delete", args=[self.agent.pk]),
                                    {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(DisinfectantMaster.objects.filter(pk=self.agent.pk).exists())
        changelist = self.client.get(reverse("admin:core_disinfectantmaster_changelist"))
        self.assertEqual(changelist.status_code, 200)
        self.assertNotContains(changelist, "delete_selected")

    def _form(self, agent, **changes):
        from core.admin import DisinfectantMasterAdminForm

        data = {
            "station": agent.station_id, "name": agent.name, "manufacturer": agent.manufacturer,
            "spectrum": agent.spectrum, "default_exposure_minutes": agent.default_exposure_minutes,
            "is_vah_listed": "on" if agent.is_vah_listed else "", "is_active": "on" if agent.is_active else "",
        }
        data.update(changes)
        return DisinfectantMasterAdminForm(data=data, instance=agent)

    def test_last_agent_in_use_cannot_be_retired(self):
        form = self._form(self.agent, is_active="")
        self.assertFalse(form.is_valid())
        self.assertIn("is_active", form.errors)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.is_active)

    def test_agent_can_be_retired_when_another_is_in_use(self):
        DisinfectantMaster.objects.create(station=self.station, name="Sprühdesinfektion")
        other_station = Station.objects.create(name="Andere Wache", slug="andere-wache-mittel")
        DisinfectantMaster.objects.create(station=other_station, name="Wischtücher")
        form = self._form(self.agent, is_active="")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_active)

    def test_agent_in_use_elsewhere_does_not_count(self):
        other_station = Station.objects.create(name="Andere Wache", slug="andere-wache-mittel-2")
        DisinfectantMaster.objects.create(station=other_station, name="Wischtücher")
        self.assertFalse(self._form(self.agent, is_active="").is_valid())
