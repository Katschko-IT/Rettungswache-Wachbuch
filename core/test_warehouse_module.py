from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Membership, Station
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation


class WarehouseModuleTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Rettungswache Test Lager",
            slug="rw-test-lager",
            warehouse_enabled=True,
        )
        self.user = User.objects.create_user(
            username="notfallsani_lager",
            first_name="Lisa",
            last_name="Muster",
            password="testpassword123",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.SHIFT_LEAD,
            is_active=True,
        )
        self.client.force_login(self.user)

        self.central_loc = StorageLocation.objects.create(
            station=self.station,
            slug="hauptlager-test",
            name="Zentrallager",
            kind=StorageLocation.Kind.CENTRAL,
        )
        self.vehicle_loc = StorageLocation.objects.create(
            station=self.station,
            slug="rtw-01-test",
            name="RTW 01 Schrank",
            kind=StorageLocation.Kind.VEHICLE,
        )

        today = timezone.localdate()
        # Kühlpflichtiges Medikament mit Out-of-Fridge Regel (Rocuronium)
        self.item_rocuronium = MedicalItem.objects.create(
            station=self.station,
            slug="rocuronium-10mg",
            name="Rocuronium 10 mg/ml (5x5ml)",
            category=MedicalItem.Category.MEDICATION,
            unit=MedicalItem.Unit.AMPOULE,
            pzn="01234567",
            min_stock=5,
            target_stock=15,
            requires_cooling=True,
            room_temp_max_days=84,  # 12 Wochen
        )

        # Normale Charge (noch ungeöffnet im Kühlschrank)
        self.batch_1 = ItemBatch.objects.create(
            item=self.item_rocuronium,
            station=self.station,
            batch_number="LOT-2026-A",
            manufacturer_exp_date=today + timedelta(days=365),  # 1 Jahr
        )
        self.stock_1 = StockItem.objects.create(
            station=self.station,
            item=self.item_rocuronium,
            batch=self.batch_1,
            location=self.central_loc,
            quantity=10,
        )

    def test_dynamic_out_of_fridge_calculation(self):
        today = timezone.localdate()
        # Vor Entnahme: MHD = Hersteller-MHD (365 Tage)
        self.assertEqual(self.batch_1.effective_date, today + timedelta(days=365))

        # Nun wird die Charge auf den RTW entnommen (Kühlkette unterbrochen)
        self.batch_1.out_of_fridge_date = today
        self.batch_1.save()

        # Dynamisches MHD muss nun genau today + 84 Tage (12 Wochen) sein!
        self.assertEqual(self.batch_1.effective_date, today + timedelta(days=84))
        self.assertEqual(self.batch_1.calculated_exp_date, today + timedelta(days=84))

    def test_fefo_urgency_levels(self):
        today = timezone.localdate()

        # 1. OK Level (> 90 Tage)
        self.assertEqual(self.batch_1.urgency["level"], "ok")

        # 2. Warning Level (45 Tage)
        self.batch_1.manufacturer_exp_date = today + timedelta(days=45)
        self.batch_1.save()
        self.assertEqual(self.batch_1.urgency["level"], "warning")

        # 3. Critical Level (15 Tage)
        self.batch_1.manufacturer_exp_date = today + timedelta(days=15)
        self.batch_1.save()
        self.assertEqual(self.batch_1.urgency["level"], "critical")

        # 4. Overdue Level (-3 Tage)
        self.batch_1.manufacturer_exp_date = today - timedelta(days=3)
        self.batch_1.save()
        self.assertEqual(self.batch_1.urgency["level"], "overdue")

        # 5. Recalled Level
        self.batch_1.is_recalled = True
        self.batch_1.save()
        self.assertEqual(self.batch_1.urgency["level"], "recalled")

    def test_stock_transfer_between_locations(self):
        resp = self.client.post(
            reverse("warehouse_stock_transfer", args=[self.batch_1.id]),
            data={
                "source_location": self.central_loc.id,
                "target_location": self.vehicle_loc.id,
                "quantity": 4,
                "mark_out_of_fridge": "on",
                "note": "Aufrüstung RTW",
            },
        )
        self.assertEqual(resp.status_code, 302)

        # Zentrallager muss jetzt 6 haben, RTW 4
        self.stock_1.refresh_from_db()
        self.assertEqual(self.stock_1.quantity, 6)

        rtw_stock = StockItem.objects.filter(batch=self.batch_1, location=self.vehicle_loc).first()
        self.assertIsNotNone(rtw_stock)
        self.assertEqual(rtw_stock.quantity, 4)

        # Audit-Journal prüfen
        mvmnt = StockMovement.objects.filter(batch=self.batch_1, kind=StockMovement.Kind.TRANSFER).first()
        self.assertIsNotNone(mvmnt)
        self.assertEqual(mvmnt.quantity, 4)
        self.assertEqual(mvmnt.source_location, self.central_loc)
        self.assertEqual(mvmnt.target_location, self.vehicle_loc)

    def test_stock_consume_decrements_quantity(self):
        resp = self.client.post(
            reverse("warehouse_stock_consume", args=[self.batch_1.id]),
            data={
                "location_id": self.central_loc.id,
                "quantity": 2,
                "reason": "Notfall-Narkose Patient",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.stock_1.refresh_from_db()
        self.assertEqual(self.stock_1.quantity, 8)

        mvmnt = StockMovement.objects.filter(batch=self.batch_1, kind=StockMovement.Kind.OUTBOUND).first()
        self.assertIsNotNone(mvmnt)
        self.assertEqual(mvmnt.quantity, 2)

    def test_batch_recall_quarantines_and_locks(self):
        resp = self.client.post(
            reverse("warehouse_batch_recall"),
            data={
                "batch_number": "LOT-2026-A",
                "reason": "BfArM-Recall vom 22.10. Wirkstoffgehalt abweichend",
            },
        )
        self.assertEqual(resp.status_code, 302)

        self.batch_1.refresh_from_db()
        self.assertTrue(self.batch_1.is_recalled)
        self.assertIn("BfArM-Recall", self.batch_1.recall_reason)

    def test_views_render(self):
        # Dashboard
        resp = self.client.get(reverse("warehouse_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Rocuronium")

        # Detail view
        resp_detail = self.client.get(reverse("warehouse_item_detail", args=[self.item_rocuronium.slug]))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "LOT-2026-A")

        # CSV Export
        resp_csv = self.client.get(reverse("warehouse_export_fefo"))
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn("text/csv", resp_csv["Content-Type"])
        self.assertIn("LOT-2026-A", resp_csv.content.decode("utf-8-sig"))
