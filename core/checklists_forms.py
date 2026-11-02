"""Formulare und Validierung für Checklisten-Läufe (0.28)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils.translation import gettext as _

from .models import Checklist, ChecklistItem


def validate_checklist_submission(
    checklist: Checklist,
    data: dict[str, Any],
    *,
    is_draft: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validiert die übermittelten Ergebnisse je Prüfpunkt einer Checkliste.

    Gibt ein Tupel ``(item_results, errors)`` zurück:
    - ``item_results``: Dict mit ``str(item.id) -> {"status": ..., "value": ..., "reason": ..., "defect_id": ...}``
    - ``errors``: Liste von Fehlermeldungen bei ungültigen Eingaben.
    """
    item_results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    # Prüfen, ob strukturierte item_results direkt übergeben wurden
    direct_results = data.get("item_results") if isinstance(data, dict) else None

    for item in checklist.items.all():
        key = str(item.id)
        if direct_results and isinstance(direct_results, dict) and key in direct_results:
            item_entry = direct_results[key] or {}
            status = str(item_entry.get("status") or "").strip()
            raw_val = item_entry.get("value")
            reason = str(item_entry.get("reason") or "").strip()[:500]
        else:
            status = str(data.get(f"result_{item.id}", "") or "").strip()
            raw_val = data.get(f"value_{item.id}")
            reason = str(data.get(f"reason_{item.id}", "") or "").strip()[:500]

        # Numerischen Messwert parsen, falls vorhanden
        val: float | None = None
        if raw_val not in (None, ""):
            if isinstance(raw_val, (int, float, Decimal)):
                val = float(raw_val)
            else:
                raw_str = str(raw_val).strip().replace(",", ".")
                if raw_str:
                    try:
                        val = float(raw_str)
                    except ValueError:
                        errors.append(
                            _("Ungültiger Messwert für „%(item)s“: %(value)s")
                            % {"item": item.text, "value": raw_val}
                        )

        # Grenzwerte prüfen
        measurement_out_of_bounds = False
        if val is not None:
            if item.min_value is not None and Decimal(str(val)) < item.min_value:
                measurement_out_of_bounds = True
            if item.max_value is not None and Decimal(str(val)) > item.max_value:
                measurement_out_of_bounds = True

        if measurement_out_of_bounds:
            # Bei Grenzwertüberschreitung automatisch als „nicht in Ordnung“ werten
            status = "not_ok"
            if not reason:
                unit = f" {item.measurement_unit}" if item.measurement_unit else ""
                bounds = f"[{item.min_value or '—'}..{item.max_value or '—'}]"
                reason = _("Messwert %(val)s%(unit)s außerhalb Grenzwert %(bounds)s") % {
                    "val": val,
                    "unit": unit,
                    "bounds": bounds,
                }

        # Validierung bei endgültigem Abschluss (nicht Zwischenstand)
        if not is_draft:
            if item.is_required and not status:
                errors.append(
                    _("Pflichtpunkt „%(item)s“ ist nicht ausgefüllt.") % {"item": item.text}
                )
            elif status == "na" and not reason:
                errors.append(
                    _("Für entfallenen Punkt „%(item)s“ ist eine Begründung erforderlich.")
                    % {"item": item.text}
                )
            elif status not in ("", "ok", "not_ok", "na"):
                errors.append(
                    _("Ungültiger Status für „%(item)s“: %(status)s")
                    % {"item": item.text, "status": status}
                )

        item_results[key] = {
            "status": status,
            "value": val,
            "reason": reason,
            "defect_id": None,
        }

    return item_results, errors
