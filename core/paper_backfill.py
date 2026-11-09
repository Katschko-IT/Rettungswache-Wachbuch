"""Nachtrag vom Papierbogen: gemeinsame Regeln für alle Nachweise (0.28).

Fällt das Wachbuch aus, arbeitet die Wache mit den Blättern aus ``/papier/``.
Läuft es wieder, werden die ausgefüllten Blätter als Nachtrag erfasst. Ein
Nachtrag trägt zwei Zeiten: die Ereigniszeit laut Bogen (``occurred_at``) und
die Erfassungszeit (das bisherige Zeitfeld des Datensatzes, siehe
``PaperBackfillRecord.BACKFILL_ENTRY_FIELD``).

Gilt für Übergaben (``HandoverEntry``), Fahrzeugübernahmen
(``VehicleHandover``), Desinfektionen (``DisinfectionProtocol``) und
Funktionskontrollen (``DeviceRoutineCheck``); Checklisten regeln ihren Nachtrag
im Checklisten-Dienst nach denselben Regeln:

- Die Ereigniszeit wird nur mit dem Häkchen „Nachtrag vom Papierbogen“
  gespeichert; ohne Häkchen bleibt sie leer (Datenbank-Bedingung).
- Sie liegt nicht in der Zukunft und höchstens ``BACKFILL_MAX_DAYS`` Tage vor
  der Erfassung.
- Das Wachenterminal (Dienstkonto) trägt nichts nach: Formulare zeigen die
  Felder dort nicht, Ansichten und App-Schnittstelle weisen den Nachtrag ab.
- Das Audit nennt Häkchen und Ereigniszeit nur bei einem Nachtrag (keine
  Freitexte).
- Was nach „wann es passiert ist“ fragt (letzte Desinfektion, letzte
  Funktionskontrolle, Sortierung), nimmt die Ereigniszeit, sonst die
  Erfassungszeit. Das 5-Minuten-Storno einer Funktionskontrolle zählt ab der
  Erfassung.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django import forms
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

BACKFILL_MAX_DAYS = 365
BACKFILL_FIELDS = ("is_paper_backfill", "occurred_at")
INPUT_FORMAT = "%Y-%m-%dT%H:%M"
DISPLAY_FORMAT = "%d.%m.%Y %H:%M"

TERMINAL_REFUSAL = _("Nachträge vom Papierbogen sind am Wachenterminal nicht möglich. Bitte persönlich anmelden.")


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"


def can_backfill(user) -> bool:
    """Nachträge nur mit persönlichem Konto, nie mit dem Dienstkonto des Wachenterminals."""
    from .terminal import is_service_user

    return bool(getattr(user, "is_authenticated", False)) and not is_service_user(user)


def backfill_time_errors(occurred_at: datetime | None, *, reference: datetime | None = None) -> list[str]:
    """Prüft die Ereigniszeit eines Nachtrags.

    Ohne ``reference`` gilt „jetzt“ (neuer Nachtrag). Bei einer Korrektur ist
    ``reference`` die Erfassungszeit des Datensatzes: Das Ereignis liegt dann
    vor der Erfassung und höchstens ``BACKFILL_MAX_DAYS`` Tage davor.
    """
    if occurred_at is None:
        return [gettext("Für Nachträge von Papier muss ein Ereigniszeitpunkt angegeben werden.")]
    if reference is None:
        now = timezone.now()
        if occurred_at > now:
            return [gettext("Der Ereigniszeitpunkt darf nicht in der Zukunft liegen.")]
        if occurred_at < now - timedelta(days=BACKFILL_MAX_DAYS):
            return [gettext("Der Ereigniszeitpunkt darf höchstens 365 Tage zurückliegen.")]
        return []
    if occurred_at > reference:
        return [gettext("Der Ereigniszeitpunkt darf nicht nach der Erfassung im Wachbuch liegen.")]
    if occurred_at < reference - timedelta(days=BACKFILL_MAX_DAYS):
        return [gettext("Der Ereigniszeitpunkt darf höchstens 365 Tage vor der Erfassung liegen.")]
    return []


def json_backfill_type_errors(body: dict) -> dict:
    """Feldfehler für falsche JSON-Typen von Häkchen und Ereigniszeit (App-Schnittstelle).

    ``occurred_at`` ist Text (ISO 8601) oder ``null``, ``is_paper_backfill`` ein
    Wahrheitswert, Text oder ``null``. Andere Typen ließen die Formularprüfung
    mit einem Serverfehler abbrechen.
    """
    errors = {}
    occurred = body.get("occurred_at")
    if occurred is not None and not isinstance(occurred, str):
        errors["occurred_at"] = [gettext("Bitte Datum und Uhrzeit als Text im Format ISO 8601 angeben.")]
    flag = body.get("is_paper_backfill")
    if flag is not None and not isinstance(flag, (bool, str)):
        errors["is_paper_backfill"] = [gettext("Bitte true oder false angeben.")]
    return errors


def truncate_to_minute(value: datetime | None) -> datetime | None:
    """Ereigniszeiten gelten auf die Minute (wie im Formular und auf dem Bogen)."""
    if value is None:
        return None
    return value.replace(second=0, microsecond=0)


def backfill_requested(data, files=None, name: str = "is_paper_backfill") -> bool:
    """Ob die Rohdaten (Formular oder JSON) einen Nachtrag verlangen."""
    if not data:
        return False
    return bool(forms.CheckboxInput().value_from_datadict(data, files or {}, name))


class PaperBackfillFormMixin:
    """Häkchen „Nachtrag vom Papierbogen“ und Ereigniszeit für ein Nachweisformular.

    Das Formular nimmt ``is_paper_backfill`` und ``occurred_at`` in
    ``Meta.fields`` auf, ruft in ``__init__`` ``setup_paper_backfill`` und in
    ``clean`` ``clean_paper_backfill`` auf.
    """

    backfill_allowed = True
    backfill_reference = None

    def setup_paper_backfill(self, *, allow: bool = True, reference: datetime | None = None) -> None:
        self.backfill_allowed = allow
        self.backfill_reference = reference
        if not allow:
            for name in BACKFILL_FIELDS:
                self.fields.pop(name, None)
            return
        flag = self.fields.get("is_paper_backfill")
        if flag is not None:
            flag.required = False
            flag.label = _("Nachtrag vom Papierbogen")
        when = self.fields.get("occurred_at")
        if when is not None:
            upper = reference or timezone.now()
            when.required = False
            when.label = _("Ereigniszeitpunkt (Papierbogen)")
            when.widget = DateTimeLocalInput(
                format=INPUT_FORMAT,
                attrs={
                    "min": timezone.localtime(upper - timedelta(days=BACKFILL_MAX_DAYS)).strftime(INPUT_FORMAT),
                    "max": timezone.localtime(upper).strftime(INPUT_FORMAT),
                },
            )

    @property
    def is_backfill_requested(self) -> bool:
        return backfill_requested(self.data, self.files, self.add_prefix("is_paper_backfill"))

    def clean_paper_backfill(self, cleaned: dict) -> dict:
        if not self.backfill_allowed:
            if self.is_bound and self.is_backfill_requested:
                self.add_error(None, TERMINAL_REFUSAL)
            return cleaned
        if cleaned.get("is_paper_backfill"):
            # Auf die Minute: Das Formularfeld zeigt keine Sekunden, eine
            # Korrektur änderte sonst unbemerkt die Zeit.
            cleaned["occurred_at"] = truncate_to_minute(cleaned.get("occurred_at"))
            if "occurred_at" not in self.errors:
                for message in backfill_time_errors(cleaned.get("occurred_at"), reference=self.backfill_reference):
                    self.add_error("occurred_at", message)
        else:
            # Ohne Häkchen keine Ereigniszeit (auch nicht versehentlich mitgeschickt).
            cleaned["occurred_at"] = None
        return cleaned


class PaperBackfillRecord:
    """Ereigniszeit und Kennzeichnung für Modelle mit Nachtrag vom Papierbogen."""

    # Name des Zeitfelds, das die Erfassung stempelt.
    BACKFILL_ENTRY_FIELD = "created_at"

    @property
    def recorded_at(self):
        return getattr(self, self.BACKFILL_ENTRY_FIELD)

    @property
    def event_at(self):
        """Wann es passiert ist: Ereigniszeit eines Nachtrags, sonst die Erfassung."""
        if self.is_paper_backfill and self.occurred_at:
            return self.occurred_at
        return self.recorded_at

    @property
    def paper_backfill_label(self) -> str:
        """„Nachtrag vom Papierbogen · Ereignis … · erfasst …“ (Listen, Detail, Druck, CSV)."""
        if not self.is_paper_backfill:
            return ""
        return paper_backfill_label(self.occurred_at, self.recorded_at)


def _format(value) -> str:
    if value is None:
        return "–"
    return timezone.localtime(value).strftime(DISPLAY_FORMAT)


def paper_backfill_label(occurred_at, recorded_at) -> str:
    return gettext("Nachtrag vom Papierbogen · Ereignis %(event)s · erfasst %(recorded)s") % {
        "event": _format(occurred_at),
        "recorded": _format(recorded_at),
    }


def event_time(entry_field: str):
    """Ausdruck „Ereigniszeit, sonst Erfassung“ für Abfragen."""
    return Coalesce(F("occurred_at"), F(entry_field))


def newest_event_first(queryset, entry_field: str):
    """Sortiert nach Ereigniszeit (Nachtrag) bzw. Erfassung, neueste zuerst."""
    return queryset.annotate(event_time=event_time(entry_field)).order_by("-event_time", "-pk")


def iso_utc(value) -> str | None:
    """ISO 8601 in UTC: gleiche Schreibweise, ob der Wert aus dem Formular oder der Datenbank kommt."""
    if value is None:
        return None
    return value.astimezone(dt_timezone.utc).isoformat()


def backfill_audit_metadata(record) -> dict:
    """Audit-Angaben nur für einen Nachtrag: Häkchen und Ereigniszeit, keine Freitexte."""
    if not getattr(record, "is_paper_backfill", False):
        return {}
    return {"paper_backfill": True, "occurred_at": iso_utc(getattr(record, "occurred_at", None))}


def backfill_constraint(model_name: str, *, strict: bool = True):
    """Datenbank-Bedingung: Ereigniszeit nur bei einem Nachtrag (``strict``: und immer bei einem)."""
    from django.db import models

    if strict:
        condition = models.Q(is_paper_backfill=False, occurred_at__isnull=True) | models.Q(
            is_paper_backfill=True, occurred_at__isnull=False
        )
    else:
        condition = models.Q(is_paper_backfill=True) | models.Q(occurred_at__isnull=True)
    return models.CheckConstraint(condition=condition, name=f"{model_name}_backfill_time")
