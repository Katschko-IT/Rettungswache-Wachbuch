"""Checklisten-Läufe: eine Prüf- und Abschlusslogik für Web und App (0.28).

Web (``core/checklists_views.py``) und App (``core/api/views.py``) lesen ihre
Eingaben unterschiedlich ein, prüfen und speichern sie aber hier:

- ``validate_results`` prüft Ergebnis, Messwert und Begründung je Prüfpunkt
  und legt eine Kopie des Prüfpunkts (Text, Einheit, Grenzwerte, Pflicht) in
  jedes Ergebnis. Spätere Änderungen am Prüfpunkt ändern alte Läufe nicht.
- ``save_draft`` speichert den gemeinsamen Zwischenstand der Wache
  (``ChecklistDraft``, veränderbar, kein Nachweis).
- ``finalize_run`` legt den Lauf mit genau einem INSERT in die append-only
  Tabelle ``core_checklistcompletion`` an, legt Mängel für „nicht in Ordnung“
  an (oder verweist auf einen offenen Mangel desselben Prüfpunkts), löscht den
  Zwischenstand und schreibt das Prüfintervall fort.

Kein Pfad ändert oder löscht Zeilen in ``core_checklistcompletion``; die
Datenbankrolle der App darf das auch nicht (``grant_database_access``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Exists, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import formats, timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from .models import Checklist, ChecklistCompletion, ChecklistDraft, ChecklistItem
from .services import audit
from .wachalltag_models import Defect, DefectEvent

STATUS_OK = "ok"
STATUS_NOT_OK = "not_ok"
STATUS_NA = "na"
STATUSES = (STATUS_OK, STATUS_NOT_OK, STATUS_NA)

REASON_MAX = 500
NOTE_MAX = 300
# Messwerte passen in die Grenzwert-Spalten (DecimalField mit 8 Stellen, 2 Nachkommastellen).
VALUE_LIMIT = Decimal("999999.99")
VALUE_STEP = Decimal("0.01")
BACKFILL_MAX_DAYS = 365
QUOTA_DAYS = 30


class ChecklistInputError(ValueError):
    """Die Anfrage ist falsch aufgebaut (App: 400), unabhängig von den Prüfregeln."""


# ---- Hilfen -----------------------------------------------------------------


def effective_at_expression():
    """Zeitpunkt eines Laufs in Abfragen: Ereigniszeit bei Nachträgen, sonst Erfassungszeit."""
    return Coalesce(F("occurred_at"), F("created_at"))


def number_text(value) -> str:
    """Zahl ohne überflüssige Nullen („9.5“, „10“, „-18“)."""
    if value is None:
        return ""
    number = Decimal(str(value)).normalize()
    return format(number, "f")


def bounds_text(min_value, max_value) -> str:
    low = "—" if min_value in (None, "") else str(min_value)
    high = "—" if max_value in (None, "") else str(max_value)
    return f"{low}..{high}"


def _decimal_text(value) -> str | None:
    return None if value is None else str(value)


def parse_value(raw) -> tuple[Decimal | None, str]:
    """Messwert lesen: ``(Zahl, "")``, ``(None, "")`` für leer oder ``(None, Grund)``.

    Gründe: ``invalid`` (keine endliche Zahl, auch NaN/Infinity) und ``range``
    (Betrag größer als ``VALUE_LIMIT``).
    """
    if raw is None:
        return None, ""
    if isinstance(raw, bool):
        return None, "invalid"
    if isinstance(raw, (int, float, Decimal)):
        text = str(raw)
    elif isinstance(raw, str):
        text = raw.strip().replace(",", ".")
        if not text:
            return None, ""
    else:
        return None, "invalid"
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "invalid"
    if not number.is_finite():
        return None, "invalid"
    if abs(number) > VALUE_LIMIT:
        return None, "range"
    return number.quantize(VALUE_STEP, rounding=ROUND_HALF_UP), ""


def parse_flag(value, name: str) -> bool:
    """Wahrheitswert aus JSON streng lesen: true/false, 1/0, "true"/"false", "1"/"0"."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value in ("true", "1", "false", "0"):
        return value in ("true", "1")
    raise ChecklistInputError(_("„%(name)s“ muss true oder false sein.") % {"name": name})


