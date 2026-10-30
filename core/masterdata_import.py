"""CSV-Stammdatenimport (ROADMAP 0.27, Baustein 7).

Nur für Master-Admins (Ansichten in ``core/masterdata_import_views.py``). Je Art
gibt es eine Vorlage; die hochgeladene Datei wird nur im Arbeitsspeicher
gelesen und nie gespeichert.

Ablauf je Datei:

1. ``decode_upload`` erkennt UTF-8 (mit/ohne BOM) oder Windows-1252 und weist
   UTF-16, Excel-Dateien und Binärdaten mit konkretem Hinweis ab.
2. ``read_table`` erkennt das Trennzeichen (``;`` oder ``,``, optional die
   Excel-Zeile ``sep=;``), ordnet die Spalten zu und liefert jede Zeile mit
   ihrer physischen Zeilennummer.
3. ``run_import`` prüft alle Zeilen gegen die einmal vorgeladenen Daten der
   eigenen Wache, legt bei fehlerfreier Datei alles in einer Transaktion an und
   rollt beim Trockenlauf (``commit=False``) wieder zurück. Die Vorschau zeigt
   damit genau, was der Import tun wird.

Grundsätze:

- Nur Anlegen, nie Ändern: Vorhandenes (natürlicher Schlüssel je Art) wird
  übersprungen. Ein erneuter Import derselben Datei ändert nichts.
- Alles oder nichts: Ein Fehler in einer Zeile verhindert den ganzen Import.
- Produktgrenze: Status-, Zustands- und Freitextspalten werden nie übernommen.
- Jede Abfrage ist an die Wache gebunden; Zuordnungen (Artikel, Lagerort,
  übergeordneter Lagerort) finden nur Objekte der eigenen Wache.
- Im Audit-Log stehen nur Art, Anzahl, Kodierung, Trennzeichen und SHA-256 der
  Datei, nie Zellwerte oder der Dateiname.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone, translation
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .csv_safety import FORMULA_PREFIXES
from .models import Station
from .mpg_models import MedicalDevice
from .services import audit
from .wachalltag_models import StationAsset
from .warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 1_048_576
MAX_ROWS = 2000
MAX_COLUMNS = 50
MAX_CELL_CHARS = 1000
# Übliche Platzhalter für „leer“ in Excel-Listen.
EMPTY_PLACEHOLDERS = frozenset({"-", "–", "—"})
TOKEN_SALT = "core.masterdata_import"
TOKEN_MAX_AGE = 3600
# Größe des Base64-Inhalts im Bestätigungsformular (1 MiB Datei → 1 398 104 Zeichen).
MAX_PAYLOAD_CHARS = 1_400_000
PATH_SEPARATOR_RE = re.compile(r"\s*(?:→|->|>)\s*")
MOJIBAKE_MARKERS = ("Ã¤", "Ã¶", "Ã¼", "ÃŸ", "Ã„", "Ã–", "Ãœ", "â€")
ENCODING_LABELS = {
    "utf-8": "UTF-8",
    "utf-8-sig": gettext_lazy("UTF-8 mit BOM"),
    "cp1252": gettext_lazy("Windows-1252 (ANSI)"),
}
DELIMITER_LABELS = {
    ";": gettext_lazy("Semikolon (;)"),
    ",": gettext_lazy("Komma (,)"),
    "\t": gettext_lazy("Tabulator"),
    "|": gettext_lazy("senkrechter Strich (|)"),
}


class ImportFileError(Exception):
    """Die Datei als Ganzes lässt sich nicht verarbeiten."""


class CellError(Exception):
    """Ein einzelner Wert ist ungültig; die Meldung ist übersetzt."""


# --- Normalisierung --------------------------------------------------------

_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "–": "-", "—": "-"})


def norm(value) -> str:
    """Vergleichsschlüssel: casefold, Leerraum zusammengefasst, Umlaute umschrieben."""
    return " ".join(str(value).split()).casefold().translate(_TRANSLIT)


def normalize_header(value) -> str:
    text = str(value).replace("\ufeff", "").strip()
    while text.endswith("*"):
        text = text[:-1].rstrip()
    return norm(text)


def digits_key(value, width: int) -> str:
    """Nur Ziffern, links mit Nullen aufgefüllt (PZN 8, GTIN 14); leer bleibt leer."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(width) if digits else ""


def path_segments(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in PATH_SEPARATOR_RE.split(value.strip()))


# --- Datenstrukturen -------------------------------------------------------


@dataclass(frozen=True)
class Column:
    header: str
    key: str
    help: object
    required: bool = False
    aliases: tuple = ()
    allowed: object = None  # Callable → Liste erlaubter (deutscher) Werte

    def allowed_values(self) -> list[str]:
        if self.allowed is None:
            return []
        with translation.override("de"):
            return [str(value) for value in self.allowed()]


@dataclass(frozen=True)
class ImportKind:
    slug: str
    title: object
    description: object
    module_flag: str
    audit_action: str
    columns: tuple
    handler_cls: type
    not_imported_text: object
    ignored_headers: tuple = ()  # ((Überschrift, Grund), …)
    max_rows: int = MAX_ROWS
    example_row: tuple = ()  # ((key, Wert), …)
    require_one_of: tuple = ()  # ((key, key, …), …)
    next_url_name: str = ""
    next_label: object = ""

    def column(self, key: str) -> Column:
        for column in self.columns:
            if column.key == key:
                return column
        raise KeyError(key)

    def header_lookup(self) -> dict[str, str]:
        lookup = {}
        for column in self.columns:
            for header in (column.header, *column.aliases):
                lookup[normalize_header(header)] = column.key
        return lookup

    def ignored_lookup(self) -> dict[str, object]:
        return {normalize_header(header): reason for header, reason in self.ignored_headers}

    def known_headers(self) -> set[str]:
        return set(self.header_lookup()) | set(self.ignored_lookup())


@dataclass
class ParsedRow:
    line: int
    values: dict
    errors: list
    bad: set


@dataclass
class Table:
    delimiter: str
    rows: list
    ignored: list


@dataclass
class RowResult:
    line: int
    label: str = ""
    status: str = "new"  # new | skipped | error
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def has_messages(self) -> bool:
        return bool(self.errors or self.notes)


@dataclass
class ImportReport:
    kind: ImportKind
    digest: str
    encoding: str = ""
    delimiter: str = ""
    file_errors: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    ignored_headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    committed: bool = False
    # Beim Bestätigen: Ergebnis weicht von der bestätigten Vorschau ab.
    changed: bool = False

    @property
    def plan_digest(self) -> str:
        """Kurzer Fingerabdruck des Ergebnisses je Zeile (neu/übersprungen/Fehler)."""
        plan = "|".join(f"{row.line}:{row.status}" for row in self.rows)
        return hashlib.sha256(plan.encode()).hexdigest()[:16]

    @property
    def has_errors(self) -> bool:
        return bool(self.file_errors) or any(row.status == "error" for row in self.rows)

    @property
    def counts(self) -> dict:
        return {
            "rows": len(self.rows),
            "created": sum(1 for row in self.rows if row.status == "new"),
            "skipped": sum(1 for row in self.rows if row.status == "skipped"),
            "warnings": sum(1 for row in self.rows if row.notes),
            "errors": sum(1 for row in self.rows if row.status == "error"),
        }

    @property
    def ignored_groups(self) -> list[tuple[str, list[str]]]:
        groups: dict[str, list[str]] = {}
        for header, reason in self.ignored_headers:
            groups.setdefault(str(reason), []).append(header)
        return list(groups.items())

    @property
    def encoding_label(self) -> str:
        return str(ENCODING_LABELS.get(self.encoding, self.encoding))

    @property
    def delimiter_label(self) -> str:
        return str(DELIMITER_LABELS.get(self.delimiter, self.delimiter))

    @property
    def rows_with_messages(self) -> list[RowResult]:
        return [row for row in self.rows if row.has_messages]


# --- Datei lesen -----------------------------------------------------------


def decode_upload(raw: bytes) -> tuple[str, str]:
    if not raw or not raw.strip():
        raise ImportFileError(_("Die Datei ist leer."))
    if raw.startswith(b"PK\x03\x04") or raw.startswith(b"\xd0\xcf\x11\xe0"):
        raise ImportFileError(
            _("Das ist eine Excel-Datei. Bitte in Excel „Speichern unter“ → „CSV UTF-8 (durch Trennzeichen getrennt)“ wählen.")
        )
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ImportFileError(
            _("Die Datei ist in UTF-16 gespeichert. Bitte in Excel „CSV UTF-8 (durch Trennzeichen getrennt)“ wählen.")
        )
    if b"\x00" in raw:
        raise ImportFileError(
            _("Die Datei ist keine Textdatei. Bitte in Excel „CSV UTF-8 (durch Trennzeichen getrennt)“ wählen.")
        )
    try:
        text = raw.decode("utf-8-sig")
        return text, ("utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        raise ImportFileError(
            _("Die Zeichenkodierung der Datei ist unbekannt. Bitte als „CSV UTF-8 (durch Trennzeichen getrennt)“ speichern.")
        ) from None


