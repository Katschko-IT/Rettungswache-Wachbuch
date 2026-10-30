"""Regressionen der Abschlussreview, Paket F4: Datenbankfehler im Kern.

Die CI läuft auf SQLite, das ``SELECT ... FOR UPDATE`` stillschweigend
weglässt. Zwei Fehler zeigten sich deshalb nur auf PostgreSQL (jede
Docker-Installation und die öffentliche Demo):

- „Ausgeben“/„Zurückgeben“ unter /geraete/ sperrte über einen LEFT OUTER JOIN
  (``holder`` ist nullbar) – PostgreSQL lehnt FOR UPDATE auf der nullbaren
  Seite ab, die Seite antwortete mit 500.
- Die Gegenbuchung in der Kaffeekasse sperrte ``core_coffeeentry``. FOR UPDATE
  verlangt das UPDATE-Recht, das ``grant_database_access`` der App-Rolle auf
  den append-only-Tabellen entzieht.

``record_row_locks`` hält deshalb für jede kompilierte Abfrage mit
``select_for_update`` fest, welche Tabellen PostgreSQL sperren würde und ob
eine davon auf der nullbaren Seite eines Outer Joins liegt.

Außerdem: Schlüssel, Funkgeräte und Pool-Geräte aus „Geräte & Fahrzeuge“ sind
kein Lagermaterial. Die Lagerübersicht spiegelt sie nicht mehr, und Migration
0066 räumt die alten, unberührten Spiegelungen auf, damit sie weder als
„Kein Bestand“ noch als „Unter Mindestbestand (0 von 5)“ erscheinen.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib
import io
import os
import re
from unittest import mock

from django.apps import apps as global_apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import QuerySet
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.constants import LOUTER
from django.db.models.sql.datastructures import Join
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.display import display_payload
from core.models import CoffeeEntry, Membership, Station
from core.wachalltag_models import InventoryEvent, InventoryItem
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StorageLocation


def app_role_read_only_tables() -> set[str]:
    """Tabellen, auf denen ``grant_database_access`` der App-Rolle UPDATE/DELETE entzieht."""
    executed = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, statement):
            executed.append(statement)

    env = {"APP_DB_USER": "rwsth_app", "FEED_DB_USER": "rwsth_feed", "BACKUP_DB_USER": "rwsth_backup",
           "PUSH_DB_USER": "rwsth_push", "POSTGRES_USER": "rwsth_owner", "POSTGRES_DB": "rwsth"}
    with mock.patch.dict(os.environ, env), mock.patch(
        "core.management.commands.grant_database_access.connection.cursor", return_value=Cursor(),
    ):
        call_command("grant_database_access", stdout=io.StringIO())
    tables = set()
    for statement in executed:
        match = re.fullmatch(r"REVOKE UPDATE, DELETE ON (.+) FROM rwsth_app", statement)
        if match:
            tables.update(name.strip() for name in match.group(1).split(","))
    return tables


def _locked_tables(query, joins) -> set[str]:
    """Tabellen, die PostgreSQL bei dieser Abfrage mit FOR UPDATE sperrt."""
    if not query.select_for_update_of:
        return {join.table_name for join in joins}
    tables = set()
    for name in query.select_for_update_of:
        model = query.model
        if name != "self":
            for part in name.split("__"):
                model = model._meta.get_field(part).related_model
        tables.add(model._meta.db_table)
    return tables


@contextlib.contextmanager
def record_row_locks():
    """Sammelt je ``select_for_update``-Abfrage die gesperrten und die nullbar gejointen Tabellen.

    Gemessen in ``get_from_clause``: Dort gelten die Referenzzähler der
    erzeugten FROM-Klausel. Aliase ohne Referenz (weggekürzte Joins) stehen
    nicht im SQL; ``as_sql`` setzt die Zähler am Ende wieder zurück.
    """
    locks = []
    original = SQLCompiler.get_from_clause

    def get_from_clause(compiler):
        query = compiler.query
        if query.select_for_update:
            joins = [join for alias, join in query.alias_map.items() if query.alias_refcount.get(alias)]
            outer = {join.table_name for join in joins if isinstance(join, Join) and join.join_type == LOUTER}
            locked = _locked_tables(query, joins)
            locks.append({"table": query.model._meta.db_table, "locked": locked, "outer": locked & outer})
        return original(compiler)

    with mock.patch.object(SQLCompiler, "get_from_clause", get_from_clause):
        yield locks


class PostgresLockAssertions:
    def assert_postgres_safe(self, locks):
        read_only = app_role_read_only_tables()
        self.assertIn("core_coffeeentry", read_only)
        for lock in locks:
            with self.subTest(lock=lock):
                self.assertEqual(lock["outer"], set(), "FOR UPDATE auf der nullbaren Seite eines Outer Joins")
                self.assertEqual(lock["locked"] & read_only, set(), "FOR UPDATE ohne UPDATE-Recht der App-Rolle")


class InventoryCheckoutWebTests(PostgresLockAssertions, TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Pool", slug="wache-pool")
        self.member = User.objects.create_user("pool", password="x" * 16)
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.item = InventoryItem.objects.create(station=self.station, item_id="hrt-2", label="Handfunkgerät HRT 2",
                                                 kind=InventoryItem.Kind.DEVICE)
        self.client.force_login(self.member)

    def post(self, action):
        with record_row_locks() as locks:
            response = self.client.post(reverse("assets_inventory_web"), {"action": action, "item_id": "hrt-2"})
        self.assertRedirects(response, reverse("assets_inventory_web"), fetch_redirect_response=False)
        self.assertIn({"table": "core_inventoryitem", "locked": {"core_inventoryitem"}, "outer": set()}, locks)
        self.assert_postgres_safe(locks)
        self.item.refresh_from_db()

    def test_checkout_and_checkin_lock_only_the_item(self):
        self.post("checkout")
        self.assertEqual(self.item.holder, self.member)
        self.post("checkin")
        self.assertIsNone(self.item.holder)
        self.assertEqual(
            list(InventoryEvent.objects.filter(item=self.item).order_by("pk").values_list("action", flat=True)),
            [InventoryEvent.Action.CHECKOUT, InventoryEvent.Action.CHECKIN],
        )

    def test_item_of_another_holder_stays_with_them(self):
        other = User.objects.create_user("andere", password="x" * 16)
        InventoryItem.objects.filter(pk=self.item.pk).update(holder=other, checked_out_at=timezone.now())
        self.post("checkout")
        self.assertEqual(self.item.holder, other)


class CoffeeCorrectionAppRoleTests(PostgresLockAssertions, TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Kasse", slug="wache-kasse", coffee_enabled=True)
        self.cashier = User.objects.create_user("kasse", password="x" * 16)
        self.member = User.objects.create_user("mara", password="x" * 16)
        Membership.objects.create(user=self.cashier, station=self.station, role=Membership.Role.CASHIER)
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.entry = CoffeeEntry.objects.create(station=self.station, member=self.member, amount_cents=700,
                                                reason="Einzahlung", kind=CoffeeEntry.Kind.PAYMENT,
                                                method=CoffeeEntry.Method.CASH, created_by=self.member)
        self.client.force_login(self.cashier)

    def correct(self):
        with record_row_locks() as locks:
            response = self.client.post(reverse("coffee_correct", args=[self.entry.pk]), {"reason": "Falscher Betrag"})
        self.assertRedirects(response, reverse("coffee"), fetch_redirect_response=False)
        self.assert_postgres_safe(locks)
        return response

    def test_correction_is_a_new_entry_without_locking_the_ledger(self):
        self.correct()
        correction = CoffeeEntry.objects.get(correction_of=self.entry)
        self.assertEqual((correction.amount_cents, correction.kind, correction.method, correction.member),
                         (-700, self.entry.kind, self.entry.method, self.member))
        self.assertEqual(CoffeeEntry.objects.filter(station=self.station).count(), 2)

    def test_second_correction_is_refused(self):
        self.correct()
        self.correct()
        self.assertEqual(CoffeeEntry.objects.filter(correction_of=self.entry).count(), 1)

    def test_constraint_catches_a_concurrent_second_correction(self):
        # Zwei Kassenwarte gleichzeitig: Beide sahen noch keine Korrektur.
        self.client.get(reverse("coffee_correct", args=[self.entry.pk]))
        CoffeeEntry.objects.create(station=self.station, member=self.member, amount_cents=-700, reason="Erste",
                                   kind=self.entry.kind, method=self.entry.method, created_by=self.cashier,
                                   correction_of=self.entry)
        original_exists = QuerySet.exists

        def exists(queryset):
            # Auch die Constraint-Prüfung in full_clean() übersieht die erste
            # Korrektur; übrig bleibt die Datenbank-Constraint (IntegrityError).
            if queryset.model is CoffeeEntry and "correction_of" in str(queryset.query):
                return False
            return original_exists(queryset)

        with mock.patch.object(QuerySet, "exists", exists):
            response = self.client.post(reverse("coffee_correct", args=[self.entry.pk]), {"reason": "Zweite"},
                                        follow=True)
        self.assertContains(response, "Diese Buchung wurde bereits korrigiert.")
        self.assertEqual(CoffeeEntry.objects.filter(correction_of=self.entry).count(), 1)


class WarehouseWithoutInventoryMirrorTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Lager", slug="wache-lager", warehouse_enabled=True)
        self.user = User.objects.create_user("lager", password="x" * 16)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def test_keys_and_radios_are_no_stock_rows(self):
        for item_id, label, kind in (("rtw-schluessel", "Fahrzeugschlüssel RTW 1", InventoryItem.Kind.KEY),
                                     ("hrt-1", "Handfunkgerät HRT 1", InventoryItem.Kind.DEVICE)):
            InventoryItem.objects.create(station=self.station, item_id=item_id, label=label, kind=kind)
        response = self.client.get(reverse("warehouse_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Fahrzeugschlüssel RTW 1")
        self.assertNotContains(response, "Handfunkgerät HRT 1")
        self.assertFalse(MedicalItem.objects.filter(station=self.station).exists())
        self.assertEqual(self.client.get(reverse("warehouse_reorder_proposal")).context["proposals"], [])
        self.assertEqual(display_payload(self.station)["warehouse_alerts"], [])


class InventoryMirrorMigrationTests(TestCase):
    """Migration 0066 entfernt nur unberührte Spiegelungen aus 0.25.0 und 0.26.0."""

    migration = importlib.import_module("core.migrations.0066_remove_inventory_mirrors")

    def setUp(self):
        self.station = Station.objects.create(name="Wache Alt", slug="wache-alt", warehouse_enabled=True)
        self.other = Station.objects.create(name="Wache Nachbar", slug="wache-nachbar", warehouse_enabled=True)
        self.user = User.objects.create_user("alt", password="x" * 16)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        inventory = (
            ("rtw-schluessel", "Schlüssel RTW 1", InventoryItem.Kind.KEY),
            ("hrt-1", "Handfunkgerät HRT 1", InventoryItem.Kind.DEVICE),
            ("notfallkoffer-atmung", "Notfallkoffer Atmung", InventoryItem.Kind.DEVICE),
            ("absauger", "Absaugpumpe", InventoryItem.Kind.DEVICE),
            ("pulsoxy", "Pulsoxymeter", InventoryItem.Kind.DEVICE),
        )
        for item_id, label, kind in inventory:
            InventoryItem.objects.create(station=self.station, item_id=item_id, label=label, kind=kind)
        # 0.25.0: create() mit den Modell-Standards (Mindestbestand 5, Soll 10).
        MedicalItem.objects.create(station=self.station, slug="rtw-schluessel", name="Schlüssel RTW 1")
        MedicalItem.objects.create(station=self.station, slug="hrt-1", name="Handfunkgerät HRT 1")
        # 0.26.0-Entwicklungsstand: Spiegelung mit 0/0.
        MedicalItem.objects.create(station=self.station, slug="notfallkoffer-atmung", name="Notfallkoffer Atmung",
                                   category=MedicalItem.Category.AIRWAY, min_stock=0, target_stock=0)
        # Von Hand gepflegt: eigener Mindestbestand bzw. echter Bestand.
        MedicalItem.objects.create(station=self.station, slug="absauger", name="Absaugpumpe", min_stock=1)
        pulsoxy = MedicalItem.objects.create(station=self.station, slug="pulsoxy", name="Pulsoxymeter")
        location = StorageLocation.objects.create(station=self.station, slug="lager", name="Lager")
        batch = ItemBatch.objects.create(item=pulsoxy, station=self.station, batch_number="P1",
                                         manufacturer_exp_date=dt.date(2030, 1, 31))
        StockItem.objects.create(station=self.station, item=pulsoxy, batch=batch, location=location, quantity=12)
        # Echter Artikel ohne Inventarstück und gleichnamiger Artikel einer anderen Wache.
        MedicalItem.objects.create(station=self.station, slug="nacl", name="NaCl 0,9 %")
        MedicalItem.objects.create(station=self.other, slug="rtw-schluessel", name="Schlüsselband")

    def alert_names(self, station):
        return {alert["name"] for alert in display_payload(station)["warehouse_alerts"]}

    def test_untouched_mirrors_are_removed(self):
        self.assertIn("Schlüssel RTW 1", self.alert_names(self.station))
        self.migration.remove_inventory_mirrors(global_apps, None)
        self.assertEqual(
            set(MedicalItem.objects.filter(station=self.station).values_list("slug", flat=True)),
            {"absauger", "pulsoxy", "nacl"},
        )
        self.assertTrue(MedicalItem.objects.filter(station=self.other, slug="rtw-schluessel").exists())
        self.assertEqual(self.alert_names(self.station), {"Absaugpumpe", "NaCl 0,9 %"})
        self.client.force_login(self.user)
        response = self.client.get(reverse("warehouse_dashboard"))
        self.assertNotContains(response, "Schlüssel RTW 1")
        self.assertNotContains(response, "Handfunkgerät HRT 1")
        self.assertContains(response, "Pulsoxymeter")

    def test_migration_is_idempotent(self):
        self.migration.remove_inventory_mirrors(global_apps, None)
        remaining = MedicalItem.objects.count()
        self.migration.remove_inventory_mirrors(global_apps, None)
        self.assertEqual(MedicalItem.objects.count(), remaining)