def _outside_limits(item: ChecklistItem, value: Decimal) -> bool:
    return (item.min_value is not None and value < item.min_value) or (
        item.max_value is not None and value > item.max_value
    )


def _snapshot(item: ChecklistItem, status: str, value: Decimal | None, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "value": float(value) if value is not None else None,
        "reason": reason,
        # Kopie des Prüfpunkts zum Zeitpunkt des Laufs.
        "text": item.text,
        "unit": item.measurement_unit,
        "min": _decimal_text(item.min_value),
        "max": _decimal_text(item.max_value),
        "required": bool(item.is_required),
        "position": item.position,
        "defect_id": None,
        "defect_linked": False,
    }


def checklist_items(checklist: Checklist) -> list[ChecklistItem]:
    return list(checklist.items.all())


# ---- Eingaben lesen ---------------------------------------------------------


def raw_results_from_post(items, data) -> dict[str, dict[str, Any]]:
    """Formularfelder ``result_<id>``, ``value_<id>``, ``reason_<id>`` je Prüfpunkt."""
    raw = {}
    for item in items:
        raw[str(item.pk)] = {
            "status": data.get(f"result_{item.pk}", "") or "",
            "value": data.get(f"value_{item.pk}"),
            "reason": data.get(f"reason_{item.pk}", "") or "",
        }
    return raw


def raw_results_from_json(items, payload) -> dict[str, dict[str, Any]]:
    """``item_results`` der App: Objekt ``{"<Prüfpunkt-Kennung>": {status, value, reason}}``.

    Fremde Kennungen, Einträge ohne Objekt und Texte in falscher Form sind ein
    Aufbaufehler (``ChecklistInputError``), kein 500.
    """
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ChecklistInputError(_("„item_results“ muss ein Objekt mit den Kennungen der Prüfpunkte sein."))
    by_key = {str(item.pk): item for item in items}
    raw = {}
    for key, entry in payload.items():
        key = str(key).strip()
        item = by_key.get(key)
        if item is None:
            raise ChecklistInputError(_("Unbekannter Prüfpunkt: %(id)s") % {"id": key[:20]})
        if not isinstance(entry, dict):
            raise ChecklistInputError(_("Das Ergebnis für „%(item)s“ muss ein Objekt sein.") % {"item": item.text})
        status = entry.get("status")
        if status is None:
            status = ""
        if not isinstance(status, str):
            raise ChecklistInputError(
                _("Ungültiger Status für „%(item)s“: %(status)s") % {"item": item.text, "status": str(status)[:40]}
            )
        reason = entry.get("reason")
        if reason is None:
            reason = ""
        if not isinstance(reason, str):
            raise ChecklistInputError(_("Die Begründung für „%(item)s“ muss Text sein.") % {"item": item.text})
        raw[key] = {"status": status, "value": entry.get("value"), "reason": reason}
    return raw


# ---- Prüfen -------------------------------------------------------------------