def text_hints(text: str) -> list[str]:
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return [
            _("Die Datei enthält doppelt umgewandelte Umlaute (z. B. „Ã¼“ statt „ü“). "
              "Bitte die Originaldatei erneut als „CSV UTF-8“ speichern.")
        ]
    return []


def clean_cell(raw: str) -> str:
    if len(raw) > MAX_CELL_CHARS:
        raise CellError(_("Der Wert ist länger als %(max)s Zeichen.") % {"max": MAX_CELL_CHARS})
    value = raw.strip()
    if value in EMPTY_PLACEHOLDERS:
        return ""
    if raw[:1] in FORMULA_PREFIXES or value[:1] in FORMULA_PREFIXES:
        raise CellError(_("Der Wert darf nicht mit =, +, -, @ oder einem Tabulator beginnen."))
    return value


def _first_record(text: str, delimiter: str):
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        for row in reader:
            cells = [cell.strip() for cell in row]
            if not any(cells) or cells[0].startswith("#"):
                continue
            return row
    except csv.Error:
        return None
    return None


def _detect_delimiter(text: str, kind: ImportKind) -> str:
    known = kind.known_headers()
    scores = {}
    for delimiter in (";", ","):
        header = _first_record(text, delimiter) or []
        scores[delimiter] = sum(1 for cell in header if normalize_header(cell) in known)
    return "," if scores[","] > scores[";"] else ";"


def read_table(text: str, kind: ImportKind) -> Table:
    # Die bisherigen Exporte schreiben vor jede Zeile ein BOM (utf-8-sig je
    # write); ein BOM ist nie Teil eines Werts.
    text = text.replace("\ufeff", "")
    line_offset = 0
    first_line, newline, rest = text.partition("\n")
    sep = re.fullmatch(r'\s*"?sep=(.)"?\s*', first_line.rstrip("\r"), flags=re.IGNORECASE)
    if sep:
        delimiter = sep.group(1)
        if delimiter not in DELIMITER_LABELS:
            raise ImportFileError(_("Das Trennzeichen in der Zeile „sep=…“ wird nicht unterstützt. Bitte ; oder , verwenden."))
        text = rest
        line_offset = 1
    else:
        delimiter = _detect_delimiter(text, kind)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    headers = None
    colmap: dict[int, str] = {}
    ignored: list[tuple[str, object]] = []
    rows: list[ParsedRow] = []
    while True:
        line = reader.line_num + 1 + line_offset
        try:
            record = next(reader)
        except StopIteration:
            break
        except csv.Error:
            raise ImportFileError(
                _("Zeile %(line)s lässt sich nicht lesen. Bitte Anführungszeichen in dieser Zeile prüfen.") % {"line": line}
            ) from None
        stripped = [cell.strip() for cell in record]
        if not any(stripped) or stripped[0].startswith("#"):
            continue
        if headers is None:
            headers, colmap, ignored = _read_header(record, kind)
            continue
        if len(rows) >= kind.max_rows:
            raise ImportFileError(
                _("Die Datei hat mehr als %(max)s Datenzeilen. Bitte auf mehrere Dateien aufteilen.") % {"max": kind.max_rows}
            )
        values: dict[str, str] = {}
        errors: list[str] = []
        bad: set[str] = set()
        for index, raw in enumerate(record):
            key = colmap.get(index)
            if key is None:
                if raw.strip() and (index >= len(headers) or not headers[index]):
                    errors.append(_("Spalte %(number)s: Wert ohne Spaltenüberschrift.") % {"number": index + 1})
                continue
            try:
                values[key] = clean_cell(raw)
            except CellError as exc:
                errors.append(f"{headers[index]}: {exc}")
                values[key] = ""
                bad.add(key)
        rows.append(ParsedRow(line=line, values=values, errors=errors, bad=bad))

    if headers is None:
        raise ImportFileError(_("Die Datei enthält keine Spaltenüberschriften."))
    if not rows:
        raise ImportFileError(_("Die Datei enthält keine Datenzeilen."))
    return Table(delimiter=delimiter, rows=rows, ignored=ignored)


def _read_header(record: list[str], kind: ImportKind):
    headers = [cell.replace("\ufeff", "").strip() for cell in record]
    while headers and not headers[-1]:
        headers.pop()
    if len(headers) > MAX_COLUMNS:
        raise ImportFileError(_("Die Datei hat mehr als %(max)s Spalten.") % {"max": MAX_COLUMNS})
    lookup = kind.header_lookup()
    ignored_lookup = kind.ignored_lookup()
    colmap: dict[int, str] = {}
    seen: dict[str, str] = {}
    ignored: list[tuple[str, object]] = []
    for index, header in enumerate(headers):
        if not header:
            continue
        normalized = normalize_header(header)
        key = lookup.get(normalized)
        if key is not None:
            if key in seen:
                raise ImportFileError(
                    _("Die Spalte „%(header)s“ kommt doppelt vor (auch als „%(other)s“).")
                    % {"header": header, "other": seen[key]}
                )
            seen[key] = header
            colmap[index] = key
        elif normalized in ignored_lookup:
            ignored.append((header, ignored_lookup[normalized]))
        else:
            ignored.append((header, gettext_lazy("unbekannte Spalte – wird nicht übernommen")))
    missing = [column.header for column in kind.columns if column.required and column.key not in seen]
    if missing:
        raise ImportFileError(_("Pflichtspalte fehlt: %(headers)s.") % {"headers": ", ".join(missing)})
    for group in kind.require_one_of:
        if not any(key in seen for key in group):
            names = ", ".join(kind.column(key).header for key in group)
            raise ImportFileError(_("Mindestens eine dieser Spalten wird gebraucht: %(headers)s.") % {"headers": names})
    return headers, colmap, ignored


