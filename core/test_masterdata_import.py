"""CSV-Stammdatenimport (ROADMAP 0.27, Baustein 7): Lager und Medizingeräte."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import re
import threading
import time
from datetime import date, timedelta
from unittest import mock, skipUnless

from django.contrib.auth.models import User
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.http import urlencode

from core import masterdata_import as mi
from core.audit_labels import ACTION_LABELS
from core.models import AuditEvent, Membership, Station
from core.mpg_models import DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from core.test_terminal import TerminalTestCase
from core.wachalltag_models import StationAsset
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation

logger = logging.getLogger(__name__)


def pzn_with_check(body7: str) -> str:
    """Gültige PZN-8 zu sieben Ziffern (Prüfziffer modulo 11, Gewichte 1–7)."""
    remainder = sum(int(digit) * weight for digit, weight in zip(body7, range(1, 8), strict=True)) % 11
    return body7 + str(remainder) if remainder != 10 else ""


def valid_pzns(count: int, start: int = 1_000_000) -> list[str]:
    result, number = [], start
    while len(result) < count:
        pzn = pzn_with_check(f"{number:07d}")
        if pzn:
            result.append(pzn)
        number += 1
    return result


def gtin_with_check(body: str) -> str:
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def csv_text(rows, delimiter=";") -> str:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    return buffer.getvalue()


def csv_bytes(rows, delimiter=";", encoding="utf-8-sig") -> bytes:
    return csv_text(rows, delimiter).encode(encoding)


def read(rows, slug="artikel", delimiter=";"):
    return mi.read_table(csv_text(rows, delimiter), mi.KINDS[slug])


VALID_PZN = valid_pzns(3)


class CsvReadingTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        # Meldungen werden auf Deutsch geprüft, unabhängig von der Sprache vorheriger Tests.
        self.enterContext(translation.override("de"))

    def test_decodes_utf8_with_and_without_bom(self):
        self.assertEqual(mi.decode_upload("Artikel;Kühl\r\n".encode("utf-8-sig")), ("Artikel;Kühl\r\n", "utf-8-sig"))
        self.assertEqual(mi.decode_upload("Artikel;Kühl\r\n".encode("utf-8")), ("Artikel;Kühl\r\n", "utf-8"))

    def test_decodes_windows_1252_umlauts(self):
        raw = "Lagerort\r\nKühlschrank\r\n".encode("cp1252")
        self.assertIn(b"\xfc", raw)
        text, encoding = mi.decode_upload(raw)
        self.assertEqual(encoding, "cp1252")
        table = mi.read_table(text, mi.KINDS["lagerorte"])
        self.assertEqual(table.rows[0].values["name"], "Kühlschrank")

    def test_rejects_utf16_binary_xlsx_and_empty_files(self):
        for raw, fragment in (
            ("Artikel\r\nA\r\n".encode("utf-16"), "UTF-16"),
            (b"Artikel\x00;x\r\n", "keine Textdatei"),
            (b"PK\x03\x04rest", "Excel-Datei"),
            (b"", "leer"),
            (b"   \r\n", "leer"),
            (b"\x81\x8d\x8f\x90\x9d", "Zeichenkodierung"),
        ):
            report = mi.run_import(mi.KINDS["artikel"], station=None, actor=None, raw=raw, commit=False)
            self.assertEqual(report.rows, [], fragment)
            self.assertTrue(report.file_errors, fragment)
            self.assertIn(fragment, report.file_errors[0])

    def test_detects_semicolon_comma_and_excel_sep_line(self):
        self.assertEqual(read([["Artikel", "PZN"], ["Pflaster, rund", ""]]).delimiter, ";")
        comma = mi.read_table("Artikel,PZN,Einheit\r\nPflaster,,Stück\r\n", mi.KINDS["artikel"])
        self.assertEqual(comma.delimiter, ",")
        self.assertEqual(comma.rows[0].values["unit"], "Stück")
        sep = mi.read_table("sep=,\r\nArtikel,PZN\r\nA;B,\r\n", mi.KINDS["artikel"])
        self.assertEqual(sep.delimiter, ",")
        self.assertEqual(sep.rows[0].values["name"], "A;B")
        self.assertEqual(sep.rows[0].line, 3)

    def test_reports_physical_start_line_for_multiline_quoted_cells(self):
        text = 'Lagerort;Beschreibung\r\n"RTW 1";"Fach; links\r\nzweite Zeile"\r\n\r\nKoffer;x\r\n'
        table = mi.read_table(text, mi.KINDS["lagerorte"])
        self.assertEqual([row.line for row in table.rows], [2, 5])
        self.assertEqual(table.rows[0].values["description"], "Fach; links\r\nzweite Zeile")

    def test_skips_blank_and_hash_rows(self):
        table = read([["# Kommentar"], ["Artikel"], ["# Beispiel: X"], [""], ["", ""], ["Mullbinde"]])
        self.assertEqual([(row.line, row.values["name"]) for row in table.rows], [(6, "Mullbinde")])

    def test_unknown_columns_are_listed_as_ignored(self):
        table = read([["Artikel", "Farbe", "Ist-Bestand"], ["Mullbinde", "weiß", "3"]])
        reasons = dict((header, str(reason)) for header, reason in table.ignored)
        self.assertIn("unbekannte Spalte", reasons["Farbe"])
        self.assertIn("Bestand (Altbestand)", reasons["Ist-Bestand"])
        self.assertNotIn("Farbe", table.rows[0].values)

    def test_missing_required_or_duplicate_header_is_file_error(self):
        with self.assertRaisesMessage(mi.ImportFileError, "Pflichtspalte fehlt: Artikel"):
            read([["PZN"], [VALID_PZN[0]]])
        with self.assertRaisesMessage(mi.ImportFileError, "doppelt"):
            read([["Artikel", "Artikelbezeichnung"], ["A", "B"]])
        with self.assertRaisesMessage(mi.ImportFileError, "Mindestens eine"):
            read([["Charge (Lot)", "Hersteller-MHD", "Lagerort", "Bestand"], ["L1", "2030-01-01", "A", "1"]],
                 slug="bestand")

    def test_header_matching_ignores_case_star_spacing_and_umlaut_spelling(self):
        table = mi.read_table("ARTIKEL* ;  kuehlpflichtig \r\nA;ja\r\n", mi.KINDS["artikel"])
        self.assertEqual(table.rows[0].values, {"name": "A", "cooling": "ja"})

    def test_row_column_and_cell_limits(self):
        rows = [["Artikel"]] + [[f"A{n}"] for n in range(2001)]
        with self.assertRaisesMessage(mi.ImportFileError, "mehr als 2000 Datenzeilen"):
            read(rows)
        with self.assertRaisesMessage(mi.ImportFileError, "mehr als 50 Spalten"):
            read([["Artikel"] + [f"X{n}" for n in range(50)], ["A"]])
        table = read([["Artikel"], ["x" * 1001]])
        self.assertIn("länger als 1000 Zeichen", table.rows[0].errors[0])
        table = read([["Artikel", ""], ["A", "Wert"]])
        self.assertIn("ohne Spaltenüberschrift", table.rows[0].errors[0])

    def test_rejects_formula_prefixed_cells(self):
        for value in ("=HYPERLINK(1)", "+1", "-1+2", "@SUM(A1)", "\tx", " =1"):
            table = read([["Artikel"], [value]])
            self.assertEqual(len(table.rows[0].errors), 1, repr(value))
            self.assertIn("darf nicht mit", table.rows[0].errors[0])

    def test_lone_dash_counts_as_empty(self):
        table = read([["Artikel", "PZN", "GTIN", "Einheit"], ["A", "-", "–", "—"]])
        self.assertEqual(table.rows[0].errors, [])
        self.assertEqual(table.rows[0].values, {"name": "A", "pzn": "", "gtin": "", "unit": ""})

    def test_pzn_zero_padding_and_checksum(self):
        for pzn in valid_pzns(20):
            self.assertEqual(mi.parse_pzn(pzn), pzn)
        padded = next(p for p in valid_pzns(200, start=100_000) if p.startswith("0"))
        self.assertEqual(mi.parse_pzn(padded.lstrip("0")), padded)
        self.assertEqual(mi.parse_pzn("PZN-" + padded), padded)
        wrong = padded[:7] + str((int(padded[7]) + 1) % 10)
        with self.assertRaisesMessage(mi.CellError, "Prüfziffer"):
            mi.parse_pzn(wrong)
        with self.assertRaisesMessage(mi.CellError, "höchstens 8"):
            mi.parse_pzn("123456789")

    def test_gtin_checksum_and_scientific_notation_hint(self):
        gtin = gtin_with_check("400638133393")
        self.assertEqual(mi.parse_gtin(gtin), gtin)
        self.assertEqual(mi.parse_gtin(gtin_with_check("0400638133393")), gtin_with_check("0400638133393"))
        with self.assertRaisesMessage(mi.CellError, "Prüfziffer"):
            mi.parse_gtin(gtin[:-1] + str((int(gtin[-1]) + 1) % 10))
        with self.assertRaisesMessage(mi.CellError, "als Text formatieren"):
            mi.parse_gtin("4,00638E+12")
        with self.assertRaisesMessage(mi.CellError, "als Text formatieren"):
            mi.parse_pzn("1,23E+06")
        with self.assertRaisesMessage(mi.CellError, "8, 12, 13 oder 14"):
            mi.parse_gtin("12345")

    def test_non_ascii_digits_are_cell_errors_not_aborts(self):
        # str.isdigit() hält „²“ für eine Ziffer; int() bräche dann den ganzen Import ab.
        with self.assertRaisesMessage(mi.CellError, "keine PZN"):
            mi.parse_pzn("1234²")
        with self.assertRaisesMessage(mi.CellError, "8, 12, 13 oder 14"):
            mi.parse_gtin("400638133393²")
        with self.assertRaisesMessage(mi.CellError, "keine PZN"):
            mi.parse_pzn("١٢٣٤٥٦٧٨")

    def test_date_formats_and_month_only_dates(self):
        self.assertEqual(mi.parse_date("2027-05-31"), date(2027, 5, 31))
        self.assertEqual(mi.parse_date("1.6.2027"), date(2027, 6, 1))
        self.assertEqual(mi.parse_date("31.12.27"), date(2027, 12, 31))
        self.assertEqual(mi.parse_date("31.12.2027 00:00"), date(2027, 12, 31))
        self.assertEqual(mi.parse_date("05/2027", month_ok=True), date(2027, 5, 31))
        self.assertEqual(mi.parse_date("02.2028", month_ok=True), date(2028, 2, 29))
        self.assertEqual(mi.parse_date("2027-11", month_ok=True), date(2027, 11, 30))
        for bad in ("2027-02-30", "05/2027", "morgen", "31.12.1899"):
            with self.assertRaises(mi.CellError, msg=bad):
                mi.parse_date(bad)
        # Prüfplaketten (STK/MTK/DGUV) zeigen Monat und Jahr.
        table = read([["Gerätebezeichnung", "Risikoklasse", "Seriennummer", "Nächste STK", "Nächste MTK",
                       "Nächste DGUV V3"], ["Absaugpumpe", "IIa", "1", "06/2030", "07.2030", "2030-08"]],
                     slug="medizingeraete")
        result = mi.RowResult(line=2)
        cells = mi.Cells(mi.KINDS["medizingeraete"], table.rows[0], result)
        self.assertEqual(cells.day("next_stk", month_ok=True), date(2030, 6, 30))
        self.assertEqual(cells.day("next_mtk", month_ok=True), date(2030, 7, 31))
        self.assertEqual(cells.day("next_dguv", month_ok=True), date(2030, 8, 31))
        self.assertEqual(result.errors, [])

    def test_every_template_header_is_recognised(self):
        for slug, kind in mi.KINDS.items():
            raw = mi.template_csv(kind).encode("utf-8")
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), slug)
            text, _encoding = mi.decode_upload(raw)
            self.assertTrue(text.splitlines()[1].startswith("# Beispiel"), slug)
            with self.assertRaisesMessage(mi.ImportFileError, "keine Datenzeilen"):
                mi.read_table(text, kind)
            header = next(csv.reader(io.StringIO(text), delimiter=";"))
            lookup = kind.header_lookup()
            self.assertEqual([h for h in header if mi.normalize_header(h) not in lookup], [], slug)
            self.assertEqual(len(header), len(kind.columns), slug)

    def test_every_audit_action_has_label(self):
        for kind in mi.KINDS.values():
            self.assertIn(kind.audit_action, ACTION_LABELS, kind.slug)

    def test_double_encoded_umlauts_give_a_hint(self):
        self.assertTrue(mi.text_hints("Artikel\r\nKÃ¼hlschrank\r\n"))
        self.assertEqual(mi.text_hints("Artikel\r\nKühlschrank\r\n"), [])


class ImportTestCase(TestCase):
    def setUp(self):
        self.enterContext(translation.override("de"))
        self.station = Station.objects.create(name="RW Import", slug="rw-import", warehouse_enabled=True,
                                              mpg_enabled=True)
        self.admin = User.objects.create_user(username="chefin", password="x-test-pass-123")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.other = Station.objects.create(name="RW Andere", slug="rw-andere", warehouse_enabled=True,
                                            mpg_enabled=True)
        self.other_admin = User.objects.create_user(username="andere", password="x-test-pass-123")
        Membership.objects.create(user=self.other_admin, station=self.other, role=Membership.Role.ADMIN)

    def run_kind(self, slug, rows, *, commit=True, station=None, actor=None, raw=None):
        return mi.run_import(
            mi.KINDS[slug], station=station or self.station, actor=actor or self.admin,
            raw=raw if raw is not None else csv_bytes(rows), commit=commit,
        )

    def assertImported(self, report, created=None):
        self.assertEqual(report.file_errors, [])
        self.assertEqual([(row.line, row.errors) for row in report.rows if row.errors], [])
        self.assertTrue(report.committed)
        if created is not None:
            self.assertEqual(report.counts["created"], created)

    def location(self, name, parent=None, station=None, **extra):
        station = station or self.station
        return StorageLocation.objects.create(station=station, slug=f"loc-{StorageLocation.objects.count()}",
                                              name=name, parent=parent, **extra)

    def item(self, name, station=None, **extra):
        station = station or self.station
        return MedicalItem.objects.create(station=station, slug=f"item-{MedicalItem.objects.count()}", name=name,
                                          **extra)


class StorageLocationImportTests(ImportTestCase):
    HEADER = ["Lagerort", "Art", "Kühlung", "Übergeordneter Lagerort", "Beschreibung"]

    def test_creates_locations_with_parent_defined_later_in_file(self):
        report = self.run_kind("lagerorte", [
            self.HEADER,
            ["Fach 3", "", "", "Schrank links", ""],
            ["Schrank links", "", "", "RTW 1", ""],
            ["RTW 1", "Fahrzeug", "", "", "Fahrzeug 1"],
        ])
        self.assertImported(report, created=3)
        fach = StorageLocation.objects.get(station=self.station, name="Fach 3")
        self.assertEqual(fach.parent.name, "Schrank links")
        self.assertEqual(fach.parent.parent.name, "RTW 1")
        self.assertEqual(fach.kind, StorageLocation.Kind.OTHER)
        self.assertEqual(StorageLocation.objects.get(name="RTW 1").kind, StorageLocation.Kind.VEHICLE)

    def test_parent_cycle_and_self_reference_are_errors(self):
        report = self.run_kind("lagerorte", [self.HEADER, ["A", "", "", "B", ""], ["B", "", "", "A", ""],
                                             ["C", "", "", "C", ""]])
        self.assertFalse(report.committed)
        messages = [" ".join(row.errors) for row in report.rows]
        self.assertIn("Kreis", messages[0])
        self.assertIn("Kreis", messages[1])
        self.assertIn("sich selbst", messages[2])
        self.assertFalse(StorageLocation.objects.exists())

    def test_ambiguous_parent_name_is_error(self):
        rtw1 = self.location("RTW 1")
        rtw2 = self.location("RTW 2")
        self.location("Schrank links", parent=rtw1)
        self.location("Schrank links", parent=rtw2)
        report = self.run_kind("lagerorte", [self.HEADER, ["Fach 3", "", "", "Schrank links", ""]])
        self.assertIn("mehrdeutig", report.rows[0].errors[0])
        # Das Beispiel ist ein Pfad, der weiterhilft, nicht die Eingabe selbst.
        self.assertIn("z. B. „RTW 1 → Schrank links“", report.rows[0].errors[0])
        report = self.run_kind("lagerorte", [self.HEADER, ["Fach 3", "", "", "RTW 2 → Schrank links", ""],
                                             ["Fach 3", "", "", "RTW 1 > Schrank links", ""]])
        self.assertImported(report, created=2)
        self.assertEqual(
            sorted(loc.parent.parent.name for loc in StorageLocation.objects.filter(name="Fach 3")), ["RTW 1", "RTW 2"],
        )

    def test_top_level_parent_wins_over_same_name_further_down(self):
        top = self.location("Kühlschrank")
        nested = self.location("Kühlschrank", parent=self.location("RTW 1"))
        report = self.run_kind("lagerorte", [self.HEADER, ["Fach oben", "", "", "Kühlschrank", ""],
                                             ["Fach RTW", "", "", "RTW 1 → Kühlschrank", ""]])
        self.assertImported(report, created=2)
        self.assertEqual(StorageLocation.objects.get(name="Fach oben").parent, top)
        self.assertEqual(StorageLocation.objects.get(name="Fach RTW").parent, nested)
        self.assertIn("genau diesem Pfad", report.rows[0].notes[0])
        self.assertIn("„RTW 1 → Kühlschrank“", report.rows[0].notes[0])
        self.assertEqual(report.rows[1].notes, [])

    def test_top_level_parent_wins_within_the_file(self):
        report = self.run_kind("lagerorte", [
            self.HEADER,
            ["Fach oben", "", "", "kühlschrank", ""], ["Fach RTW", "", "", "RTW 1 > Kühlschrank", ""],
            ["Kühlschrank", "Kühlschrank", "", "RTW 1", ""], ["RTW 1", "Fahrzeug", "", "", ""],
            ["Kühlschrank", "Kühlschrank", "", "", ""],
        ])
        self.assertImported(report, created=5)
        top = StorageLocation.objects.get(name="Kühlschrank", parent=None)
        nested = StorageLocation.objects.get(name="Kühlschrank", parent__name="RTW 1")
        self.assertEqual(StorageLocation.objects.get(name="Fach oben").parent, top)
        self.assertEqual(StorageLocation.objects.get(name="Fach RTW").parent, nested)
        self.assertIn("„RTW 1 → Kühlschrank“", report.rows[0].notes[0])

    def test_same_child_name_under_different_parents(self):
        report = self.run_kind("lagerorte", [
            self.HEADER,
            ["RTW 1", "Fahrzeug", "", "", ""], ["RTW 2", "Fahrzeug", "", "", ""],
            ["Schrank links", "", "", "RTW 1", ""], ["Schrank links", "", "", "RTW 2", ""],
            ["Fach 3", "", "", "RTW 1 → Schrank links", ""], ["Fach 3", "", "", "RTW 2 → Schrank links", ""],
        ])
        self.assertImported(report, created=6)
        again = self.run_kind("lagerorte", [self.HEADER, ["Fach 3", "", "", "RTW 1 → Schrank links", ""]])
        self.assertEqual(again.rows[0].status, "skipped")
        self.assertEqual(StorageLocation.objects.filter(name="Fach 3").count(), 2)

    def test_fridge_kind_sets_cold_storage(self):
        report = self.run_kind("lagerorte", [self.HEADER, ["Medikamentenkühlschrank", "Kühlschrank", "", "", ""],
                                             ["Hauptlager", "Hauptlager / Apotheke", "", "", ""]])
        self.assertImported(report, created=2)
        self.assertTrue(StorageLocation.objects.get(name="Medikamentenkühlschrank").is_cold_storage)
        self.assertFalse(StorageLocation.objects.get(name="Hauptlager").is_cold_storage)
        self.assertEqual(StorageLocation.objects.get(name="Hauptlager").kind, StorageLocation.Kind.CENTRAL)

    def test_existing_location_is_skipped_and_unchanged(self):
        existing = self.location("Hauptlager", kind=StorageLocation.Kind.CENTRAL, description="alt")
        report = self.run_kind("lagerorte", [self.HEADER, ["hauptlager", "Kühlschrank", "Ja", "", "neu"]])
        self.assertImported(report, created=0)
        self.assertEqual(report.rows[0].status, "skipped")
        existing.refresh_from_db()
        self.assertEqual((existing.description, existing.kind, existing.is_cold_storage), ("alt", "central", False))

    def test_duplicate_row_in_file_is_error(self):
        report = self.run_kind("lagerorte", [self.HEADER, ["Koffer", "", "", "", ""], ["koffer", "", "", "", ""]])
        self.assertIn("Zeile 2", report.rows[1].errors[0])
        self.assertFalse(report.committed)

    def test_parent_from_other_station_is_not_found(self):
        self.location("Fremdes Lager", station=self.other)
        report = self.run_kind("lagerorte", [self.HEADER, ["Fach", "", "", "Fremdes Lager", ""]])
        self.assertIn("weder auf dieser Wache", report.rows[0].errors[0])
        self.assertFalse(StorageLocation.objects.filter(station=self.station).exists())


class ArticleImportTests(ImportTestCase):
    def test_creates_articles_with_zero_min_and_target_stock_by_default(self):
        report = self.run_kind("artikel", [["Artikel", "PZN", "Einheit", "Kategorie"],
                                           ["Mullbinde 8 cm", VALID_PZN[0], "Stk", "Verband"]])
        self.assertImported(report, created=1)
        item = MedicalItem.objects.get(station=self.station)
        self.assertEqual((item.min_stock, item.target_stock), (0, 0))
        self.assertEqual((item.unit, item.category, item.pzn), ("pcs", "bandage", VALID_PZN[0]))
        self.assertEqual(item.notes, "")

    def test_target_defaults_to_min_and_room_days_only_for_cooling(self):
        report = self.run_kind("artikel", [
            ["Artikel", "Mindestbestand", "Sollbestand", "Kühlpflichtig", "Max. Tage bei Raumtemperatur"],
            ["A", "1.000", "", "nein", "84"], ["B", "5", "2", "ja", "84"],
        ])
        self.assertImported(report, created=2)
        a = MedicalItem.objects.get(name="A")
        self.assertEqual((a.min_stock, a.target_stock, a.room_temp_max_days), (1000, 1000, None))
        self.assertIn("kühlpflichtig", report.rows[0].notes[0])
        self.assertIn("unter dem Mindestbestand", report.rows[1].notes[0])
        self.assertEqual(MedicalItem.objects.get(name="B").room_temp_max_days, 84)

    def test_existing_pzn_is_skipped_and_not_updated(self):
        self.item("Altname", pzn=VALID_PZN[0], min_stock=7)
        report = self.run_kind("artikel", [["Artikel", "PZN", "Mindestbestand"], ["Neuer Name", VALID_PZN[0], "1"]])
        self.assertImported(report, created=0)
        item = MedicalItem.objects.get(station=self.station)
        self.assertEqual((item.name, item.min_stock), ("Altname", 7))

    def test_existing_unpadded_pzn_and_short_gtin_match(self):
        padded = next(p for p in valid_pzns(200, start=100_000) if p.startswith("0"))
        gtin14 = gtin_with_check("0400638133393")
        self.item("Alt PZN", pzn=padded.lstrip("0"))
        self.item("Alt GTIN", gtin=gtin14)
        report = self.run_kind("artikel", [["Artikel", "PZN", "GTIN"], ["X", padded, ""], ["Y", "", gtin14[1:]]])
        self.assertImported(report, created=0)
        self.assertEqual([row.status for row in report.rows], ["skipped", "skipped"])

    def test_existing_name_without_codes_is_skipped_with_hint(self):
        self.item("Mullbinde")
        report = self.run_kind("artikel", [["Artikel", "PZN"], ["mullbinde", VALID_PZN[1]], ["Neu", ""]])
        self.assertImported(report, created=1)
        self.assertEqual(report.rows[0].status, "skipped")
        self.assertIn("PZN bzw. GTIN bitte dort ergänzen", report.rows[0].notes[0])

    def test_identical_duplicates_merge_conflicting_duplicates_error(self):
        report = self.run_kind("artikel", [["Artikel", "PZN", "Mindestbestand"], ["A", VALID_PZN[0], "1"],
                                           ["A", VALID_PZN[0], "1"]])
        self.assertImported(report, created=1)
        self.assertIn("Gleich wie Zeile 2", report.rows[1].notes[0])
        report = self.run_kind("artikel", [["Artikel", "PZN", "Mindestbestand"], ["B", VALID_PZN[1], "1"],
                                           ["B", VALID_PZN[1], "2"]])
        self.assertFalse(report.committed)
        self.assertIn("Widerspricht Zeile 2", report.rows[1].errors[0])
        self.assertFalse(MedicalItem.objects.filter(name="B").exists())

    def test_superscript_pzn_is_a_row_error_and_keeps_the_preview(self):
        report = self.run_kind("artikel", [["Artikel", "PZN", "GTIN"], ["A", "1234²", ""],
                                           ["B", "", "400638133393²"], ["C", VALID_PZN[0], ""]], commit=False)
        self.assertEqual(report.file_errors, [])
        self.assertEqual([row.status for row in report.rows], ["error", "error", "new"])
        self.assertIn("keine PZN", report.rows[0].errors[0])
        self.assertIn("GTIN", report.rows[1].errors[0])

    def test_unknown_category_lists_allowed_values(self):
        report = self.run_kind("artikel", [["Artikel", "Kategorie"], ["A", "Spielzeug"]])
        self.assertIn("Erlaubt: Notfallmedikamente & Ampullen", report.rows[0].errors[0])
        self.assertFalse(report.committed)

    def test_english_ui_accepts_german_labels(self):
        with translation.override("en"):
            report = self.run_kind("artikel", [["Artikel", "Kategorie", "Einheit", "Kühlpflichtig"],
                                               ["A", "Hygiene & Desinfektion", "Packung(en)", "Ja"]])
            self.assertImported(report, created=1)
            report = self.run_kind("artikel", [["Artikel", "Kategorie"], ["B", "Spielzeug"]])
            self.assertIn("Notfallmedikamente & Ampullen", report.rows[0].errors[0])
        item = MedicalItem.objects.get(name="A")
        self.assertEqual((item.category, item.unit, item.requires_cooling), ("hygiene", "pack", True))

    def test_reorder_export_headers_are_accepted(self):
        report = self.run_kind("artikel", [
            ["PZN", "Artikelbezeichnung", "Kategorie", "Bestellmenge", "Einheit", "Ist-Bestand", "Mindestbestand",
             "Sollbestand"],
            [VALID_PZN[0], "Mullbinde", "Verbandstoffe & Wundversorgung", "3", "Stück", "2", "5", "5"],
        ])
        self.assertImported(report, created=1)
        self.assertEqual(sorted(h for h, _r in report.ignored_headers), ["Bestellmenge", "Ist-Bestand"])
        self.assertEqual(MedicalItem.objects.get(station=self.station).min_stock, 5)

    def test_same_pzn_at_other_station_does_not_match(self):
        other_item = self.item("Fremd", station=self.other, pzn=VALID_PZN[0], min_stock=9)
        report = self.run_kind("artikel", [["Artikel", "PZN"], ["Eigen", VALID_PZN[0]]])
        self.assertImported(report, created=1)
        self.assertTrue(MedicalItem.objects.filter(station=self.station, name="Eigen").exists())
        other_item.refresh_from_db()
        self.assertEqual((other_item.name, other_item.min_stock), ("Fremd", 9))

    def test_slugs_unique_against_existing(self):
        MedicalItem.objects.create(station=self.station, slug="mullbinde", name="Mullbinde alt", pzn=VALID_PZN[2])
        report = self.run_kind("artikel", [["Artikel", "PZN"], ["Mullbinde", VALID_PZN[0]], ["Mullbinde", VALID_PZN[1]],
                                           ["???", ""]])
        self.assertImported(report, created=3)
        slugs = set(MedicalItem.objects.filter(station=self.station).values_list("slug", flat=True))
        self.assertEqual(slugs, {"mullbinde", "mullbinde-1", "mullbinde-2", "item"})


class StockImportTests(ImportTestCase):
    HEADER = ["Artikel", "PZN", "Charge (Lot)", "Hersteller-MHD", "Out-of-Fridge Datum", "Lagerort", "Bestand",
              "Einheit", "Status / Rückruf"]

    def setUp(self):
        super().setUp()
        self.lager = self.location("Hauptlager", kind=StorageLocation.Kind.CENTRAL)
        self.kuehl = self.location("Kühlschrank", kind=StorageLocation.Kind.FRIDGE, is_cold_storage=True)
        self.binde = self.item("Mullbinde", pzn=VALID_PZN[0], unit=MedicalItem.Unit.PIECE)
        self.roc = self.item("Rocuronium", pzn=VALID_PZN[1], unit=MedicalItem.Unit.AMPOULE, requires_cooling=True,
                             room_temp_max_days=84)
        self.mhd = timezone.localdate() + timedelta(days=400)

    def test_legacy_stock_creates_batch_stock_item_and_legacy_movement(self):
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Hauptlager",
                                                         "12", "Stück", ""]])
        self.assertImported(report, created=1)
        batch = ItemBatch.objects.get(item=self.binde)
        self.assertEqual((batch.batch_number, batch.manufacturer_exp_date, batch.station), ("L1", self.mhd, self.station))
        self.assertEqual(StockItem.objects.get(batch=batch, location=self.lager).quantity, 12)
        movement = StockMovement.objects.get(batch=batch)
        self.assertEqual(movement.kind, "legacy")
        self.assertEqual(movement.get_kind_display(), "Übernahme Altbestand")
        self.assertEqual((movement.actor, movement.target_location, movement.source_location), (self.admin, self.lager, None))
        self.assertEqual(movement.note, f"CSV-Import {report.digest[:12]}")
        self.assertEqual(movement.quantity, 12)

    def test_reimport_is_idempotent_no_second_movement(self):
        rows = [self.HEADER, ["", VALID_PZN[0], "L1", self.mhd.isoformat(), "", "Hauptlager", "12", "", ""]]
        self.assertImported(self.run_kind("bestand", rows), created=1)
        again = self.run_kind("bestand", rows)
        self.assertImported(again, created=0)
        self.assertEqual(again.rows[0].status, "skipped")
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockItem.objects.get().quantity, 12)

    def test_same_batch_at_second_location_reuses_batch(self):
        report = self.run_kind("bestand", [
            self.HEADER,
            ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Hauptlager", "5", "", ""],
            ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Kühlschrank", "2", "", ""],
        ])
        self.assertImported(report, created=2)
        self.assertEqual(ItemBatch.objects.count(), 1)
        self.assertEqual(StockMovement.objects.filter(kind="legacy").count(), 2)

    def test_recalled_status_row_is_rejected(self):
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Hauptlager",
                                                         "1", "", "Gesperrt: Rückruf"]])
        self.assertFalse(report.committed)
        self.assertIn("Gesperrte Chargen", report.rows[0].errors[0])
        batch = ItemBatch.objects.create(item=self.binde, station=self.station, batch_number="L9",
                                         manufacturer_exp_date=self.mhd, is_recalled=True)
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L9", self.mhd.isoformat(), "", "Hauptlager",
                                                         "1", "", ""]])
        self.assertIn("gesperrt", report.rows[0].errors[0])
        self.assertFalse(StockItem.objects.filter(batch=batch).exists())

    def test_existing_batch_with_other_expiry_is_error(self):
        ItemBatch.objects.create(item=self.binde, station=self.station, batch_number="L1",
                                 manufacturer_exp_date=self.mhd + timedelta(days=30))
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Hauptlager",
                                                         "1", "", ""]])
        self.assertIn("anderen MHD", report.rows[0].errors[0])
        self.assertFalse(report.committed)

    def test_zero_quantity_is_skipped_and_in_file_duplicates_are_errors(self):
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Hauptlager",
                                                         "0", "", ""]])
        self.assertEqual(report.rows[0].status, "skipped")
        self.assertIn("Bestand 0", report.rows[0].notes[0])
        report = self.run_kind("bestand", [
            self.HEADER,
            ["Mullbinde", "", "L2", self.mhd.isoformat(), "", "Hauptlager", "1", "", ""],
            ["Mullbinde", "", "L2", self.mhd.isoformat(), "", "Hauptlager", "2", "", ""],
            ["Mullbinde", "", "L2", (self.mhd + timedelta(days=1)).isoformat(), "", "Kühlschrank", "2", "", ""],
        ])
        self.assertIn("Zeile 2", report.rows[1].errors[0])
        self.assertIn("anderes MHD", report.rows[2].errors[0])
        self.assertFalse(StockItem.objects.exists())

    def test_location_path_notation_resolves_duplicate_names(self):
        rtw1, rtw2 = self.location("RTW 1"), self.location("RTW 2")
        fach1 = self.location("Fach 3", parent=rtw1)
        self.location("Fach 3", parent=rtw2)
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Fach 3",
                                                         "1", "", ""]])
        self.assertIn("mehrdeutig", report.rows[0].errors[0])
        self.assertIn("→ Fach 3", report.rows[0].errors[0])
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "",
                                                         "RTW 1 → Fach 3", "1", "", ""]])
        self.assertImported(report, created=1)
        self.assertEqual(StockItem.objects.get().location, fach1)

    def test_top_level_location_wins_over_same_name_further_down(self):
        nested = self.location("Kühlschrank", kind=StorageLocation.Kind.FRIDGE, is_cold_storage=True,
                               parent=self.location("RTW 1", kind=StorageLocation.Kind.VEHICLE))
        report = self.run_kind("bestand", [
            self.HEADER,
            ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Kühlschrank", "1", "", ""],
            ["Mullbinde", "", "L2", self.mhd.isoformat(), "", "RTW 1 → Kühlschrank", "2", "", ""],
        ])
        self.assertImported(report, created=2)
        self.assertEqual(StockItem.objects.get(batch__batch_number="L1").location, self.kuehl)
        self.assertEqual(StockItem.objects.get(batch__batch_number="L2").location, nested)
        self.assertIn("genau diesem Pfad", " ".join(report.rows[0].notes))
        self.assertIn("„RTW 1 → Kühlschrank“", " ".join(report.rows[0].notes))
        self.assertNotIn("genau diesem Pfad", " ".join(report.rows[1].notes))
        self.assertEqual(report.rows[0].label, "Mullbinde · L1 · Kühlschrank")

    def test_same_path_twice_is_ambiguous_without_misleading_example(self):
        self.location("Hauptlager")
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "",
                                                         "Hauptlager", "1", "", ""]])
        self.assertFalse(report.committed)
        self.assertIn("mehrdeutig", report.rows[0].errors[0])
        self.assertIn("mehrmals", report.rows[0].errors[0])
        self.assertNotIn("z. B.", report.rows[0].errors[0])
        self.assertFalse(StockItem.objects.exists())

    def test_cooling_item_out_of_fridge_shortens_effective_date(self):
        oof = timezone.localdate() - timedelta(days=4)
        report = self.run_kind("bestand", [
            self.HEADER,
            ["Rocuronium", "", "R1", self.mhd.isoformat(), oof.strftime("%d.%m.%Y"), "Hauptlager", "5", "Ampulle", ""],
            ["Rocuronium", "", "R2", self.mhd.isoformat(), "", "Hauptlager", "5", "Stück", ""],
        ])
        self.assertImported(report, created=2)
        batch = ItemBatch.objects.get(batch_number="R1")
        self.assertEqual(batch.out_of_fridge_date, oof)
        self.assertEqual(batch.calculated_exp_date, oof + timedelta(days=84))
        self.assertIn("ohne Out-of-Fridge-Datum", " ".join(report.rows[1].notes))
        self.assertIn("weicht vom Artikel ab", " ".join(report.rows[1].notes))

    def test_month_only_mhd_means_end_of_month(self):
        report = self.run_kind("bestand", [self.HEADER, ["Mullbinde", "", "L1", "05/2030", "", "Hauptlager", "1", "", ""]])
        self.assertImported(report, created=1)
        self.assertEqual(ItemBatch.objects.get().manufacturer_exp_date, date(2030, 5, 31))

    def test_fefo_export_round_trip_between_stations(self):
        self.client.force_login(self.admin)
        for location, lot, quantity in ((self.lager, "L1", 4), (self.kuehl, "L1", 2), (self.lager, "L2", 7)):
            batch, _created = ItemBatch.objects.get_or_create(
                item=self.binde, station=self.station, batch_number=lot, defaults={"manufacturer_exp_date": self.mhd},
            )
            StockItem.objects.create(station=self.station, item=self.binde, batch=batch, location=location,
                                     quantity=quantity)
        export = self.client.get(reverse("warehouse_export_fefo")).content
        self.location("Hauptlager", station=self.other)
        self.location("Kühlschrank", station=self.other)
        articles = self.run_kind("artikel", [], raw=export, station=self.other, actor=self.other_admin)
        self.assertImported(articles, created=1)
        self.assertTrue(articles.ignored_headers)
        stock = self.run_kind("bestand", [], raw=export, station=self.other, actor=self.other_admin)
        self.assertImported(stock, created=3)
        mine = sorted(StockItem.objects.filter(station=self.station).values_list(
            "batch__batch_number", "batch__manufacturer_exp_date", "location__name", "quantity"))
        theirs = sorted(StockItem.objects.filter(station=self.other).values_list(
            "batch__batch_number", "batch__manufacturer_exp_date", "location__name", "quantity"))
        self.assertEqual(mine, theirs)
        self.assertEqual(StockMovement.objects.filter(station=self.other, kind="legacy").count(), 3)

    def test_article_or_location_of_other_station_is_not_found(self):
        self.item("Nur drüben", station=self.other, pzn=VALID_PZN[2])
        self.location("Lager drüben", station=self.other)
        report = self.run_kind("bestand", [
            self.HEADER,
            ["", VALID_PZN[2], "L1", self.mhd.isoformat(), "", "Hauptlager", "1", "", ""],
            ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Lager drüben", "1", "", ""],
        ])
        self.assertIn("Kein Artikel mit dieser PZN", report.rows[0].errors[0])
        self.assertIn("gibt es auf dieser Wache nicht", report.rows[1].errors[0])
        self.assertFalse(ItemBatch.objects.exists())

    def test_import_never_updates_or_deletes_movements(self):
        original_save = StockMovement.save

        def insert_only(instance, *args, **kwargs):
            if instance.pk is not None:
                raise AssertionError("StockMovement darf nur eingefügt werden")
            return original_save(instance, *args, **kwargs)

        rows = [self.HEADER, ["Mullbinde", "", "L1", self.mhd.isoformat(), "", "Hauptlager", "3", "", ""]]
        with mock.patch.object(StockMovement, "save", insert_only), \
                mock.patch.object(StockMovement, "delete", side_effect=AssertionError("kein Löschen")):
            self.assertImported(self.run_kind("bestand", rows), created=1)
            self.assertImported(self.run_kind("bestand", rows), created=0)
            self.run_kind("bestand", rows, commit=False)
        self.assertEqual(StockMovement.objects.count(), 1)


class DeviceImportTests(ImportTestCase):
    HEADER = ["Gerätebezeichnung", "Risikoklasse", "Hersteller", "Seriennummer", "Inventarnummer", "Anlage 2 (MTK)",
              "MTK-Intervall (M)", "Nächste STK", "Status"]

    def row(self, name="Absaugpumpe", risk="IIa", maker="Hersteller", serial="SN1", inventory="", anlage2="",
            mtk="", next_stk="2030-06-30", status=""):
        return [name, risk, maker, serial, inventory, anlage2, mtk, next_stk, status]

    def test_requires_serial_or_inventory_number(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(serial="", inventory="")])
        self.assertIn("§ 14 MPBetreibV", report.rows[0].errors[0])
        self.assertImported(self.run_kind("medizingeraete", [self.HEADER, self.row(serial="", inventory="INV-1")]),
                            created=1)

    def test_risk_class_is_required(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(risk="")])
        self.assertIn("Pflichtfeld", report.rows[0].errors[0])
        report = self.run_kind("medizingeraete", [["Gerätebezeichnung", "Seriennummer"], ["A", "1"]])
        self.assertIn("Pflichtspalte fehlt: Risikoklasse", report.file_errors[0])
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(risk="Klasse IIb"), self.row(serial="2", risk="3")])
        self.assertImported(report, created=2)
        self.assertEqual(sorted(MedicalDevice.objects.values_list("risk_class", flat=True)), ["III", "IIb"])

    def test_anlage_2_requires_mtk_interval(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(anlage2="Ja")])
        self.assertIn("MTK-Intervall", report.rows[0].errors[0])
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(anlage2="Ja", mtk="12")])
        self.assertImported(report, created=1)
        self.assertEqual(MedicalDevice.objects.get().mtk_interval_months, 12)

    def test_imported_devices_are_ready_and_marked_legacy_without_maintenance_logs(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(next_stk="06/2030")])
        self.assertImported(report, created=1)
        device = MedicalDevice.objects.get(station=self.station)
        self.assertIsNotNone(device.legacy_imported_at)
        self.assertEqual(device.current_status, MedicalDevice.Status.READY)
        self.assertEqual(device.next_stk_date, date(2030, 6, 30))
        self.assertEqual((device.stk_interval_months, device.dguv_interval_months, device.location), (24, 12, "Wache"))
        self.assertEqual(MaintenanceLog.objects.count(), 0)
        self.assertEqual(DeviceTrainingRecord.objects.count(), 0)
        self.assertEqual(device.notes, "")

    def test_existing_device_is_skipped_and_next_stk_unchanged(self):
        existing = MedicalDevice.objects.create(station=self.station, slug="defi", name="Defi", serial_number="sn1",
                                                manufacturer="hersteller", next_stk_date=date(2027, 1, 31))
        MedicalDevice.objects.create(station=self.station, slug="alt", name="Alt", inventory_number="INV-7",
                                     current_status=MedicalDevice.Status.DECOMMISSIONED)
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(next_stk="2031-01-31"),
                                                  self.row(serial="", inventory="inv-7")])
        self.assertImported(report, created=0)
        existing.refresh_from_db()
        self.assertEqual(existing.next_stk_date, date(2027, 1, 31))
        self.assertIsNone(existing.legacy_imported_at)
        # B1: Ein Import nimmt ein außer Betrieb genommenes Gerät nie wieder in Betrieb.
        self.assertEqual(report.rows[0].notes, [])
        self.assertIn("außer Betrieb genommen und bleibt es", report.rows[1].notes[0])
        self.assertEqual(MedicalDevice.objects.get(slug="alt").current_status, MedicalDevice.Status.DECOMMISSIONED)

    def test_same_serial_from_other_manufacturer_is_new_and_duplicates_in_file_are_errors(self):
        MedicalDevice.objects.create(station=self.station, slug="defi", name="Defi", serial_number="SN1",
                                     manufacturer="Andere")
        self.assertImported(self.run_kind("medizingeraete", [self.HEADER, self.row()]), created=1)
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(serial="X", inventory="I1"),
                                                  self.row(serial="Y", inventory="i1")])
        self.assertIn("Inventarnummer wie Zeile 2", report.rows[1].errors[0])

    def test_status_column_is_never_stored(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(status="Eingeschränkt"),
                                                  self.row(serial="2", status="Einsatzklar")])
        self.assertImported(report, created=2)
        self.assertIn("eingeschränkt", " ".join(report.rows[0].notes))
        self.assertEqual(set(MedicalDevice.objects.values_list("current_status", flat=True)), {"ready"})

    def test_locked_device_row_blocks_commit(self):
        for status in ("Gesperrt", "Außer Betrieb (Gesperrt)", "In Wartung / STK", "oob", "defekt"):
            report = self.run_kind("medizingeraete", [self.HEADER, self.row(), self.row(serial="2", status=status)])
            self.assertFalse(report.committed, status)
            self.assertIn("Mangel melden", report.rows[1].errors[0], status)
        self.assertFalse(MedicalDevice.objects.exists())
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(status="kaputt")])
        self.assertIn("kein bekannter Gerätestatus", report.rows[0].errors[0])

    def test_decommissioned_device_row_is_not_imported(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(status="Ausgemustert"),
                                                  self.row(serial="2", status="Außer Betrieb genommen"),
                                                  self.row(serial="3")])
        self.assertImported(report, created=1)
        self.assertEqual([row.status for row in report.rows], ["skipped", "skipped", "new"])
        self.assertEqual(MedicalDevice.objects.get().serial_number, "3")
        self.assertIn("Außer Betrieb genommene Geräte", report.rows[0].notes[0])

    def test_decommissioned_row_with_cell_problems_does_not_block_valid_row(self):
        # Das Bestandsverzeichnis listet auch außer Betrieb genommene Geräte; deren
        # Nummern oder Risikoklasse fehlen oft. Die Zeile wird übersprungen, nicht geprüft.
        report = self.run_kind("medizingeraete", [
            self.HEADER,
            self.row(name="Alt", serial="", inventory="", risk="", next_stk="irgendwann", status="Ausgemustert"),
            self.row(name="Neu", serial="", inventory="INV-9"),
        ])
        self.assertImported(report, created=1)
        self.assertEqual([(row.status, row.errors) for row in report.rows], [("skipped", []), ("new", [])])
        self.assertEqual(report.rows[0].label, "Alt")
        self.assertEqual(MedicalDevice.objects.get().name, "Neu")

    def test_export_with_retired_device_round_trip_skips_it(self):
        from core.evidence import retire_device

        common = {"station": self.station, "risk_class": "IIa", "manufacturer": "GS"}
        MedicalDevice.objects.create(slug="aktiv", name="Aktiv", serial_number="SN-A", **common)
        retired = MedicalDevice.objects.create(slug="alt", name="Alt", serial_number="SN-B", **common)
        self.assertTrue(retire_device(retired, actor=self.admin))
        self.client.force_login(self.admin)
        export = self.client.get(reverse("mpg_export_bestandsverzeichnis")).content
        self.assertIn("Außerbetriebnahme", export.decode("utf-8-sig").splitlines()[0])
        report = self.run_kind("medizingeraete", [], raw=export, station=self.other, actor=self.other_admin)
        self.assertImported(report, created=1)
        self.assertIn("Außerbetriebnahme", [header for header, _hint in report.ignored_headers])
        self.assertEqual(list(MedicalDevice.objects.filter(station=self.other).values_list("name", flat=True)),
                         ["Aktiv"])

    def test_past_dates_and_missing_stk_give_hints(self):
        report = self.run_kind("medizingeraete", [self.HEADER, self.row(next_stk="2001-01-01"),
                                                  self.row(serial="2", next_stk="")])
        self.assertImported(report, created=2)
        self.assertIn("überfällig", report.rows[0].notes[0])
        self.assertIn("Anlage 1", report.rows[1].notes[0])

    def test_bestandsverzeichnis_export_round_trip(self):
        MedicalDevice.objects.create(
            station=self.station, slug="corpuls", name="Defi corpuls3", category="defi", risk_class="IIb",
            manufacturer="GS", model_type="C3", serial_number="SN-9", inventory_number="0815", udi_di="04012345",
            ce_notified_body="0123", year_of_manufacture=2020, acquired_at=date(2020, 3, 1), location="RTW 1",
            is_anlage_2=True, mtk_interval_months=24, stk_interval_months=12, dguv_interval_months=24,
            next_stk_date=date(2030, 1, 31), next_mtk_date=date(2030, 2, 28), next_dguv_date=date(2030, 3, 31),
        )
        self.client.force_login(self.admin)
        export = self.client.get(reverse("mpg_export_bestandsverzeichnis")).content
        header = next(csv.reader(io.StringIO(export.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(header[-5:], ["Anlage 2 (MTK)", "MTK-Intervall (M)", "DGUV-Intervall (M)", "Anschaffungsdatum",
                                       "Aus Altbestand übernommen am"])
        report = self.run_kind("medizingeraete", [], raw=export, station=self.other, actor=self.other_admin)
        self.assertImported(report, created=1)
        fields = ("name", "category", "risk_class", "manufacturer", "model_type", "serial_number", "inventory_number",
                  "udi_di", "ce_notified_body", "year_of_manufacture", "acquired_at", "location", "is_anlage_1",
                  "is_anlage_2", "stk_interval_months", "mtk_interval_months", "dguv_interval_months",
                  "next_stk_date", "next_mtk_date", "next_dguv_date")
        self.assertEqual(
            MedicalDevice.objects.filter(station=self.station).values_list(*fields).get(),
            MedicalDevice.objects.filter(station=self.other).values_list(*fields).get(),
        )
        copy = MedicalDevice.objects.get(station=self.other)
        export_b = self.client_class()
        export_b.force_login(self.other_admin)
        last = list(csv.reader(io.StringIO(export_b.get(reverse("mpg_export_bestandsverzeichnis")).content.decode(
            "utf-8-sig")), delimiter=";"))[1][-1]
        self.assertEqual(last, timezone.localtime(copy.legacy_imported_at).strftime("%d.%m.%Y"))

    def test_device_detail_shows_altbestand_until_first_passed_stk(self):
        self.assertImported(self.run_kind("medizingeraete", [self.HEADER, self.row(anlage2="Ja", mtk="12")]))
        device = MedicalDevice.objects.get()
        self.client.force_login(self.admin)
        url = reverse("mpg_device_detail", args=[device.slug])
        page = self.client.get(url)
        self.assertContains(page, "Aus Altbestand übernommen am")
        self.assertContains(page, 'badge badge-info">Altbestand<', count=3)
        MaintenanceLog.objects.create(device=device, station=self.station, kind="stk", performed_by="Firma",
                                      passed=False, next_due_date=date(2031, 1, 31), created_by=self.admin)
        self.assertContains(self.client.get(url), 'badge badge-info">Altbestand<', count=3)
        MaintenanceLog.objects.create(device=device, station=self.station, kind="stk", performed_by="Firma",
                                      passed=True, next_due_date=date(2031, 1, 31), created_by=self.admin)
        page = self.client.get(url)
        self.assertContains(page, 'badge badge-info">Altbestand<', count=2)
        self.assertContains(page, "Aus Altbestand übernommen am")
        manual = MedicalDevice.objects.create(station=self.station, slug="manuell", name="Manuell")
        page = self.client.get(reverse("mpg_device_detail", args=[manual.slug]))
        self.assertNotContains(page, "Aus Altbestand übernommen am")
        self.assertNotContains(page, 'badge badge-info">Altbestand<')

    def test_device_slug_avoids_station_asset_ids(self):
        StationAsset.objects.create(station=self.station, asset_id="absaugpumpe", label="Absaugpumpe alt",
                                    kind=StationAsset.Kind.DEVICE, status=StationAsset.Status.OOB)
        self.assertImported(self.run_kind("medizingeraete", [self.HEADER, self.row()]), created=1)
        device = MedicalDevice.objects.get(station=self.station)
        self.assertEqual(device.slug, "absaugpumpe-1")
        self.assertEqual(StationAsset.objects.get().status, StationAsset.Status.OOB)


class ImportViewSecurityTests(ImportTestCase):
    ARTICLE_ROWS = [["Artikel", "PZN"], ["Mullbinde", VALID_PZN[0]]]

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.run_url = reverse("masterdata_import_run", args=["artikel"])

    def upload(self, rows=None, raw=None, client=None, slug="artikel"):
        raw = raw if raw is not None else csv_bytes(rows or self.ARTICLE_ROWS)
        return (client or self.client).post(reverse("masterdata_import_run", args=[slug]), {
            "step": "check", "file": SimpleUploadedFile("liste.csv", raw, content_type="text/csv"),
        })

    def commit(self, response, client=None, slug="artikel", **override):
        data = {"step": "commit", "payload": response.context["payload"], "digest": response.context["report"].digest,
                "token": response.context["token"]}
        data.update(override)
        return (client or self.client).post(reverse("masterdata_import_run", args=[slug]), data)

    def test_only_admin_can_use_import(self):
        urls = [reverse("masterdata_import"), self.run_url, reverse("masterdata_import_template", args=["artikel"])]
        for role in (Membership.Role.MEMBER, Membership.Role.SHIFT_LEAD, Membership.Role.CASHIER,
                     Membership.Role.AUDITOR):
            user = User.objects.create_user(username=f"u-{role}", password="x-test-pass-123")
            Membership.objects.create(user=user, station=self.station, role=role)
            client = Client()
            client.force_login(user)
            for url in urls:
                self.assertEqual(client.get(url).status_code, 403, (role, url))
            response = client.post(self.run_url, {"step": "check", "file": SimpleUploadedFile("a.csv", b"Artikel\nA\n")})
            self.assertEqual(response.status_code, 403, role)
        anonymous = Client()
        for url in urls:
            self.assertRedirects(anonymous.get(url), f"{reverse('login')}?{urlencode({'next': url})}",
                                 fetch_redirect_response=False)
        self.assertFalse(MedicalItem.objects.exists())

    def test_disabled_module_kind_and_unknown_kind_are_404(self):
        Station.objects.filter(pk=self.station.pk).update(mpg_enabled=False)
        self.assertEqual(self.client.get(reverse("masterdata_import_run", args=["medizingeraete"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("masterdata_import_template", args=["medizingeraete"])).status_code,
                         404)
        self.assertEqual(self.client.get(reverse("masterdata_import_run", args=["unbekannt"])).status_code, 404)
        overview = self.client.get(reverse("masterdata_import"))
        self.assertNotContains(overview, reverse("masterdata_import_run", args=["medizingeraete"]))
        self.assertContains(overview, reverse("masterdata_import_run", args=["artikel"]))

    def test_overview_counts_only_own_station(self):
        self.item("Eigen")
        self.item("Fremd 1", station=self.other)
        self.item("Fremd 2", station=self.other)
        page = self.client.get(reverse("masterdata_import"))
        self.assertContains(page, "Vorhanden: 1")
        self.assertNotContains(page, "Vorhanden: 2")

    def test_kind_page_documents_columns(self):
        page = self.client.get(reverse("masterdata_import_run", args=["medizingeraete"]))
        self.assertContains(page, "<code>Risikoklasse</code>", html=False)
        self.assertContains(page, "Klasse IIa")
        self.assertContains(page, 'name="file"')

    def test_preview_writes_nothing(self):
        models = (MedicalItem, StorageLocation, ItemBatch, StockItem, StockMovement, MedicalDevice, StationAsset,
                  MaintenanceLog, AuditEvent, User, Membership)
        # Für den Bestand: vorhandener Artikel und Lagerort, neue Charge.
        self.item("Kompresse", pzn=VALID_PZN[1])
        self.location("Fach 9")
        mhd = (timezone.localdate() + timedelta(days=300)).isoformat()
        before = {model: model.objects.count() for model in models}
        for slug, rows in (
            ("lagerorte", [["Lagerort"], ["Hauptlager"]]),
            ("artikel", self.ARTICLE_ROWS),
            ("bestand", [["Artikel", "Charge (Lot)", "Hersteller-MHD", "Lagerort", "Bestand"],
                         ["Kompresse", "L-9", mhd, "Fach 9", "5"]]),
            ("medizingeraete", [["Gerätebezeichnung", "Risikoklasse", "Seriennummer"], ["Absaugpumpe", "IIa", "1"]]),
        ):
            response = self.upload(rows, slug=slug)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["can_commit"], slug)
        self.assertEqual({model: model.objects.count() for model in models}, before)

    def test_preview_then_commit_imports_and_writes_one_audit_event_with_counts_only(self):
        preview = self.upload([["Artikel", "PZN"], ["Geheimer Artikelname", VALID_PZN[0]], ["Zweiter", ""]])
        self.assertIn("no-store", preview["Cache-Control"])
        self.assertContains(preview, "Jetzt importieren (2 neu)")
        self.assertContains(preview, "data-submit-once")
        done = self.commit(preview)
        self.assertEqual(done.status_code, 200)
        self.assertTemplateUsed(done, "core/masterdata_import_done.html")
        self.assertIn("no-store", done["Cache-Control"])
        self.assertEqual(MedicalItem.objects.filter(station=self.station).count(), 2)
        events = AuditEvent.objects.filter(action__startswith="import.")
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual((event.action, event.object_type, event.station, event.actor),
                         ("import.articles", "Station", self.station, self.admin))
        self.assertEqual(set(event.metadata), {"kind", "counts", "sha256", "encoding", "delimiter"})
        self.assertEqual(event.metadata["counts"], {"rows": 2, "created": 2, "skipped": 0, "warnings": 0})
        self.assertEqual(event.metadata["sha256"], preview.context["report"].digest)
        self.assertNotIn("Geheimer", json.dumps(event.metadata))
        self.assertNotIn("liste.csv", json.dumps(event.metadata))
        audit_page = self.client.get(reverse("audit_log"))
        self.assertContains(audit_page, "Artikel importiert")

    def test_done_page_points_to_locations_before_warehouse(self):
        # Ohne Lagerorte legte „Zum Lager“ drei Beispiel-Lagerorte an (warehouse_dashboard).
        done = self.commit(self.upload())
        self.assertTrue(done.context["locations_missing"])
        self.assertNotContains(done, f'href="{reverse("warehouse_dashboard")}"')
        self.assertContains(done, reverse("masterdata_import_run", args=["lagerorte"]))
        self.assertContains(done, "drei Beispiel-Lagerorte")
        self.assertFalse(StorageLocation.objects.filter(station=self.station).exists())
        self.location("Hauptlager")
        done = self.commit(self.upload([["Artikel"], ["Zweiter Artikel"]]))
        self.assertFalse(done.context["locations_missing"])
        self.assertContains(done, f'href="{reverse("warehouse_dashboard")}"')
        self.assertNotContains(done, "drei Beispiel-Lagerorte")

    def test_commit_rejects_tampered_payload_expired_token_and_foreign_station_or_user(self):
        preview = self.upload()
        tampered = base64.b64encode(csv_bytes([["Artikel"], ["Anderer Inhalt"]])).decode()
        response = self.commit(preview, payload=tampered)
        self.assertContains(response, "Die Vorschau ist abgelaufen oder die Datei wurde verändert", status_code=400)
        response = self.commit(preview, payload=tampered,
                               digest=hashlib.sha256(base64.b64decode(tampered)).hexdigest())
        self.assertEqual(response.status_code, 400)
        response = self.commit(preview, payload="kein base64!")
        self.assertEqual(response.status_code, 400)
        # Ein Token für eine andere Art gilt nicht.
        response = self.commit(preview, slug="lagerorte")
        self.assertEqual(response.status_code, 400)
        # Abgelaufen (älter als eine Stunde).
        with mock.patch.object(signing, "time") as patched_time:
            patched_time.time.return_value = time.time() + mi.TOKEN_MAX_AGE + 60
            response = self.commit(preview)
        self.assertEqual(response.status_code, 400)
        # Admin einer anderen Wache bzw. eine andere Person mit demselben Token.
        other_client = Client()
        other_client.force_login(self.other_admin)
        self.assertEqual(self.commit(preview, client=other_client).status_code, 400)
        second_admin = User.objects.create_user(username="zweite", password="x-test-pass-123")
        Membership.objects.create(user=second_admin, station=self.station, role=Membership.Role.ADMIN)
        second_client = Client()
        second_client.force_login(second_admin)
        self.assertEqual(self.commit(preview, client=second_client).status_code, 400)
        self.assertFalse(MedicalItem.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__startswith="import.").exists())
        # Mit gültigem Token klappt es genau einmal; die Wiederholung legt nichts doppelt an.
        self.assertTemplateUsed(self.commit(preview), "core/masterdata_import_done.html")
        again = self.commit(preview)
        self.assertEqual(MedicalItem.objects.count(), 1)
        self.assertEqual(again.context["counts"]["created"], 0)

    def test_commit_is_all_or_nothing_when_data_changed_after_preview(self):
        preview = self.upload([["Artikel", "PZN", "Mindestbestand"], ["A", VALID_PZN[0], "1"],
                               ["B", VALID_PZN[1], "1"]])
        self.assertTrue(preview.context["can_commit"])
        self.item("Kollegin war schneller", pzn=VALID_PZN[1], min_stock=3)
        response = self.commit(preview)
        self.assertTemplateUsed(response, "core/masterdata_import_preview.html")
        self.assertTrue(response.context["report"].changed)
        self.assertContains(response, "Seit der Prüfung hat sich der Datenbestand geändert")
        self.assertEqual(MedicalItem.objects.count(), 1)  # nur der Artikel der Kollegin
        self.assertFalse(AuditEvent.objects.filter(action__startswith="import.").exists())
        # Die neue Vorschau lässt sich bestätigen.
        self.assertEqual(response.context["counts"]["created"], 1)
        self.assertTemplateUsed(self.commit(response), "core/masterdata_import_done.html")
        self.assertEqual(MedicalItem.objects.count(), 2)
        # Ändert sich die Lage so, dass eine Zeile ungültig wird, entsteht gar nichts.
        StorageLocation.objects.create(station=self.station, slug="x", name="Hauptlager")
        loc_preview = self.upload([["Lagerort", "Übergeordneter Lagerort"], ["Fach", "Hauptlager"], ["Koffer", ""]],
                                  slug="lagerorte")
        StorageLocation.objects.create(station=self.station, slug="y", name="Hauptlager", parent=None)
        response = self.commit(loc_preview, slug="lagerorte")
        self.assertTemplateUsed(response, "core/masterdata_import_preview.html")
        self.assertFalse(response.context["can_commit"])
        self.assertIn("mehrdeutig", response.context["report"].rows[0].errors[0])
        self.assertFalse(StorageLocation.objects.filter(name__in=["Fach", "Koffer"]).exists())

    def test_database_error_during_commit_rolls_everything_back(self):
        rows = [["Artikel"], ["A"], ["B"], ["C"]]
        calls = {"n": 0}
        original = MedicalItem.save

        def failing(instance, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                from django.db import IntegrityError
                raise IntegrityError("simuliert")
            return original(instance, *args, **kwargs)

        with mock.patch.object(MedicalItem, "save", failing):
            report = self.run_kind("artikel", rows)
        self.assertFalse(report.committed)
        self.assertIn("Zeile 4 konnte nicht gespeichert werden", report.file_errors[0])
        self.assertFalse(MedicalItem.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__startswith="import.").exists())

    def test_oversized_upload_is_rejected(self):
        raw = b"Artikel\r\n" + b"A" * (mi.MAX_FILE_BYTES + 10)
        response = self.upload(raw=raw)
        self.assertContains(response, "größer als 1 MB", status_code=400)
        self.assertFalse(MedicalItem.objects.exists())
        self.assertEqual(self.client.post(self.run_url, {"step": "check"}).status_code, 400)

    def test_run_view_enforces_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(self.run_url, {"step": "check", "file": SimpleUploadedFile("a.csv", csv_bytes(
            self.ARTICLE_ROWS))})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.post(self.run_url, {"step": "commit", "payload": "x", "digest": "0" * 64,
                                                    "token": "x"}).status_code, 403)
        # Mit Token: Prüfen (multipart) und Bestätigen (urlencoded) funktionieren.
        page = client.get(self.run_url)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        preview = client.post(self.run_url, {"csrfmiddlewaretoken": token, "step": "check",
                                             "file": SimpleUploadedFile("a.csv", csv_bytes(self.ARTICLE_ROWS))})
        self.assertEqual(preview.status_code, 200)
        done = client.post(self.run_url, {
            "csrfmiddlewaretoken": token, "step": "commit", "payload": preview.context["payload"],
            "digest": preview.context["report"].digest, "token": preview.context["token"],
        })
        self.assertTemplateUsed(done, "core/masterdata_import_done.html")
        self.assertEqual(MedicalItem.objects.count(), 1)

    def test_payload_not_persisted_in_session_or_db(self):
        raw = csv_bytes([["Artikel", "PZN"], ["Unverwechselbar-Q7", VALID_PZN[0]]])
        self.client.get(self.run_url)
        session_before = dict(self.client.session.items())
        preview = self.upload(raw=raw)
        payload = preview.context["payload"]
        self.assertEqual(dict(self.client.session.items()), session_before)
        self.commit(preview)
        self.assertEqual(dict(self.client.session.items()), session_before)
        from django.apps import apps

        text = raw.decode("utf-8-sig")
        with connection.cursor() as cursor:
            for model in apps.get_models():
                if not model._meta.managed or model._meta.proxy:
                    continue
                for field in model._meta.concrete_fields:
                    if field.get_internal_type() not in ("CharField", "TextField", "JSONField"):
                        continue
                    table = connection.ops.quote_name(model._meta.db_table)
                    column = connection.ops.quote_name(field.column)
                    for needle in (payload, text):
                        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE CAST({column} AS TEXT) LIKE %s",
                                       [f"%{needle}%"])
                        self.assertEqual(cursor.fetchone()[0], 0, (model.__name__, field.name))

    def test_preview_escapes_cell_values(self):
        response = self.upload([["Lagerort"], ["<script>alert(1)</script>"]], slug="lagerorte")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_preview_shows_errors_and_offers_upload_again(self):
        wrong = VALID_PZN[0][:7] + str((int(VALID_PZN[0][7]) + 1) % 10)
        response = self.upload([["Artikel", "PZN"], ["A", wrong]])
        self.assertContains(response, "Bitte die Datei korrigieren und erneut prüfen.")
        self.assertContains(response, "Prüfziffer")
        self.assertNotContains(response, 'name="payload"')
        self.assertFalse(response.context["can_commit"])

    def test_template_download_has_bom_semicolon_and_example_row(self):
        response = self.client.get(reverse("masterdata_import_template", args=["artikel"]))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="wachwerk-vorlage-artikel.csv"', response["Content-Disposition"])
        body = response.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        lines = body.decode("utf-8-sig").splitlines()
        self.assertTrue(lines[0].startswith("Artikel*;Kategorie;Einheit;PZN"))
        self.assertTrue(lines[1].startswith("# Beispiel"))
        # Die unveränderte Vorlage ist eine gültige, aber leere Datei.
        preview = self.upload(raw=body)
        self.assertIn("keine Datenzeilen", preview.context["report"].file_errors[0])

    def test_more_page_shows_import_card_only_for_admins(self):
        self.assertContains(self.client.get(reverse("more")), reverse("masterdata_import"))
        lead = User.objects.create_user(username="lead", password="x-test-pass-123")
        Membership.objects.create(user=lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        client = Client()
        client.force_login(lead)
        self.assertNotContains(client.get(reverse("more")), reverse("masterdata_import"))

    def test_import_overview_renders_in_english(self):
        self.client.cookies["wachbuch_language"] = "en"
        page = self.client.get(reverse("masterdata_import"), HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(page, "Import master data")
        self.assertNotContains(page, "Stammdaten importieren")


class ImportTerminalTests(TerminalTestCase):
    def test_terminal_account_cannot_import(self):
        self.use_terminal()
        self.unlock()
        for url in (reverse("masterdata_import"), reverse("masterdata_import_run", args=["artikel"])):
            response = self.client.get(url)
            self.assertNotEqual(response.status_code, 200, url)
        response = self.client.post(reverse("masterdata_import_run", args=["artikel"]), {
            "step": "check", "file": SimpleUploadedFile("a.csv", b"Artikel\r\nA\r\n"),
        })
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(MedicalItem.objects.exists())


@override_settings(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)
class ImportDemoSandboxTests(TestCase):
    def test_demo_sandbox_blocks_import_run(self):
        from django.core.cache import cache

        cache.clear()
        self.client.post(reverse("login"), {"username": "Demo", "password": "Demo"})
        overview = self.client.get(reverse("masterdata_import"))
        self.assertEqual(overview.status_code, 200)
        self.assertNotContains(overview, f'"{reverse("masterdata_import_run", args=["artikel"])}"')
        self.assertEqual(self.client.get(reverse("masterdata_import_template", args=["artikel"])).status_code, 200)
        response = self.client.get(reverse("masterdata_import_run", args=["artikel"]))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("masterdata_import_run", args=["artikel"]), {
            "step": "check", "file": SimpleUploadedFile("a.csv", b"Artikel\r\nDemo-Import\r\n"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MedicalItem.objects.filter(name="Demo-Import").exists())


@skipUnless(connection.vendor == "postgresql", "Sperrverhalten nur unter PostgreSQL prüfbar")
class ImportLockTests(TransactionTestCase):
    def test_import_lock_does_not_block_other_writes_of_the_station(self):
        station = Station.objects.create(name="RW Sperre", slug="rw-sperre")
        admin = User.objects.create_user(username="sperre", password="x-test-pass-123")
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        results = []
        original = mi.StorageLocationHandler.apply_all

        def other_write():
            from django.db import connection as thread_connection

            try:
                with thread_connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '2s'")
                AuditEvent.objects.create(station=station, actor=admin, action="test.parallel",
                                          object_type="Station", object_id=str(station.pk))
                results.append("ok")
            except Exception as exc:  # pragma: no cover - nur bei Regression
                results.append(type(exc).__name__)
            finally:
                thread_connection.close()

        def apply_all(handler, entries):
            # Läuft innerhalb der Import-Transaktion, die die Wache gesperrt hat.
            thread = threading.Thread(target=other_write)
            thread.start()
            thread.join(10)
            return original(handler, entries)

        with mock.patch.object(mi.StorageLocationHandler, "apply_all", apply_all):
            report = mi.run_import(mi.KINDS["lagerorte"], station=station, actor=admin,
                                   raw=csv_bytes([["Lagerort"], ["Hauptlager"]]), commit=True)
        self.assertTrue(report.committed)
        self.assertEqual(results, ["ok"])
        self.assertTrue(StorageLocation.objects.filter(station=station, name="Hauptlager").exists())


class ImportPerformanceTests(ImportTestCase):
    def test_300_articles_and_40_devices_import_within_query_budget(self):
        pzns = valid_pzns(300)
        article_rows = [["Artikel", "PZN", "Einheit", "Kategorie", "Mindestbestand", "Sollbestand"]] + [
            [f"Artikel {n:03d}", pzn, "Stück", "Sonstiges Material", "1", "2"] for n, pzn in enumerate(pzns)
        ]
        device_rows = [["Gerätebezeichnung", "Risikoklasse", "Hersteller", "Seriennummer", "Inventarnummer",
                        "Nächste STK", "Nächste DGUV V3"]] + [
            [f"Gerät {n:02d}", "IIa", "Hersteller", f"SN-{n:03d}", f"INV-{n:03d}", "06/2030", "06/2030"]
            for n in range(40)
        ]
        self.location("Hauptlager")
        started = time.monotonic()
        for slug, rows, budget in (("artikel", article_rows, 300 + 20), ("medizingeraete", device_rows, 2 * 40 + 20)):
            for commit in (False, True):
                with CaptureQueriesContext(connection) as queries:
                    report = self.run_kind(slug, rows, commit=commit)
                self.assertEqual(report.file_errors, [], slug)
                self.assertEqual(report.counts["errors"], 0, slug)
                self.assertEqual(report.counts["created"], len(rows) - 1, slug)
                self.assertLessEqual(len(queries), budget, (slug, commit))
        stock_rows = [["PZN", "Charge (Lot)", "Hersteller-MHD", "Lagerort", "Bestand"]] + [
            [pzn, "L1", "12/2030", "Hauptlager", "5"] for pzn in pzns
        ]
        with CaptureQueriesContext(connection) as queries:
            report = self.run_kind("bestand", stock_rows)
        self.assertImported(report, created=300)
        self.assertLessEqual(len(queries), 3 * 300 + 20)
        elapsed = time.monotonic() - started
        logger.info("Stammdatenimport 300 Artikel + 40 Geräte + 300 Bestände: %.2f s", elapsed)
        self.assertEqual(MedicalItem.objects.filter(station=self.station).count(), 300)
        self.assertEqual(MedicalDevice.objects.filter(station=self.station).count(), 40)
        self.assertEqual(StockMovement.objects.filter(station=self.station, kind="legacy").count(), 300)
        self.assertLess(elapsed, 120)