def validate_results(items, raw, *, final: bool) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Ergebnisse je Prüfpunkt prüfen und mit Kopie des Prüfpunkts zurückgeben.

    Immer: Status nur ``ok``/``not_ok``/``na`` (oder leer), Messwerte endlich
    und im Bereich der Spalte. Ein Messwert außerhalb der Grenzwerte setzt
    „nicht in Ordnung“ mit automatischer Begründung (0 ist ein echter
    Grenzwert). Beim Abschluss zusätzlich: mindestens ein Ergebnis,
    Pflichtpunkte bewertet, „entfällt“ mit Begründung, Messpunkte mit
    Messwert bei „in Ordnung“/„nicht in Ordnung“.
    """
    results: dict[str, dict[str, Any]] = {}
    input_errors: list[str] = []
    rule_errors: list[str] = []
    for item in items:
        key = str(item.pk)
        entry = raw.get(key) or {}
        status = str(entry.get("status") or "").strip()
        reason = str(entry.get("reason") or "").strip()[:REASON_MAX]
        value = None
        value_problem = False
        if status and status not in STATUSES:
            input_errors.append(
                _("Ungültiger Status für „%(item)s“: %(status)s") % {"item": item.text, "status": status[:40]}
            )
            status = ""
        if item.has_measurement and status != STATUS_NA:
            raw_value = entry.get("value")
            number, problem = parse_value(raw_value)
            if problem == "invalid":
                value_problem = True
                input_errors.append(
                    _("Ungültiger Messwert für „%(item)s“: %(value)s") % {"item": item.text, "value": str(raw_value)[:40]}
                )
            elif problem == "range":
                value_problem = True
                input_errors.append(
                    _("Der Messwert für „%(item)s“ liegt außerhalb des zulässigen Bereichs.") % {"item": item.text}
                )
            else:
                value = number
        if value is not None and _outside_limits(item, value):
            status = STATUS_NOT_OK
            if not reason:
                unit = f" {item.measurement_unit}" if item.measurement_unit else ""
                reason = _("Messwert %(val)s%(unit)s außerhalb Grenzwert %(bounds)s") % {
                    "val": number_text(value),
                    "unit": unit,
                    "bounds": f"[{bounds_text(item.min_value, item.max_value)}]",
                }
        if final:
            if item.is_required and not status:
                rule_errors.append(_("Pflichtpunkt „%(item)s“ ist nicht ausgefüllt.") % {"item": item.text})
            elif status == STATUS_NA and not reason:
                rule_errors.append(
                    _("Für entfallenen Punkt „%(item)s“ ist eine Begründung erforderlich.") % {"item": item.text}
                )
            elif (
                item.has_measurement
                and status in (STATUS_OK, STATUS_NOT_OK)
                and value is None
                and not value_problem
            ):
                rule_errors.append(_("Messwert für „%(item)s“ fehlt.") % {"item": item.text})
        results[key] = _snapshot(item, status, value, reason)
    if final and items and not any(entry["status"] for entry in results.values()):
        return results, input_errors + [
            _("Für diesen Abschluss fehlen die Ergebnisse je Prüfpunkt. Bitte jeden Prüfpunkt bewerten.")
        ]
    return results, input_errors + rule_errors


def backfill_errors(occurred_at: datetime | None, *, now: datetime | None = None) -> list[str]:
    """Regeln für den Nachtrag vom Papierbogen (wie bei Übergaben, dazu höchstens 365 Tage alt)."""
    now = now or timezone.now()
    if occurred_at is None:
        return [_("Für Nachträge von Papier muss ein Ereigniszeitpunkt angegeben werden.")]
    if occurred_at > now:
        return [_("Der Ereigniszeitpunkt darf nicht in der Zukunft liegen.")]
    if occurred_at < now - timedelta(days=BACKFILL_MAX_DAYS):
        return [_("Der Ereigniszeitpunkt darf höchstens 365 Tage zurückliegen.")]
    return []


def parse_backfill_time(raw) -> tuple[datetime | None, bool]:
    """Ereigniszeit aus Formular (``YYYY-MM-DDTHH:MM``) oder App (ISO 8601): ``(Zeit, lesbar)``."""
    if raw in (None, ""):
        return None, True
    if not isinstance(raw, str):
        return None, False
    text = raw.strip()
    parsed = None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError:
        try:
            parsed = parse_datetime(text)
        except ValueError:
            parsed = None
    if parsed is None:
        return None, False
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed, True


# ---- Speichern ----------------------------------------------------------------


@dataclass
class FinalizeResult:
    completion: ChecklistCompletion
    created_defects: list = field(default_factory=list)
    linked_defects: list = field(default_factory=list)

    @property
    def defects(self) -> list:
        return [*self.created_defects, *self.linked_defects]


def save_draft(*, station, checklist, user, item_results, note, via: str) -> ChecklistDraft:
    """Gemeinsamen Zwischenstand der Wache anlegen oder ersetzen (eine Zeile je Checkliste)."""
    note = (note or "")[:NOTE_MAX]
    with transaction.atomic():
        draft = ChecklistDraft.objects.select_for_update().filter(station=station, checklist=checklist).first()
        if draft is None:
            try:
                with transaction.atomic():
                    draft = ChecklistDraft.objects.create(
                        station=station, checklist=checklist, created_by=user, updated_by=user,
                        item_results=item_results, note=note,
                    )
            except IntegrityError:
                # Gleichzeitig angelegt: den anderen Zwischenstand fortschreiben.
                draft = ChecklistDraft.objects.select_for_update().get(station=station, checklist=checklist)
                draft = _update_draft(draft, user, item_results, note)
        else:
            draft = _update_draft(draft, user, item_results, note)
        audit(user, station, "checklist.draft_saved", draft, {
            "fields": ["checklist", "note", "item_results"],
            "checklist_id": checklist.pk,
            "via": via,
        })
    return draft


def _update_draft(draft, user, item_results, note):
    draft.item_results = item_results
    draft.note = note
    draft.updated_by = user
    draft.save(update_fields=["item_results", "note", "updated_by", "updated_at"])
    return draft


def _entry_order(pair):
    key, entry = pair
    position = entry.get("position") if isinstance(entry, dict) else None
    return (position if isinstance(position, int) else 0, int(key) if str(key).isdigit() else 0)


def _local_text(moment) -> str:
    return formats.date_format(timezone.localtime(moment), "d.m.Y H:i")


def _defect_texts(checklist, entry, run_time) -> tuple[str, str]:
    item_text = entry.get("text") or ""
    title = _("Mangel aus Checkliste „%(checklist)s“: %(item)s") % {"checklist": checklist.title, "item": item_text}
    lines = [
        _("Prüfpunkt: %(item)s") % {"item": item_text},
        _("Checkliste: %(checklist)s") % {"checklist": checklist.title},
        _("Feststellung: %(reason)s") % {"reason": entry.get("reason") or _("nicht in Ordnung")},
    ]
    if entry.get("value") is not None:
        unit = f" {entry['unit']}" if entry.get("unit") else ""
        lines.append(_("Messwert: %(value)s%(unit)s (Grenzwerte: %(bounds)s)") % {
            "value": number_text(entry["value"]),
            "unit": unit,
            "bounds": bounds_text(entry.get("min"), entry.get("max")),
        })
    lines.append(_("Aus dem Checklisten-Lauf vom %(date)s.") % {"date": _local_text(run_time)})
    return title[:160], "\n".join(lines)


def open_defect_for_item(station, checklist, item_id: int):
    """Offener Mangel (nicht erledigt) aus einem früheren Lauf derselben Checkliste und desselben Prüfpunkts."""
    return (
        Defect.objects.filter(station=station, source_checklist_run__checklist=checklist, source_item_id=item_id)
        .exclude(status=Defect.Status.DONE)
        .order_by("-created_at", "-pk")
        .first()
    )


def finalize_run(
    *,
    station,
    checklist,
    user,
    item_results: dict[str, dict[str, Any]],
    note: str,
    is_paper_backfill: bool = False,
    occurred_at: datetime | None = None,
    via: str,
) -> FinalizeResult:
    """Lauf abschließen: ein INSERT in den Nachweis, Mängel, Zwischenstand weg, Intervall weiter.

    Mängel entstehen vor dem Lauf, damit ihre Kennungen im Nachweis stehen;
    danach bekommen sie den Rückverweis auf den Lauf (UPDATE nur an
    ``core_defect``). Gibt es für den Prüfpunkt schon einen offenen Mangel aus
    dieser Checkliste, entsteht kein zweiter: Das Ergebnis verweist auf ihn
    (``defect_linked``) und der Mangel bekommt einen Verlaufseintrag.
    """
    from .api.wachalltag import advance_checklist_schedule

    note = (note or "")[:NOTE_MAX]
    occurred_at = occurred_at if is_paper_backfill else None
    run_time = occurred_at or timezone.now()
    with transaction.atomic():
        # Abschlüsse derselben Checkliste nacheinander (keine doppelten Mängel).
        # Gesperrt wird die veränderbare Vorlage, nie die append-only Tabelle.
        Checklist.objects.select_for_update().filter(pk=checklist.pk).first()
        created, linked = [], []
        for key, entry in sorted(item_results.items(), key=_entry_order):
            if entry.get("status") != STATUS_NOT_OK:
                continue
            item_id = int(key)
            existing = open_defect_for_item(station, checklist, item_id)
            if existing is not None:
                entry["defect_id"] = existing.pk
                entry["defect_linked"] = True
                linked.append(existing)
                continue
            title, description = _defect_texts(checklist, entry, run_time)
            defect = Defect.objects.create(
                station=station,
                title=title,
                description=description,
                asset_ref=(_("Checkliste: %(checklist)s") % {"checklist": checklist.title})[:160],
                priority=Defect.Priority.IMPORTANT,
                status=Defect.Status.OPEN,
                category=Defect.Category.TASK,
                created_by=user,
                source_item_id=item_id,
                source_item_text=(entry.get("text") or "")[:200],
            )
            DefectEvent.objects.create(
                defect=defect, station=station, actor=user, kind=DefectEvent.Kind.CREATED, note=defect.title,
            )
            entry["defect_id"] = defect.pk
            created.append(defect)

        completion = ChecklistCompletion.objects.create(
            station=station,
            checklist=checklist,
            completed_by=user,
            note=note,
            item_results=item_results,
            is_paper_backfill=bool(is_paper_backfill),
            occurred_at=occurred_at,
        )
        if created:
            Defect.objects.filter(pk__in=[defect.pk for defect in created]).update(source_checklist_run=completion)
        for defect in created:
            defect.source_checklist_run = completion
            audit(user, station, "defect.created", defect, {
                "via": "checklist",
                "checklist_id": checklist.pk,
                "item_id": defect.source_item_id,
                "checklist_run_id": completion.pk,
            })
        for defect in linked:
            DefectEvent.objects.create(
                defect=defect, station=station, actor=user, kind=DefectEvent.Kind.UPDATED,
                metadata={
                    "note": _("Erneut festgestellt im Checklisten-Lauf"),
                    "via": "checklist",
                    "checklist_run_id": completion.pk,
                },
            )
        ChecklistDraft.objects.filter(station=station, checklist=checklist).delete()
        fields = ["checklist", "note", "item_results"]
        if completion.is_paper_backfill:
            fields += ["is_paper_backfill", "occurred_at"]
        audit(user, station, "checklist.completed", completion, {
            "fields": fields,
            "defects_created": [defect.pk for defect in created],
            "defects_linked": [defect.pk for defect in linked],
            "via": via,
        })
        advance_checklist_schedule(checklist.pk, done_at=occurred_at)
    return FinalizeResult(completion=completion, created_defects=created, linked_defects=linked)


# ---- Lesen und Auswerten ------------------------------------------------------


def status_label(status: str) -> str:
    labels = {
        STATUS_OK: _("in Ordnung"),
        STATUS_NOT_OK: _("nicht in Ordnung"),
        STATUS_NA: _("entfällt"),
    }
    return labels.get(status, _("nicht bewertet"))


def has_result_per_item(item_results) -> bool:
    """Jeder gespeicherte Prüfpunkt hat ein Ergebnis (Kennzahl des 0.28-Ziels)."""
    if not isinstance(item_results, dict) or not item_results:
        return False
    return all(isinstance(entry, dict) and entry.get("status") in STATUSES for entry in item_results.values())


def summarize(item_results) -> dict[str, int]:
    counts = {STATUS_OK: 0, STATUS_NOT_OK: 0, STATUS_NA: 0, "open": 0}
    if isinstance(item_results, dict):
        for entry in item_results.values():
            status = entry.get("status") if isinstance(entry, dict) else ""
            counts[status if status in STATUSES else "open"] += 1
    counts["total"] = sum(counts.values())
    return counts


def result_rows(item_results, items_by_id=None) -> list[dict[str, Any]]:
    """Ergebnisse eines Laufs in Anzeigereihenfolge, aus der gespeicherten Kopie des Prüfpunkts.

    Läufe vor 0.28-Abschluss ohne Kopie greifen auf den heutigen Prüfpunkt zurück.
    """
    items_by_id = items_by_id or {}
    rows = []
    if not isinstance(item_results, dict):
        return rows
    for key, entry in sorted(item_results.items(), key=_entry_order):
        if not isinstance(entry, dict):
            continue
        item = items_by_id.get(int(key)) if str(key).isdigit() else None
        text = entry.get("text") or (item.text if item else _("Prüfpunkt %(id)s") % {"id": key})
        if "text" in entry:
            unit, low, high, required = entry.get("unit") or "", entry.get("min"), entry.get("max"), entry.get("required")
        elif item is not None:
            unit, low, high, required = (
                item.measurement_unit, _decimal_text(item.min_value), _decimal_text(item.max_value), item.is_required,
            )
        else:
            unit, low, high, required = "", None, None, None
        status = entry.get("status") if entry.get("status") in STATUSES else ""
        defect_id = entry.get("defect_id")
        rows.append({
            "key": str(key),
            "text": text,
            "status": status,
            "status_label": status_label(status),
            "value": entry.get("value"),
            "value_text": number_text(entry.get("value")) if entry.get("value") is not None else "",
            "unit": unit,
            "min": low,
            "max": high,
            "has_limits": low is not None or high is not None,
            "bounds": bounds_text(low, high),
            "required": required,
            "reason": entry.get("reason") or "",
            "defect_id": defect_id if isinstance(defect_id, int) else None,
            "defect_linked": bool(entry.get("defect_linked")),
        })
    return rows


def prefill_from_results(item_results) -> dict[str, dict[str, str]]:
    """Werte zum Vorbelegen des Formulars aus einem Zwischenstand."""
    prefill = {}
    if not isinstance(item_results, dict):
        return prefill
    for key, entry in item_results.items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status") if entry.get("status") in STATUSES else ""
        value = entry.get("value")
        value_text = ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value_text = formats.number_format(Decimal(number_text(value)), use_l10n=True)
        prefill[str(key)] = {
            "status": status,
            "value": value_text,
            "reason": str(entry.get("reason") or ""),
        }
    return prefill


def prefill_from_post(items, data) -> dict[str, dict[str, str]]:
    """Werte zum erneuten Anzeigen eines abgelehnten Formulars: genau das Eingegebene."""
    prefill = {}
    for item in items:
        status = str(data.get(f"result_{item.pk}", "") or "")
        prefill[str(item.pk)] = {
            "status": status if status in STATUSES else "",
            "value": str(data.get(f"value_{item.pk}", "") or "")[:40],
            "reason": str(data.get(f"reason_{item.pk}", "") or "")[:REASON_MAX],
        }
    return prefill


def latest_runs(checklists) -> dict[int, ChecklistCompletion]:
    """Letzter endgültiger Lauf je Checkliste, nach Ereigniszeit (Nachträge zählen mit ihrer Zeit)."""
    ids = [checklist.pk for checklist in checklists]
    if not ids:
        return {}
    newest = (
        ChecklistCompletion.objects.filter(checklist=OuterRef("pk"))
        .annotate(effective=effective_at_expression())
        .order_by("-effective", "-pk")
        .values("pk")[:1]
    )
    run_ids = dict(
        Checklist.objects.filter(pk__in=ids).annotate(run_id=Subquery(newest)).values_list("pk", "run_id")
    )
    runs = ChecklistCompletion.objects.select_related("completed_by").in_bulk(
        [run_id for run_id in run_ids.values() if run_id]
    )
    return {checklist_id: runs[run_id] for checklist_id, run_id in run_ids.items() if run_id in runs}


def per_item_quota(station, *, now=None, days: int = QUOTA_DAYS) -> dict[str, int] | None:
    """Anteil der Läufe mit Ergebnis je Punkt (Summe der Wache, keine Werte je Person).

    Gezählt werden endgültige Läufe der letzten ``days`` Tage (Ereigniszeit)
    von Checklisten mit Prüfpunkten. Ohne solche Läufe ``None``.
    """
    now = now or timezone.now()
    runs = (
        ChecklistCompletion.objects.filter(station=station)
        .annotate(effective=effective_at_expression())
        .filter(effective__gte=now - timedelta(days=days), effective__lte=now)
        .filter(Exists(ChecklistItem.objects.filter(checklist_id=OuterRef("checklist_id"))))
        .values_list("item_results", flat=True)
    )
    total = 0
    complete = 0
    for item_results in runs.iterator(chunk_size=500):
        total += 1
        complete += has_result_per_item(item_results)
    if not total:
        return None
    return {"total": total, "complete": complete, "percent": round(complete * 100 / total)}