def template_csv(kind: ImportKind) -> str:
    """Vorlage mit BOM, ``;``, Überschrift und einer übersprungenen Beispielzeile."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    example = dict(kind.example_row)
    with translation.override("de"):
        writer.writerow([column.header + ("*" if column.required else "") for column in kind.columns])
        writer.writerow([str(example.get(column.key, "")) for column in kind.columns])
    return "\ufeff" + buffer.getvalue()


# --- Werte prüfen ----------------------------------------------------------

TRUE_WORDS = frozenset({"ja", "j", "x", "1", "true", "wahr", "yes", "y"})
FALSE_WORDS = frozenset({"nein", "n", "0", "false", "falsch", "no"})
_SCIENTIFIC_RE = re.compile(r"^\d+(?:[.,]\d+)?e\+?\d+$", re.IGNORECASE)
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_TIME_SUFFIX_RE = re.compile(r"\s+\d{1,2}:\d{2}(?::\d{2})?$")


def _scientific(value: str) -> bool:
    return bool(_SCIENTIFIC_RE.match(value.replace(" ", "")))


def truncated_number_error() -> CellError:
    return CellError(
        _("Die Zahl wurde vom Tabellenprogramm gekürzt (z. B. 4,01E+12). Bitte die Spalte als Text formatieren.")
    )


def parse_int(value: str, low: int, high: int) -> int:
    text = value.replace(" ", "")
    if _scientific(text):
        raise truncated_number_error()
    if _THOUSANDS_RE.match(text):
        text = text.replace(".", "")
    if not re.fullmatch(r"\d+", text):
        raise CellError(_("„%(value)s“ ist keine ganze Zahl.") % {"value": value})
    number = int(text)
    if not low <= number <= high:
        raise CellError(_("Erlaubt sind %(min)s bis %(max)s.") % {"min": low, "max": high})
    return number


def parse_bool(value: str) -> bool:
    word = norm(value)
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise CellError(_("„%(value)s“ ist weder Ja noch Nein.") % {"value": value})


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_date(value: str, *, month_ok: bool = False, min_year: int = 2000, max_year: int = 2100) -> date:
    text = _TIME_SUFFIX_RE.sub("", value.strip())
    parsed = None
    try:
        if match := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
            parsed = date(int(match[1]), int(match[2]), int(match[3]))
        elif match := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})", text):
            year = int(match[3])
            parsed = date(year + 2000 if year < 100 else year, int(match[2]), int(match[1]))
        elif month_ok and (match := re.fullmatch(r"(\d{1,2})[./](\d{4})", text)):
            parsed = _last_day(int(match[2]), int(match[1]))
        elif month_ok and (match := re.fullmatch(r"(\d{4})-(\d{1,2})", text)):
            parsed = _last_day(int(match[1]), int(match[2]))
    except ValueError:
        parsed = None
    if parsed is None:
        if month_ok:
            raise CellError(
                _("„%(value)s“ ist kein gültiges Datum (TT.MM.JJJJ, JJJJ-MM-TT oder MM/JJJJ).") % {"value": value}
            )
        raise CellError(_("„%(value)s“ ist kein gültiges Datum (TT.MM.JJJJ oder JJJJ-MM-TT).") % {"value": value})
    if not min_year <= parsed.year <= max_year:
        raise CellError(_("Das Jahr muss zwischen %(min)s und %(max)s liegen.") % {"min": min_year, "max": max_year})
    return parsed


_CHOICE_CACHE: dict[tuple, dict[str, str]] = {}


def choice_lookup(choices, synonyms: dict | None = None) -> dict[str, str]:
    """Code und deutsche Bezeichnung (sowie die der aktiven Sprache) → Code."""
    cache_key = (choices, id(synonyms), translation.get_language())
    if cache_key in _CHOICE_CACHE:
        return _CHOICE_CACHE[cache_key]
    lookup = {}
    for code, label in choices.choices:
        lookup[norm(code)] = code
        lookup[norm(label)] = code
    with translation.override("de"):
        for code, label in choices.choices:
            lookup[norm(str(label))] = code
    for word, code in (synonyms or {}).items():
        lookup[norm(word)] = code
    _CHOICE_CACHE[cache_key] = lookup
    return lookup


def allowed_labels(choices) -> list[str]:
    with translation.override("de"):
        return [str(label) for _code, label in choices.choices]


def parse_choice(value: str, choices, synonyms: dict | None = None) -> str:
    code = choice_lookup(choices, synonyms).get(norm(value))
    if code is None:
        raise CellError(
            _("„%(value)s“ ist kein erlaubter Wert. Erlaubt: %(allowed)s.")
            % {"value": value, "allowed": ", ".join(allowed_labels(choices))}
        )
    return code


def parse_pzn(value: str) -> str:
    text = re.sub(r"^pzn[\s:\-]*", "", value.strip(), flags=re.IGNORECASE).replace(" ", "")
    if _scientific(text):
        raise truncated_number_error()
    if not text.isdigit():
        raise CellError(_("„%(value)s“ ist keine PZN (nur Ziffern).") % {"value": value})
    if len(text) > 8:
        raise CellError(_("Eine PZN hat höchstens 8 Ziffern."))
    pzn = text.zfill(8)
    remainder = sum(int(digit) * weight for digit, weight in zip(pzn[:7], range(1, 8), strict=True)) % 11
    if remainder == 10 or remainder != int(pzn[7]):
        raise CellError(_("„%(value)s“ ist ungültig (Prüfziffer).") % {"value": value})
    return pzn


def gtin_check_digit_ok(digits: str) -> bool:
    body = [int(char) for char in digits[:-1]]
    total = sum(digit * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == int(digits[-1])


def parse_gtin(value: str) -> str:
    text = value.replace(" ", "")
    if _scientific(text):
        raise truncated_number_error()
    if not text.isdigit() or len(text) not in (8, 12, 13, 14):
        raise CellError(_("Eine GTIN/EAN hat 8, 12, 13 oder 14 Ziffern."))
    if not gtin_check_digit_ok(text):
        raise CellError(_("„%(value)s“ ist ungültig (Prüfziffer).") % {"value": value})
    return text


class Cells:
    """Zugriff auf die Werte einer Zeile; Fehler landen mit Spaltenname im Ergebnis."""

    def __init__(self, kind: ImportKind, parsed: ParsedRow, result: RowResult):
        self.kind = kind
        self.values = parsed.values
        self.bad = parsed.bad
        self.result = result

    def header(self, key: str) -> str:
        return self.kind.column(key).header

    def fail(self, key: str, message) -> None:
        self.result.errors.append(f"{self.header(key)}: {message}")

    def note(self, key: str, message) -> None:
        self.result.notes.append(f"{self.header(key)}: {message}")

    def raw(self, key: str) -> str:
        return self.values.get(key, "")

    def has(self, key: str) -> bool:
        return bool(self.values.get(key)) and key not in self.bad

    def _get(self, key, parser, *, required=False, default=None):
        if key in self.bad:
            return default
        value = self.values.get(key, "")
        if not value:
            if required:
                self.fail(key, _("Pflichtfeld ist leer."))
            return default
        try:
            return parser(value)
        except CellError as exc:
            self.fail(key, exc)
            self.bad.add(key)
            return default

    def text(self, key, max_len, *, required=False, default=""):
        def parser(value):
            if len(value) > max_len:
                raise CellError(_("Höchstens %(max)s Zeichen.") % {"max": max_len})
            return value
        return self._get(key, parser, required=required, default=default)

    def integer(self, key, low, high, *, required=False, default=None):
        return self._get(key, lambda value: parse_int(value, low, high), required=required, default=default)

    def boolean(self, key, *, default):
        return self._get(key, parse_bool, default=default)

    def day(self, key, *, required=False, month_ok=False, min_year=2000, max_year=2100):
        return self._get(
            key, lambda value: parse_date(value, month_ok=month_ok, min_year=min_year, max_year=max_year),
            required=required,
        )

    def choice(self, key, choices, synonyms=None, *, required=False, default=None):
        return self._get(key, lambda value: parse_choice(value, choices, synonyms), required=required, default=default)

    def pzn(self, key):
        return self._get(key, parse_pzn, default="")

    def gtin(self, key):
        return self._get(key, parse_gtin, default="")


class SlugPool:
    """Eindeutige Slugs im Speicher statt einer Abfrage je Kandidat."""

    def __init__(self, taken, fallback: str):
        self.taken = set(taken)
        self.fallback = fallback

    def make(self, name: str) -> str:
        base = slugify(name)[:50] or self.fallback
        slug, counter = base, 1
        while slug in self.taken:
            slug = f"{base}-{counter}"
            counter += 1
        self.taken.add(slug)
        return slug


def _model_errors(instance, exclude, result: RowResult) -> None:
    try:
        instance.full_clean(exclude=exclude, validate_unique=False, validate_constraints=False)
    except ValidationError as exc:
        for name, messages in exc.message_dict.items():
            try:
                label = str(instance._meta.get_field(name).verbose_name)
            except Exception:
                label = name
            for message in messages:
                result.errors.append(f"{label}: {message}")


# --- Arten -----------------------------------------------------------------


class KindHandler:
    model = None

    def __init__(self, kind: ImportKind, *, station: Station, actor, digest: str):
        self.kind = kind
        self.station = station
        self.actor = actor
        self.digest = digest
        self.now = timezone.now()
        self.today = timezone.localdate()
        self.current_line = None

    @classmethod
    def existing_count(cls, station) -> int:
        return cls.model.objects.filter(station=station).count()

    def preload(self) -> None:
        pass

    def validate(self, cells: Cells, result: RowResult):
        raise NotImplementedError

    def finalize(self, entries) -> None:
        pass

    def apply(self, plan, result: RowResult) -> None:
        raise NotImplementedError

    def apply_all(self, entries) -> None:
        for result, plan in entries:
            if result.status == "new":
                self.current_line = result.line
                self.apply(plan, result)


class _LocationIndex:
    """Lagerorte der Wache mit vollem Pfad (Wurzel → … → Name)."""

    def __init__(self, station):
        self.objects = {loc.pk: loc for loc in StorageLocation.objects.filter(station=station).only(
            "id", "station", "name", "parent", "slug", "kind", "is_cold_storage", "description",
        ).order_by("pk")}
        self.paths: dict[int, tuple] = {}
        for pk in self.objects:
            self.paths[pk] = self._path(pk)
        self.by_path: dict[tuple, StorageLocation] = {}
        for pk, path in self.paths.items():
            self.by_path.setdefault(path, self.objects[pk])
        self.by_name: dict[str, list] = defaultdict(list)
        for loc in self.objects.values():
            self.by_name[norm(loc.name)].append(loc)

    def _path(self, pk) -> tuple:
        parts, seen, current = [], set(), self.objects.get(pk)
        while current is not None and current.pk not in seen:
            seen.add(current.pk)
            parts.append(norm(current.name))
            current = self.objects.get(current.parent_id)
        return tuple(reversed(parts))

    def display_path(self, loc) -> str:
        parts, seen, current = [], set(), loc
        while current is not None and current.pk not in seen:
            seen.add(current.pk)
            parts.append(current.name)
            current = self.objects.get(current.parent_id)
        return " → ".join(reversed(parts))

    def find(self, value: str):
        """(Lagerort, Fehlermeldung) für einen Namen oder Pfad „A → B“."""
        segments = path_segments(value)
        if any(not part for part in segments):
            return None, _("„%(value)s“ ist kein gültiger Pfad.") % {"value": value}
        wanted = tuple(norm(part) for part in segments)
        matches = [loc for loc in self.by_name.get(wanted[-1], []) if self.paths[loc.pk][-len(wanted):] == wanted]
        if not matches:
            return None, _("„%(value)s“ gibt es auf dieser Wache nicht. Bitte zuerst die Lagerorte importieren.") % {
                "value": value,
            }
        if len(matches) > 1:
            return None, _("„%(value)s“ ist mehrdeutig. Bitte als Pfad angeben, z. B. „%(example)s“.") % {
                "value": value, "example": self.display_path(matches[0]),
            }
        return matches[0], ""


class _Cycle(Exception):
    pass


class _Unresolved(Exception):
    pass


class StorageLocationHandler(KindHandler):
    model = StorageLocation
    KIND_SYNONYMS = {
        "hauptlager": "central", "zentrallager": "central", "apotheke": "central", "lager": "central",
        "fahrzeug": "vehicle", "rtw": "vehicle", "ktw": "vehicle", "nef": "vehicle",
        "koffer": "container", "rucksack": "container", "notfallkoffer": "container", "notfallrucksack": "container",
        "kühlschrank": "fridge", "kuehlschrank": "fridge", "medikamentenkühlschrank": "fridge",
        "sonstiges": "other", "sonstige": "other", "andere": "other",
    }

    def preload(self):
        self.index = _LocationIndex(self.station)
        self.slugs = SlugPool((loc.slug for loc in self.index.objects.values()), "loc")

    def validate(self, cells, result):
        name = cells.text("name", 120, required=True)
        if name and PATH_SEPARATOR_RE.search(name):
            cells.fail("name", _("Bitte ohne „→“ oder „>“ (Trennzeichen für Pfade)."))
        kind = cells.choice("kind", StorageLocation.Kind, self.KIND_SYNONYMS, default=StorageLocation.Kind.OTHER)
        cold = cells.boolean("cold", default=kind == StorageLocation.Kind.FRIDGE)
        parent = cells.text("parent", 400)
        ref = path_segments(parent) if parent else None
        if ref and any(not part for part in ref):
            cells.fail("parent", _("„%(value)s“ ist kein gültiger Pfad.") % {"value": parent})
            ref = None
        description = cells.text("description", 255)
        result.label = f"{parent} → {name}" if parent else name
        instance = StorageLocation(station=self.station, name=name, kind=kind, is_cold_storage=cold,
                                   description=description, slug="x")
        _model_errors(instance, ["station", "parent", "slug"], result)
        return {"name": name, "ref": ref, "instance": instance}

    def finalize(self, entries):
        nodes = [(result, plan) for result, plan in entries if plan and plan["name"]]
        by_name: dict[str, list[int]] = defaultdict(list)
        for position, (_result, plan) in enumerate(nodes):
            by_name[norm(plan["name"])].append(position)
        memo: dict[int, tuple] = {}
        parents: dict[int, tuple] = {}

        def path_of(position, visiting):
            if position in memo:
                return memo[position]
            if position in visiting:
                raise _Cycle
            visiting.add(position)
            try:
                plan = nodes[position][1]
                own = norm(plan["name"])
                if plan["ref"] is None:
                    path = (own,)
                else:
                    parent = resolve(plan["ref"], position, visiting)
                    parents[position] = parent
                    path = parent[2] + (own,)
            finally:
                visiting.discard(position)
            memo[position] = path
            return path

        def resolve(ref, position, visiting):
            wanted = tuple(norm(part) for part in ref)
            # Vorhandene Orte zählen einzeln (auch bei gleichem Pfad); eine Zeile
            # der Datei mit dem Pfad eines vorhandenen Orts ist derselbe Ort.
            candidates = [
                ("db", loc, self.index.paths[loc.pk]) for loc in self.index.by_name.get(wanted[-1], [])
                if self.index.paths[loc.pk][-len(wanted):] == wanted
            ]
            known_paths = {candidate[2] for candidate in candidates}
            self_only = True
            for other in by_name.get(wanted[-1], []):
                if other == position:
                    continue
                self_only = False
                try:
                    path = path_of(other, visiting)
                except _Unresolved:
                    continue  # Diese Zeile bekommt ihre eigene Meldung.
                if path[-len(wanted):] == wanted and path not in known_paths:
                    known_paths.add(path)
                    candidates.append(("file", other, path))
            if not candidates:
                if self_only and wanted[-1] == norm(nodes[position][1]["name"]) and len(wanted) == 1:
                    raise _Unresolved(_("Ein Lagerort kann nicht sich selbst übergeordnet sein."))
                raise _Unresolved(
                    _("„%(value)s“ gibt es weder auf dieser Wache noch in der Datei.") % {"value": " → ".join(ref)}
                )
            if len(candidates) > 1:
                raise _Unresolved(
                    _("„%(value)s“ ist mehrdeutig. Bitte als Pfad angeben, z. B. „A → B“.") % {"value": " → ".join(ref)}
                )
            return candidates[0]

        first_line: dict[tuple, int] = {}
        for position, (result, plan) in enumerate(nodes):
            try:
                path = path_of(position, set())
            except _Cycle:
                result.errors.append(
                    f"{self.kind.column('parent').header}: "
                    + _("Die Zuordnung der übergeordneten Lagerorte bildet einen Kreis.")
                )
                continue
            except _Unresolved as exc:
                result.errors.append(f"{self.kind.column('parent').header}: {exc}")
                continue
            plan["path"] = path
            plan["parent"] = parents.get(position)
            if path in first_line:
                result.errors.append(
                    f"{self.kind.column('name').header}: "
                    + _("Dieser Lagerort steht schon in Zeile %(line)s.") % {"line": first_line[path]}
                )
                continue
            first_line[path] = result.line
            if path in self.index.by_path:
                result.status = "skipped"
        self.created: dict[tuple, StorageLocation] = {}

    def apply_all(self, entries):
        new = [(result, plan) for result, plan in entries if result.status == "new"]
        for result, plan in sorted(new, key=lambda entry: len(entry[1]["path"])):
            self.current_line = result.line
            instance = plan["instance"]
            parent = plan["parent"]
            if parent is not None and parent[0] == "db":
                instance.parent = parent[1]
            elif parent is not None:
                instance.parent = self.index.by_path.get(parent[2]) or self.created[parent[2]]
            instance.slug = self.slugs.make(instance.name)
            instance.save()
            self.created[plan["path"]] = instance


class MedicalItemHandler(KindHandler):
    model = MedicalItem
    CATEGORY_SYNONYMS = {
        "medikament": "med", "medikamente": "med", "notfallmedikamente": "med", "ampullen": "med",
        "infusion": "infusion", "infusionen": "infusion", "infusionslösung": "infusion",
        "infusionslösungen": "infusion",
        "atemweg": "airway", "atemwege": "airway", "beatmung": "airway", "atemwegsmanagement": "airway",
        "diagnostik": "diag", "monitoring": "diag",
        "verband": "bandage", "verbandstoffe": "bandage", "verbandsmaterial": "bandage", "wundversorgung": "bandage",
        "hygiene": "hygiene", "desinfektion": "hygiene",
        "immobilisation": "immo", "rettung": "immo",
        "sonstiges": "other", "sonstige": "other", "material": "other",
    }
    UNIT_SYNONYMS = {
        "stk": "pcs", "stk.": "pcs", "st": "pcs", "st.": "pcs", "stück": "pcs", "stueck": "pcs",
        "ampulle": "amp", "ampullen": "amp", "amp.": "amp",
        "packung": "pack", "packungen": "pack", "pck": "pack", "pkg": "pack", "pack.": "pack",
        "flasche": "btl", "flaschen": "btl", "fl": "btl", "fl.": "btl",
        "rolle": "roll", "rollen": "roll",
        "kanister": "can", "dose": "can", "dosen": "can",
    }

    def preload(self):
        items = list(MedicalItem.objects.filter(station=self.station).only("id", "name", "pzn", "gtin", "slug"))
        self.by_pzn, self.by_gtin = {}, {}
        self.by_name_without_code: dict[str, MedicalItem] = {}
        self.by_name: dict[str, MedicalItem] = {}
        for item in items:
            pzn, gtin = digits_key(item.pzn, 8), digits_key(item.gtin, 14)
            if pzn:
                self.by_pzn.setdefault(pzn, item)
            if gtin:
                self.by_gtin.setdefault(gtin, item)
            self.by_name.setdefault(norm(item.name), item)
            if not pzn and not gtin:
                self.by_name_without_code.setdefault(norm(item.name), item)
        self.slugs = SlugPool((item.slug for item in items), "item")
        self.seen: dict[tuple, tuple] = {}
        self.seen_names: dict[str, tuple] = {}

    def validate(self, cells, result):
        name = cells.text("name", 160, required=True)
        category = cells.choice("category", MedicalItem.Category, self.CATEGORY_SYNONYMS,
                                default=MedicalItem.Category.OTHER)
        unit = cells.choice("unit", MedicalItem.Unit, self.UNIT_SYNONYMS, default=MedicalItem.Unit.PIECE)
        pzn = cells.pzn("pzn")
        gtin = cells.gtin("gtin")
        min_stock = cells.integer("min_stock", 0, 100_000, default=0)
        target_stock = cells.integer("target_stock", 0, 100_000, default=min_stock)
        if target_stock < min_stock:
            cells.note("target_stock", _("liegt unter dem Mindestbestand."))
        cooling = cells.boolean("cooling", default=False)
        room_days = cells.integer("room_days", 1, 3650)
        if room_days and not cooling:
            cells.note("room_days", _("gilt nur für kühlpflichtige Artikel und wird nicht übernommen."))
            room_days = None
        result.label = name
        instance = MedicalItem(
            station=self.station, slug="x", name=name, category=category, unit=unit, pzn=pzn, gtin=gtin,
            min_stock=min_stock, target_stock=target_stock, requires_cooling=cooling, room_temp_max_days=room_days,
        )
        _model_errors(instance, ["station", "slug"], result)
        if not name or result.errors:
            return {"instance": instance}

        gtin_key = digits_key(gtin, 14)
        signature = (norm(name), category, unit, pzn, gtin_key, min_stock, target_stock, cooling, room_days)
        keys = [("pzn", pzn)] if pzn else []
        if gtin_key:
            keys.append(("gtin", gtin_key))
        if not keys:
            keys.append(("name", norm(name)))
        for key in keys:
            if key in self.seen:
                line, other = self.seen[key]
                if other == signature:
                    result.status = "skipped"
                    result.notes.append(_("Gleich wie Zeile %(line)s.") % {"line": line})
                else:
                    result.errors.append(
                        _("Widerspricht Zeile %(line)s (gleiche PZN, GTIN oder Bezeichnung, andere Angaben).")
                        % {"line": line}
                    )
                return {"instance": instance}
        for key in keys:
            self.seen[key] = (result.line, signature)
        earlier = self.seen_names.get(norm(name))
        if earlier and earlier[1] != pzn:
            cells.note("name", _("Gleicher Name wie Zeile %(line)s, aber andere PZN.") % {"line": earlier[0]})
        self.seen_names.setdefault(norm(name), (result.line, pzn))

        if pzn and pzn in self.by_pzn or gtin_key and gtin_key in self.by_gtin:
            result.status = "skipped"
        elif (pzn or gtin_key) and norm(name) in self.by_name_without_code:
            result.status = "skipped"
            result.notes.append(
                _("Ein Artikel gleichen Namens ohne PZN/GTIN ist vorhanden. PZN bzw. GTIN bitte dort ergänzen.")
            )
        elif not pzn and not gtin_key and norm(name) in self.by_name:
            result.status = "skipped"
        return {"instance": instance}

    def apply(self, plan, result):
        instance = plan["instance"]
        instance.slug = self.slugs.make(instance.name)
        instance.save()


class StockHandler(KindHandler):
    model = StockItem

    def preload(self):
        items = list(MedicalItem.objects.filter(station=self.station).only(
            "id", "station", "name", "pzn", "gtin", "unit", "requires_cooling", "room_temp_max_days",
        ))
        self.by_pzn, self.by_gtin = {}, {}
        self.by_name: dict[str, list] = defaultdict(list)
        for item in items:
            if key := digits_key(item.pzn, 8):
                self.by_pzn.setdefault(key, item)
            if key := digits_key(item.gtin, 14):
                self.by_gtin.setdefault(key, item)
            self.by_name[norm(item.name)].append(item)
        self.locations = _LocationIndex(self.station)
        self.batches = {
            (batch.item_id, batch.batch_number): batch
            for batch in ItemBatch.objects.filter(station=self.station).only(
                "id", "item_id", "batch_number", "manufacturer_exp_date", "out_of_fridge_date", "is_recalled",
            )
        }
        self.stock_pairs = set(
            StockItem.objects.filter(station=self.station).values_list("batch_id", "location_id")
        )
        self.seen_rows: dict[tuple, int] = {}
        self.seen_batches: dict[tuple, tuple] = {}
        self.new_batches: dict[tuple, ItemBatch] = {}
        self.note_text = f"CSV-Import {self.digest[:12]}"

    def _item(self, cells):
        pzn = cells.pzn("pzn")
        gtin_key = digits_key(cells.gtin("gtin"), 14)
        name = cells.text("item", 160)
        if "pzn" in cells.bad or "gtin" in cells.bad:
            return None
        if pzn:
            item = self.by_pzn.get(pzn)
            if item is None:
                cells.fail("pzn", _("Kein Artikel mit dieser PZN. Bitte zuerst die Artikel importieren."))
            return item
        if gtin_key:
            item = self.by_gtin.get(gtin_key)
            if item is None:
                cells.fail("gtin", _("Kein Artikel mit dieser GTIN. Bitte zuerst die Artikel importieren."))
            return item
        if name:
            matches = self.by_name.get(norm(name), [])
            if len(matches) == 1:
                return matches[0]
            if matches:
                cells.fail("item", _("Mehrere Artikel heißen so. Bitte die PZN oder GTIN angeben."))
            else:
                cells.fail("item", _("Kein Artikel mit dieser Bezeichnung. Bitte zuerst die Artikel importieren."))
            return None
        cells.result.errors.append(_("Artikel, PZN oder GTIN fehlt."))
        return None

    def validate(self, cells, result):
        item = self._item(cells)
        lot = cells.text("lot", 60, required=True)
        mhd = cells.day("mhd", required=True, month_ok=True)
        oof = cells.day("oof")
        location = None
        if cells.has("location"):
            location, problem = self.locations.find(cells.raw("location"))
            if problem:
                cells.fail("location", problem)
        elif "location" not in cells.bad:
            cells.fail("location", _("Pflichtfeld ist leer."))
        quantity = cells.integer("quantity", 0, 100_000, required=True)
        status = cells.raw("status")
        if status and norm(status).startswith("gesperrt"):
            cells.fail("status", _("Gesperrte Chargen werden nicht übernommen."))
        result.label = " · ".join(part for part in (
            item.name if item else cells.raw("item") or cells.raw("pzn") or cells.raw("gtin"),
            lot,
            self.locations.display_path(location) if location else cells.raw("location"),
        ) if part)

        if mhd and mhd < self.today:
            cells.note("mhd", _("liegt in der Vergangenheit."))
        if item is not None and cells.has("unit"):
            try:
                unit = parse_choice(cells.raw("unit"), MedicalItem.Unit, MedicalItemHandler.UNIT_SYNONYMS)
            except CellError:
                unit = None
            if unit != item.unit:
                cells.note("unit", _("weicht vom Artikel ab (dort: %(unit)s).") % {"unit": item.get_unit_display()})
        if item is not None and oof and not item.requires_cooling:
            cells.note("oof", _("Der Artikel ist nicht kühlpflichtig; das Datum wird nicht übernommen."))
            oof = None
        if item is None or location is None or not lot or mhd is None or quantity is None or result.errors:
            return None

        batch_key = (item.pk, lot)
        existing = self.batches.get(batch_key)
        if existing is not None:
            if existing.is_recalled:
                cells.fail("lot", _("Diese Charge ist gesperrt (Rückruf)."))
                return None
            if existing.manufacturer_exp_date != mhd:
                cells.fail("mhd", _("Die Charge ist mit einem anderen MHD (%(date)s) vorhanden.") % {
                    "date": existing.manufacturer_exp_date.strftime("%d.%m.%Y"),
                })
                return None
            if oof and existing.out_of_fridge_date != oof:
                cells.note("oof", _("Die Charge ist vorhanden; ihr Datum bleibt unverändert."))
        row_key = (item.pk, lot, location.pk)
        if row_key in self.seen_rows:
            result.errors.append(
                _("Artikel, Charge und Lagerort stehen schon in Zeile %(line)s.") % {"line": self.seen_rows[row_key]}
            )
            return None
        self.seen_rows[row_key] = result.line
        earlier = self.seen_batches.get(batch_key)
        if earlier is not None and earlier[1:] != (mhd, oof):
            result.errors.append(
                _("Dieselbe Charge hat in Zeile %(line)s ein anderes MHD oder Out-of-Fridge-Datum.") % {"line": earlier[0]}
            )
            return None
        self.seen_batches.setdefault(batch_key, (result.line, mhd, oof))

        if quantity == 0:
            result.status = "skipped"
            cells.note("quantity", _("Bestand 0 wird nicht übernommen."))
        elif existing is not None and (existing.pk, location.pk) in self.stock_pairs:
            result.status = "skipped"
        if item.requires_cooling and not location.is_cold_storage and not oof and result.status == "new":
            result.notes.append(
                _("Kühlpflichtiger Artikel außerhalb der Kühlung ohne Out-of-Fridge-Datum. Bitte prüfen.")
            )
        return {"item": item, "lot": lot, "mhd": mhd, "oof": oof, "location": location, "quantity": quantity}

    def apply(self, plan, result):
        item, location = plan["item"], plan["location"]
        batch_key = (item.pk, plan["lot"])
        batch = self.batches.get(batch_key) or self.new_batches.get(batch_key)
        if batch is None:
            batch = ItemBatch(
                item=item, station=self.station, batch_number=plan["lot"],
                manufacturer_exp_date=plan["mhd"], out_of_fridge_date=plan["oof"],
            )
            batch.save()
            self.new_batches[batch_key] = batch
        StockItem(station=self.station, item=item, batch_id=batch.pk, location=location,
                  quantity=plan["quantity"]).save()
        StockMovement(
            station=self.station, item=item, batch_id=batch.pk, source_location=None, target_location=location,
            quantity=plan["quantity"], kind=StockMovement.Kind.LEGACY_IMPORT, actor=self.actor, note=self.note_text,
        ).save()


class MedicalDeviceHandler(KindHandler):
    model = MedicalDevice
    CATEGORY_SYNONYMS = {
        "defibrillator": "defi", "defi": "defi", "monitor": "defi", "ekg-monitor": "defi",
        "beatmung": "vent", "beatmungsgerät": "vent", "beatmungsgeraet": "vent", "ventilator": "vent",
        "absaugung": "suction", "absauggerät": "suction", "absaugpumpe": "suction",
        "spritzenpumpe": "perfusor", "perfusor": "perfusor", "infusionspumpe": "perfusor",
        "diagnostik": "diag", "ekg": "diag", "pulsoxymeter": "diag",
        "reanimationshilfe": "cpr", "thoraxkompression": "cpr", "cpr": "cpr",
        "sonstiges": "other", "sonstige": "other",
    }
    RISK_SYNONYMS = {"1": "I", "2a": "IIa", "2b": "IIb", "3": "III", "klasse 2a": "IIa", "klasse 2b": "IIb"}
    STATUS_SYNONYMS = {
        "einsatzbereit": "ready", "ok": "ready", "in ordnung": "ready",
        "gesperrt": "oob", "außer betrieb": "oob", "defekt": "oob",
        "wartung": "maintenance", "in wartung": "maintenance",
        "ausgemustert": "decommissioned", "außer betrieb genommen": "decommissioned",
    }

    def preload(self):
        devices = list(MedicalDevice.objects.filter(station=self.station).only(
            "id", "slug", "inventory_number", "serial_number", "manufacturer",
        ))
        self.by_inventory = {norm(d.inventory_number): d for d in devices if d.inventory_number.strip()}
        self.by_serial = {
            (norm(d.serial_number), norm(d.manufacturer)): d for d in devices if d.serial_number.strip()
        }
        asset_ids = StationAsset.objects.filter(
            station=self.station, kind=StationAsset.Kind.DEVICE,
        ).values_list("asset_id", flat=True)
        self.slugs = SlugPool([*(d.slug for d in devices), *asset_ids], "device")
        self.seen_inventory: dict[str, int] = {}
        self.seen_serial: dict[tuple, int] = {}

    def _status(self, cells, result) -> bool:
        """False, wenn die Zeile wegen des Status übersprungen wird."""
        if not cells.has("status"):
            return True
        code = choice_lookup(MedicalDevice.Status, self.STATUS_SYNONYMS).get(norm(cells.raw("status")))
        if code is None:
            cells.fail("status", _("„%(value)s“ ist kein bekannter Gerätestatus. Erlaubt: %(allowed)s.") % {
                "value": cells.raw("status"), "allowed": ", ".join(allowed_labels(MedicalDevice.Status)),
            })
        elif code in (MedicalDevice.Status.OOB, MedicalDevice.Status.MAINTENANCE):
            cells.fail("status", _("Das Gerät ist laut Datei nicht einsatzklar. Bitte die Zeile entfernen, das Gerät "
                                   "einzeln anlegen und über „Mangel melden“ sperren."))
        elif code == MedicalDevice.Status.DECOMMISSIONED:
            result.status = "skipped"
            cells.note("status", _("Ausgemusterte Geräte werden nicht übernommen."))
            return False
        elif code == MedicalDevice.Status.LIMITED:
            cells.note("status", _("Laut Datei eingeschränkt. Der Status wird nicht übernommen; "
                                   "nach dem Import bitte prüfen und bei Bedarf einen Mangel melden."))
        return True

    def validate(self, cells, result):
        name = cells.text("name", 160, required=True)
        category = cells.choice("category", MedicalDevice.Category, self.CATEGORY_SYNONYMS,
                                default=MedicalDevice.Category.OTHER)
        risk = cells.choice("risk_class", MedicalDevice.RiskClass, self.RISK_SYNONYMS, required=True)
        manufacturer = cells.text("manufacturer", 120)
        model_type = cells.text("model_type", 120)
        serial = cells.text("serial", 120)
        inventory = cells.text("inventory", 60)
        if not serial and not inventory and not {"serial", "inventory"} & cells.bad:
            result.errors.append(_("Seriennummer oder Inventarnummer fehlt (§ 14 MPBetreibV)."))
        udi = cells.text("udi", 80)
        ce = cells.text("ce", 10)
        if ce.isdigit() and len(ce) < 4:
            ce = ce.zfill(4)
        year = cells.integer("year", 1950, self.today.year + 1)
        acquired = cells.day("acquired", min_year=1950, max_year=self.today.year)
        if acquired and acquired > self.today:
            cells.fail("acquired", _("liegt in der Zukunft."))
        location = cells.text("location", 120) or "Wache"
        anlage_1 = cells.boolean("anlage_1", default=True)
        anlage_2 = cells.boolean("anlage_2", default=False)
        stk_interval = cells.integer("stk_interval", 1, 120, default=24)
        mtk_interval = cells.integer("mtk_interval", 1, 120)
        if anlage_2 and not mtk_interval and "mtk_interval" not in cells.bad:
            cells.fail("mtk_interval", _("Bei Anlage 2 (MTK) bitte das MTK-Intervall angeben."))
        dguv_interval = cells.integer("dguv_interval", 1, 120, default=12)
        next_stk = cells.day("next_stk", month_ok=True)
        next_mtk = cells.day("next_mtk", month_ok=True)
        next_dguv = cells.day("next_dguv", month_ok=True)
        for key, value in (("next_stk", next_stk), ("next_mtk", next_mtk), ("next_dguv", next_dguv)):
            if value and value < self.today:
                cells.note(key, _("liegt in der Vergangenheit. Die Prüfung ist überfällig."))
        if anlage_1 and not next_stk and "next_stk" not in cells.bad:
            cells.note("next_stk", _("fehlt, obwohl das Gerät unter Anlage 1 fällt."))
        if next_mtk and not anlage_2:
            cells.note("next_mtk", _("ist angegeben, aber Anlage 2 (MTK) steht auf Nein."))
        result.label = " · ".join(part for part in (name, inventory or serial) if part)
        importable = self._status(cells, result)

        instance = MedicalDevice(
            station=self.station, slug="x", name=name, category=category, risk_class=risk or "",
            manufacturer=manufacturer, model_type=model_type, serial_number=serial, inventory_number=inventory,
            udi_di=udi, ce_notified_body=ce, year_of_manufacture=year, acquired_at=acquired, location=location,
            current_status=MedicalDevice.Status.READY, is_anlage_1=anlage_1, is_anlage_2=anlage_2,
            stk_interval_months=stk_interval, mtk_interval_months=mtk_interval, dguv_interval_months=dguv_interval,
            next_stk_date=next_stk, next_mtk_date=next_mtk, next_dguv_date=next_dguv, legacy_imported_at=self.now,
        )
        if risk:
            _model_errors(instance, ["station", "slug"], result)
        if not importable or result.errors:
            return {"instance": instance}

        inventory_key = norm(inventory) if inventory else ""
        serial_key = (norm(serial), norm(manufacturer)) if serial else None
        if inventory_key and inventory_key in self.seen_inventory:
            result.errors.append(_("Gleiche Inventarnummer wie Zeile %(line)s.") % {
                "line": self.seen_inventory[inventory_key],
            })
            return {"instance": instance}
        if serial_key and serial_key in self.seen_serial:
            result.errors.append(_("Gleiche Seriennummer und gleicher Hersteller wie Zeile %(line)s.") % {
                "line": self.seen_serial[serial_key],
            })
            return {"instance": instance}
        if inventory_key:
            self.seen_inventory[inventory_key] = result.line
        if serial_key:
            self.seen_serial[serial_key] = result.line
        if inventory_key in self.by_inventory or serial_key in self.by_serial:
            result.status = "skipped"
        return {"instance": instance}

    def apply(self, plan, result):
        instance = plan["instance"]
        instance.slug = self.slugs.make(instance.name)
        instance.save()


# --- Registry --------------------------------------------------------------

STOCK_HINT = gettext_lazy("Bestand bitte über „Bestand (Altbestand)“ übernehmen.")
FREE_TEXT_HINT = gettext_lazy("Freitext wird nicht übernommen.")
LAST_CHECK_HINT = gettext_lazy("Bitte „Nächste …“ von der Prüfplakette übernehmen.")


def _device_allowed(choices):
    return lambda: allowed_labels(choices)


KINDS = {
    "lagerorte": ImportKind(
        slug="lagerorte",
        title=gettext_lazy("Lagerorte"),
        description=gettext_lazy(
            "Lager, Fahrzeugschränke, Koffer und Kühlschränke. Untergeordnete Orte über die Spalte "
            "„Übergeordneter Lagerort“."
        ),
        module_flag="warehouse_enabled",
        audit_action="import.storage_locations",
        handler_cls=StorageLocationHandler,
        columns=(
            Column("Lagerort", "name", gettext_lazy("Bezeichnung des Lagerorts, z. B. „Fach 3“."), required=True,
                   aliases=("Lagerort-Bezeichnung", "Bezeichnung")),
            Column("Art", "kind", gettext_lazy("Art des Lagerorts. Leer: Sonstiger Lagerort."),
                   allowed=lambda: allowed_labels(StorageLocation.Kind)),
            Column("Kühlung", "cold", gettext_lazy("Ja, wenn der Ort gekühlt ist. Leer: Ja nur beim Kühlschrank."),
                   aliases=("Kühlpflichtig", "Kühlschrank", "Kühlpflichtiger Lagerort"),
                   allowed=lambda: ["Ja", "Nein"]),
            Column("Übergeordneter Lagerort", "parent",
                   gettext_lazy("Name oder Pfad eines vorhandenen Lagerorts oder einer Zeile dieser Datei, "
                                "z. B. „RTW 1 → Schrank links“. Leer: oberste Ebene."),
                   aliases=("Übergeordnet",)),
            Column("Beschreibung", "description", gettext_lazy("Kurze Beschreibung, höchstens 255 Zeichen.")),
        ),
        not_imported_text=gettext_lazy(
            "Vorhandene Lagerorte (gleicher Pfad) werden übersprungen und nicht geändert. Lagerorte lassen sich "
            "nach dem Import nicht bearbeiten oder löschen; die Datei deshalb vorher genau prüfen."
        ),
        example_row=(("name", "# Beispiel: Fach 3"), ("kind", "Koffer / Rucksack"), ("cold", "Nein"),
                     ("parent", "RTW 1"), ("description", "Schrank links")),
        next_url_name="warehouse_dashboard",
        next_label=gettext_lazy("Zum Lager"),
    ),
    "artikel": ImportKind(
        slug="artikel",
        title=gettext_lazy("Artikel"),
        description=gettext_lazy("Artikelstamm für Medikamente und Material: PZN, GTIN, Einheit, Mindest- und Sollbestand."),
        module_flag="warehouse_enabled",
        audit_action="import.articles",
        handler_cls=MedicalItemHandler,
        columns=(
            Column("Artikel", "name", gettext_lazy("Bezeichnung des Artikels."), required=True,
                   aliases=("Artikelbezeichnung", "Bezeichnung")),
            Column("Kategorie", "category", gettext_lazy("Leer: Sonstiges Material."),
                   allowed=lambda: allowed_labels(MedicalItem.Category)),
            Column("Einheit", "unit", gettext_lazy("Leer: Stück. Auch „Stk“, „Amp“ oder „Pck“."),
                   allowed=lambda: allowed_labels(MedicalItem.Unit)),
            Column("PZN", "pzn", gettext_lazy("Pharmazentralnummer; fehlende führende Nullen werden ergänzt."),
                   aliases=("PZN (Pharmazentralnummer)",)),
            Column("GTIN", "gtin", gettext_lazy("GTIN/EAN mit 8, 12, 13 oder 14 Ziffern."),
                   aliases=("GTIN / EAN", "EAN")),
            Column("Mindestbestand", "min_stock", gettext_lazy("Ganze Zahl. Leer: 0."),
                   aliases=("Mindestbestand Wache",)),
            Column("Sollbestand", "target_stock", gettext_lazy("Ganze Zahl. Leer: wie Mindestbestand."),
                   aliases=("Sollbestand Wache",)),
            Column("Kühlpflichtig", "cooling", gettext_lazy("Ja für 2–8 °C. Leer: Nein."),
                   aliases=("Kühlpflichtig (2–8 °C)", "Kühlung"), allowed=lambda: ["Ja", "Nein"]),
            Column("Max. Tage bei Raumtemperatur", "room_days",
                   gettext_lazy("Nur bei kühlpflichtigen Artikeln: Haltbarkeit ungekühlt in Tagen.")),
        ),
        ignored_headers=(
            ("Charge (Lot)", STOCK_HINT), ("Hersteller-MHD", STOCK_HINT), ("Out-of-Fridge Datum", STOCK_HINT),
            ("Effektives MHD (FEFO)", STOCK_HINT), ("Lagerort", STOCK_HINT), ("Bestand", STOCK_HINT),
            ("Status / Rückruf", STOCK_HINT), ("Bestellmenge", STOCK_HINT), ("Ist-Bestand", STOCK_HINT),
            ("Dosierung / Lagerhinweise", FREE_TEXT_HINT), ("Notizen", FREE_TEXT_HINT),
            ("Hinweise", FREE_TEXT_HINT), ("Bemerkung", FREE_TEXT_HINT),
        ),
        not_imported_text=gettext_lazy(
            "Vorhandene Artikel (gleiche PZN, GTIN oder Bezeichnung) werden übersprungen und nicht geändert. "
            "Hinweise und Dosierungstexte werden nicht übernommen. Bestände kommen über „Bestand (Altbestand)“."
        ),
        example_row=(("name", "# Beispiel: Einmalhandschuhe Gr. M"), ("category", "Hygiene & Desinfektion"),
                     ("unit", "Packung(en)"), ("min_stock", "2"), ("target_stock", "4"), ("cooling", "Nein")),
        next_url_name="warehouse_dashboard",
        next_label=gettext_lazy("Zum Lager"),
    ),
    "bestand": ImportKind(
        slug="bestand",
        title=gettext_lazy("Bestand (Altbestand)"),
        description=gettext_lazy(
            "Vorhandene Chargen je Lagerort, gebucht als „Übernahme Altbestand“. Artikel und Lagerorte müssen "
            "schon angelegt sein. Betäubungsmittel gehören nicht hierher; ihr Bestand bleibt im BtM-Buch."
        ),
        module_flag="warehouse_enabled",
        audit_action="import.stock",
        handler_cls=StockHandler,
        columns=(
            Column("Artikel", "item", gettext_lazy("Bezeichnung eines vorhandenen Artikels (oder PZN/GTIN)."),
                   aliases=("Artikelbezeichnung",)),
            Column("PZN", "pzn", gettext_lazy("PZN eines vorhandenen Artikels; hat Vorrang vor der Bezeichnung.")),
            Column("GTIN", "gtin", gettext_lazy("GTIN eines vorhandenen Artikels."), aliases=("GTIN / EAN", "EAN")),
            Column("Charge (Lot)", "lot", gettext_lazy("Chargennummer wie auf der Packung."), required=True,
                   aliases=("Charge", "Lot", "Chargennummer", "Chargennummer (Lot)")),
            Column("Hersteller-MHD", "mhd", gettext_lazy("Aufgedrucktes MHD; „05/2027“ gilt als Monatsende."),
                   required=True, aliases=("MHD", "Verfall", "Verfallsdatum", "Hersteller-MHD (aufgedruckt)")),
            Column("Out-of-Fridge Datum", "oof",
                   gettext_lazy("Nur bei kühlpflichtigen Artikeln: Tag, an dem die Kühlung endete."),
                   aliases=("Datum der Kühlkettenunterbrechung",)),
            Column("Lagerort", "location", gettext_lazy("Name oder Pfad eines vorhandenen Lagerorts, z. B. „RTW 1 → Fach 3“."),
                   required=True),
            Column("Bestand", "quantity", gettext_lazy("Menge an diesem Lagerort. 0 wird übersprungen."),
                   required=True, aliases=("Menge",)),
            Column("Einheit", "unit", gettext_lazy("Nur zum Abgleich mit dem Artikel.")),
            Column("Status / Rückruf", "status", gettext_lazy("Gesperrte Chargen werden nicht übernommen."),
                   aliases=("Status",)),
        ),
        ignored_headers=(
            ("Kategorie", gettext_lazy("kommt aus dem Artikel")),
            ("Effektives MHD (FEFO)", gettext_lazy("wird berechnet")),
        ),
        require_one_of=(("item", "pzn", "gtin"),),
        not_imported_text=gettext_lazy(
            "Vorhandene Bestände (gleiche Charge am gleichen Lagerort) werden übersprungen und nicht geändert. "
            "Gesperrte Chargen und Betäubungsmittel werden nicht übernommen."
        ),
        example_row=(("item", "# Beispiel: Einmalhandschuhe Gr. M"), ("lot", "L2401"), ("mhd", "05/2028"),
                     ("location", "RTW 1 → Fach 3"), ("quantity", "3"), ("unit", "Packung(en)")),
        next_url_name="warehouse_dashboard",
        next_label=gettext_lazy("Zum Lager"),
    ),
    "medizingeraete": ImportKind(
        slug="medizingeraete",
        title=gettext_lazy("Medizingeräte"),
        description=gettext_lazy(
            "Bestandsverzeichnis nach § 14 MPBetreibV mit Prüffristen. Importierte Geräte sind als Altbestand "
            "gekennzeichnet, bis die erste Prüfung in Wachwerk eingetragen ist."
        ),
        module_flag="mpg_enabled",
        audit_action="import.medical_devices",
        handler_cls=MedicalDeviceHandler,
        columns=(
            Column("Gerätebezeichnung", "name", gettext_lazy("Bezeichnung des Geräts."), required=True,
                   aliases=("Bezeichnung", "Gerät")),
            Column("Kategorie", "category", gettext_lazy("Leer: Sonstiges aktives Medizinprodukt."),
                   aliases=("Gerätekategorie",), allowed=_device_allowed(MedicalDevice.Category)),
            Column("Risikoklasse", "risk_class", gettext_lazy("Pflicht: I, IIa, IIb oder III."), required=True,
                   allowed=_device_allowed(MedicalDevice.RiskClass)),
            Column("Hersteller", "manufacturer", gettext_lazy("Höchstens 120 Zeichen.")),
            Column("Typ / Modell", "model_type", gettext_lazy("Höchstens 120 Zeichen."),
                   aliases=("Typ", "Modell", "Modell / Typ")),
            Column("Seriennummer", "serial", gettext_lazy("Seriennummer oder Inventarnummer ist Pflicht.")),
            Column("Inventarnummer", "inventory", gettext_lazy("Seriennummer oder Inventarnummer ist Pflicht."),
                   aliases=("Inventarnummer / Barcode",)),
            Column("UDI-DI (GTIN)", "udi", gettext_lazy("Höchstens 80 Zeichen."), aliases=("UDI-DI", "UDI")),
            Column("CE-Kennnummer", "ce", gettext_lazy("Kennnummer der benannten Stelle, z. B. 0123.")),
            Column("Baujahr", "year", gettext_lazy("Vierstellige Jahreszahl.")),
            Column("Anschaffungsdatum", "acquired", gettext_lazy("Datum, nicht in der Zukunft.")),
            Column("Standort / Fahrzeug", "location", gettext_lazy("Leer: Wache."), aliases=("Standort",)),
            Column("Anlage 1 (STK)", "anlage_1", gettext_lazy("STK-Pflicht. Leer: Ja."),
                   aliases=("Anlage 1",), allowed=lambda: ["Ja", "Nein"]),
            Column("Anlage 2 (MTK)", "anlage_2", gettext_lazy("MTK-Pflicht. Leer: Nein."),
                   aliases=("Anlage 2",), allowed=lambda: ["Ja", "Nein"]),
            Column("STK-Intervall (M)", "stk_interval", gettext_lazy("Monate, 1 bis 120. Leer: 24."),
                   aliases=("STK-Intervall", "STK-Intervall (Monate)")),
            Column("MTK-Intervall (M)", "mtk_interval", gettext_lazy("Monate, 1 bis 120. Pflicht bei Anlage 2."),
                   aliases=("MTK-Intervall", "MTK-Intervall (Monate)")),
            Column("DGUV-Intervall (M)", "dguv_interval", gettext_lazy("Monate, 1 bis 120. Leer: 12."),
                   aliases=("DGUV-Intervall", "DGUV V3 Intervall (Monate)")),
            Column("Nächste STK", "next_stk", gettext_lazy("Datum von der Prüfplakette; „06/2027“ gilt als Monatsende.")),
            Column("Nächste MTK", "next_mtk", gettext_lazy("Datum von der Prüfplakette; „06/2027“ gilt als Monatsende.")),
            Column("Nächste DGUV V3", "next_dguv",
                   gettext_lazy("Datum von der Prüfplakette; „06/2027“ gilt als Monatsende."),
                   aliases=("Nächste DGUV",)),
            Column("Status", "status",
                   gettext_lazy("Wird nicht übernommen. Gesperrte Geräte oder Geräte in Wartung verhindern den "
                                "Import; ausgemusterte Geräte werden übersprungen."),
                   aliases=("Betriebsstatus",), allowed=_device_allowed(MedicalDevice.Status)),
        ),
        ignored_headers=(
            ("Letzte Funktionskontrolle", gettext_lazy("Funktionskontrollen werden nicht übernommen.")),
            ("Letzter Funktionscheck", gettext_lazy("Funktionskontrollen werden nicht übernommen.")),
            ("Aus Altbestand übernommen am", gettext_lazy("wird beim Import neu gesetzt")),
            ("Letzte STK", LAST_CHECK_HINT), ("Letzte MTK", LAST_CHECK_HINT), ("Letzte DGUV", LAST_CHECK_HINT),
            ("Letzte DGUV V3", LAST_CHECK_HINT),
            ("Außerbetriebnahme", gettext_lazy("wird nicht übernommen")),
            ("Hinweise", FREE_TEXT_HINT), ("Notizen", FREE_TEXT_HINT), ("Bemerkung", FREE_TEXT_HINT),
            ("Status-Bemerkung", FREE_TEXT_HINT), ("Hinweise / Medizinproduktebuch-Notizen", FREE_TEXT_HINT),
            ("Online-Bedienungsanleitung", gettext_lazy("wird nicht übernommen")),
        ),
        not_imported_text=gettext_lazy(
            "Vorhandene Geräte (gleiche Inventarnummer oder gleiche Seriennummer beim gleichen Hersteller) werden "
            "übersprungen und nicht geändert. Status, Funktionskontrollen, Prüfprotokolle, Einweisungen und "
            "Notizen werden nicht übernommen; es entstehen keine rückdatierten Einträge im Medizinproduktebuch."
        ),
        example_row=(("name", "# Beispiel: Absaugpumpe"), ("category", "Absaugpumpe"), ("risk_class", "IIa"),
                     ("manufacturer", "Hersteller GmbH"), ("serial", "SN-0001"), ("inventory", "INV-0001"),
                     ("location", "RTW 1"), ("anlage_1", "Ja"), ("anlage_2", "Nein"), ("stk_interval", "24"),
                     ("dguv_interval", "12"), ("next_stk", "06/2027"), ("next_dguv", "06/2027")),
        next_url_name="mpg_dashboard",
        next_label=gettext_lazy("Zu den Medizingeräten"),
    ),
}


def available_kinds(station) -> list[ImportKind]:
    return [kind for kind in KINDS.values() if not kind.module_flag or getattr(station, kind.module_flag, False)]


def get_kind(slug: str, station) -> ImportKind | None:
    kind = KINDS.get(slug)
    if kind is None or (kind.module_flag and not getattr(station, kind.module_flag, False)):
        return None
    return kind


def next_kind(kind: ImportKind, station) -> ImportKind | None:
    kinds = available_kinds(station)
    for position, candidate in enumerate(kinds):
        if candidate.slug == kind.slug and position + 1 < len(kinds):
            return kinds[position + 1]
    return None


# --- Import ----------------------------------------------------------------


def run_import(
    kind: ImportKind, *, station: Station, actor, raw: bytes, commit: bool, expected_plan: str | None = None,
) -> ImportReport:
    """Prüft und importiert eine Datei; ohne ``commit`` wird alles zurückgerollt.

    ``expected_plan`` ist der ``plan_digest`` der bestätigten Vorschau. Weicht das
    Ergebnis beim Bestätigen davon ab (jemand hat inzwischen etwas angelegt),
    wird nichts importiert und ``report.changed`` gesetzt.
    """
    report = ImportReport(kind=kind, digest=hashlib.sha256(raw).hexdigest())
    try:
        text, report.encoding = decode_upload(raw)
        report.hints.extend(text_hints(text))
        table = read_table(text, kind)
    except ImportFileError as exc:
        report.file_errors.append(str(exc))
        return report
    report.delimiter = table.delimiter
    report.ignored_headers = table.ignored

    handler = kind.handler_cls(kind, station=station, actor=actor, digest=report.digest)
    try:
        with transaction.atomic():
            if commit:
                # FOR NO KEY UPDATE reiht Importe derselben Wache hintereinander,
                # ohne die FOR-KEY-SHARE-Sperre zu blockieren, die jedes INSERT
                # mit Fremdschlüssel auf die Wache nimmt (Audit, Übergaben, …).
                Station.objects.select_for_update(no_key=True).filter(pk=station.pk).first()
            handler.preload()
            entries = []
            for parsed in table.rows:
                result = RowResult(line=parsed.line)
                result.errors.extend(parsed.errors)
                handler.current_line = parsed.line
                plan = handler.validate(Cells(kind, parsed, result), result)
                entries.append((result, plan))
                report.rows.append(result)
            handler.finalize(entries)
            for result in report.rows:
                if result.errors:
                    result.status = "error"
            if commit and expected_plan is not None and not report.has_errors:
                report.changed = report.plan_digest != expected_plan
            if not report.has_errors and not report.changed:
                handler.apply_all(entries)
                if commit:
                    counts = report.counts
                    audit(actor, station, kind.audit_action, station, {
                        "kind": kind.slug,
                        "counts": {key: counts[key] for key in ("rows", "created", "skipped", "warnings")},
                        "sha256": report.digest,
                        "encoding": report.encoding,
                        "delimiter": report.delimiter,
                    })
                    report.committed = True
            if not report.committed:
                transaction.set_rollback(True)
    except (IntegrityError, ValidationError, ValueError) as exc:
        report.committed = False
        report.file_errors.append(
            _("Zeile %(line)s konnte nicht gespeichert werden. Es wurde nichts importiert.")
            % {"line": handler.current_line or "?"}
        )
        logger.warning("Stammdatenimport %s abgebrochen in Zeile %s: %s", kind.slug, handler.current_line,
                       type(exc).__name__)
    return report


def make_token(station, actor, slug: str, digest: str, plan: str) -> str:
    """Signiert Wache, Person, Art, Prüfsumme und das Vorschau-Ergebnis (1 h gültig)."""
    return signing.dumps({"s": station.pk, "u": actor.pk, "k": slug, "d": digest, "p": plan}, salt=TOKEN_SALT)


def token_plan(token: str, station, actor, slug: str, digest: str) -> str | None:
    """``plan_digest`` der Vorschau, wenn das Token zu Wache, Person, Art und Datei passt."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("p"), str):
        return None
    expected = {"s": station.pk, "u": actor.pk, "k": slug, "d": digest}
    if {key: data.get(key) for key in expected} != expected:
        return None
    return data["p"]
