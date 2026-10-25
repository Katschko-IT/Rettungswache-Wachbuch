"""Kaffeekasse: Monatsbeiträge, Stand pro Person, Kassenbestand, GiroCode.

Regeln (docs/KAFFEEKASSE.md):

- Für jede teilnehmende Person entsteht je Monat genau ein Monatsbeitrag als
  Belastung (``CoffeeEntry.Kind.FEE``). Der Betrag wird beim Anlegen
  festgeschrieben; eine spätere Beitragsänderung ändert alte Monate nicht.
- Einzahlungen tilgen offene Monate der Reihe nach (ältester zuerst). Was
  übrig bleibt, ist Guthaben für die nächsten Monate.
- Eine Befreiung (Urlaub, Elternzeit, Krankheit) gleicht genau einen Monat aus.
- Der Bestand der Kasse ergibt sich aus Bareinzahlungen und Kassenbewegungen.
  Der Kassensturz vergleicht ihn mit dem gezählten Bargeld.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from .coffee_models import CoffeeCashMovement, CoffeeFund, CoffeeParticipant
from .models import CoffeeEntry, Membership

logger = logging.getLogger(__name__)

PAID = "paid"
OPEN = "open"
WAIVED = "waived"
NOT_CHARGED = "none"
FUTURE = "future"


def month_start(day: dt.date) -> dt.date:
    return day.replace(day=1)


def add_months(month: dt.date, count: int) -> dt.date:
    index = month.year * 12 + month.month - 1 + count
    return dt.date(index // 12, index % 12 + 1, 1)


def month_label(month: dt.date) -> str:
    return formats.date_format(month, "F Y")


def station_today(station) -> dt.date:
    try:
        zone = ZoneInfo(station.timezone_name or "Europe/Berlin")
    except Exception:  # unbekannte Zeitzone: Serverzeit
        zone = timezone.get_current_timezone()
    return timezone.now().astimezone(zone).date()


def fund_for(station) -> CoffeeFund:
    """Einstellungen der Kasse; ohne Datensatz gelten die Standardwerte (kein Beitrag)."""
    fund = CoffeeFund.objects.filter(station=station).first()
    return fund or CoffeeFund(station=station)


def euro(cents: int) -> str:
    return formats.number_format(cents / 100, 2, use_l10n=True, force_grouping=True) + " €"


# --- Monatsbeiträge --------------------------------------------------------

def ensure_fees(station, today: dt.date | None = None) -> int:
    """Bucht fehlende Monatsbeiträge bis einschließlich des laufenden Monats.

    Idempotent (eindeutiger Monat je Person); ausgeschiedene Mitglieder zahlen
    nicht weiter.
    """
    fund = fund_for(station)
    if not station.coffee_enabled or not fund.pk or not fund.monthly_fee_cents:
        return 0
    current = month_start(today or station_today(station))
    active_users = set(
        Membership.objects.filter(station=station, is_active=True).values_list("user_id", flat=True)
    )
    participants = [
        p for p in CoffeeParticipant.objects.filter(station=station, since__lte=current)
        if p.user_id in active_users
    ]
    if not participants:
        return 0
    existing = defaultdict(set)
    for user_id, period in CoffeeEntry.objects.filter(
        station=station, kind=CoffeeEntry.Kind.FEE, correction_of__isnull=True,
        member_id__in=[p.user_id for p in participants],
    ).values_list("member_id", "period"):
        existing[user_id].add(period)
    created = 0
    for participant in participants:
        month = participant.since
        last = min(current, participant.until) if participant.until else current
        while month <= last:
            if month not in existing[participant.user_id]:
                try:
                    with transaction.atomic():
                        CoffeeEntry.objects.create(
                            station=station,
                            member_id=participant.user_id,
                            amount_cents=-fund.monthly_fee_cents,
                            reason=_("Monatsbeitrag %(month)s") % {"month": month_label(month)},
                            kind=CoffeeEntry.Kind.FEE,
                            period=month,
                        )
                    created += 1
                except (IntegrityError, ValidationError):  # paralleler Lauf war schneller
                    pass
            month = add_months(month, 1)
    return created


@dataclass
class MonthStatus:
    period: dt.date
    status: str
    due_cents: int = 0
    remaining_cents: int = 0

    @property
    def label(self) -> str:
        return month_label(self.period)

    @property
    def short_label(self) -> str:
        return formats.date_format(self.period, "M y")

    @property
    def remaining_euros(self) -> float:
        return self.remaining_cents / 100


@dataclass
class MemberStatus:
    balance_cents: int = 0
    months: dict = field(default_factory=dict)

    @property
    def open_cents(self) -> int:
        return max(-self.balance_cents, 0)

    @property
    def credit_cents(self) -> int:
        return max(self.balance_cents, 0)

    @property
    def open_euros(self) -> float:
        return self.open_cents / 100

    @property
    def credit_euros(self) -> float:
        return self.credit_cents / 100

    @property
    def open_months(self) -> list:
        return [m for m in self.months.values() if m.status == OPEN]

    def recent(self, current: dt.date, count: int) -> list:
        """Die letzten ``count`` Monate bis ``current`` (neuester zuerst)."""
        result = []
        for offset in range(count):
            month = add_months(current, -offset)
            result.append(self.months.get(month) or MonthStatus(month, NOT_CHARGED))
        return result


def _status_from_rows(rows) -> MemberStatus:
    fees = defaultdict(int)
    waivers = defaultdict(int)
    pool = 0
    balance = 0
    for kind, period, amount in rows:
        balance += amount
        if kind == CoffeeEntry.Kind.FEE:
            fees[period] -= amount
        elif kind == CoffeeEntry.Kind.WAIVER:
            waivers[period] += amount
        else:
            pool += amount
    status = MemberStatus(balance_cents=balance)
    for period in sorted(fees):
        due = fees[period]
        if due <= 0:
            continue  # Beitrag per Gegenbuchung zurückgenommen
        remaining = max(due - waivers.get(period, 0), 0)
        if remaining == 0:
            status.months[period] = MonthStatus(period, WAIVED, due)
            continue
        paid = min(max(pool, 0), remaining)
        pool -= paid
        remaining -= paid
        status.months[period] = MonthStatus(period, PAID if remaining == 0 else OPEN, due, remaining)
    return status


def member_status(station, user) -> MemberStatus:
    rows = CoffeeEntry.objects.filter(station=station, member=user).values_list("kind", "period", "amount_cents")
    return _status_from_rows(rows)


def station_statuses(station) -> dict:
    """Stand aller Personen mit Buchungen (nur für den Kassenwart)."""
    grouped = defaultdict(list)
    for member_id, kind, period, amount in CoffeeEntry.objects.filter(station=station).values_list(
        "member_id", "kind", "period", "amount_cents"
    ):
        grouped[member_id].append((kind, period, amount))
    return {member_id: _status_from_rows(rows) for member_id, rows in grouped.items()}


def year_months(year: int) -> list:
    """Januar bis Dezember eines Jahres (jeweils der Monatserste)."""
    return [dt.date(year, month, 1) for month in range(1, 13)]


def year_cells(status: "MemberStatus", year: int, current: dt.date) -> list:
    cells = []
    for month in year_months(year):
        if month > current:
            cells.append(MonthStatus(month, FUTURE))
        else:
            cells.append(status.months.get(month) or MonthStatus(month, NOT_CHARGED))
    return cells


def chosen_year(raw, current: dt.date, first_year: int | None) -> int:
    """Jahr aus ``?jahr=``; begrenzt auf das erste Beitragsjahr bis zum laufenden Jahr."""
    first = min(first_year or current.year, current.year)
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return current.year
    return min(max(year, first), current.year)


def first_fee_year(station, user=None) -> int | None:
    entries = CoffeeEntry.objects.filter(station=station, kind=CoffeeEntry.Kind.FEE)
    if user is not None:
        entries = entries.filter(member=user)
    first = entries.order_by("period").values_list("period", flat=True).first()
    return first.year if first else None


def month_summary(station, month: dt.date) -> dict:
    """Wie viele Teilnehmende den Monat bezahlt haben – ohne Namen, für alle sichtbar."""
    statuses = station_statuses(station)
    counts = {PAID: 0, OPEN: 0, WAIVED: 0}
    for status in statuses.values():
        entry = status.months.get(month)
        if entry and entry.status in counts:
            counts[entry.status] += 1
    counts["total"] = sum(counts.values())
    return counts


# --- Kasse und Konto -------------------------------------------------------

@dataclass
class Pots:
    cash_cents: int
    bank_cents: int

    @property
    def cash_euros(self) -> float:
        return self.cash_cents / 100

    @property
    def bank_euros(self) -> float:
        return self.bank_cents / 100


def pots(station) -> Pots:
    payments = CoffeeEntry.objects.filter(station=station, kind=CoffeeEntry.Kind.PAYMENT)
    cash_in = payments.filter(method=CoffeeEntry.Method.CASH).aggregate(s=Sum("amount_cents"))["s"] or 0
    bank_in = payments.exclude(method=CoffeeEntry.Method.CASH).aggregate(s=Sum("amount_cents"))["s"] or 0
    movements = CoffeeCashMovement.objects.filter(station=station)
    cash_moves = movements.filter(pot=CoffeeCashMovement.Pot.CASH).aggregate(s=Sum("amount_cents"))["s"] or 0
    bank_moves = movements.filter(pot=CoffeeCashMovement.Pot.BANK).aggregate(s=Sum("amount_cents"))["s"] or 0
    # Bargeld aufs Konto: die Dose wird abgebucht (negativ), das Konto steigt.
    deposits = movements.filter(kind=CoffeeCashMovement.Kind.DEPOSIT).aggregate(s=Sum("amount_cents"))["s"] or 0
    return Pots(cash_cents=cash_in + cash_moves, bank_cents=bank_in + bank_moves - deposits)


def last_count(station):
    return (
        CoffeeCashMovement.objects.filter(station=station, kind=CoffeeCashMovement.Kind.COUNT, correction_of__isnull=True)
        .exclude(corrections__isnull=False)
        .select_related("created_by", "witness")
        .first()
    )


# --- GiroCode (EPC-QR, EPC069-12) -------------------------------------------

EPC_MAX_BYTES = 331


def normalize_iban(value: str) -> str:
    return "".join(value.split()).upper()


def epc_payload(*, name: str, iban: str, amount_cents: int = 0, text: str = "", bic: str = "") -> str:
    """Überweisungsdaten für Banking-Apps (Version 002, UTF-8, SEPA-Überweisung).

    Zeilen: BCD, 002, 1, SCT, BIC, Name, IBAN, Betrag, Zweckcode, Referenz,
    Verwendungszweck. Nach dem letzten gefüllten Feld folgt kein Zeilenumbruch.
    """
    name = " ".join(name.split())[:70]
    text = " ".join(text.split())[:140]
    amount = ""
    if amount_cents > 0:
        amount = f"EUR{amount_cents // 100}.{amount_cents % 100:02d}"
    lines = ["BCD", "002", "1", "SCT", normalize_iban(bic), name, normalize_iban(iban), amount, "", "", text]
    while lines and not lines[-1]:
        lines.pop()
    payload = "\n".join(lines)
    if len(payload.encode("utf-8")) > EPC_MAX_BYTES:
        raise ValueError("GiroCode zu lang")
    return payload


def transfer_text(station, user) -> str:
    person = (user.get_full_name() or user.get_username()).strip()
    return f"Kaffeekasse {station.name} {person}"


def girocode_png(payload: str) -> bytes:
    import io

    import qrcode

    buffer = io.BytesIO()
    qrcode.make(payload, box_size=6, border=2).save(buffer, format="PNG")
    return buffer.getvalue()


def transfer_details(station, fund, user, amount_cents: int) -> dict | None:
    """Überweisungsangaben samt GiroCode-Nutzdaten – oder None ohne IBAN."""
    if not station.iban:
        return None
    name = fund.account_holder or station.name
    text = transfer_text(station, user)
    try:
        payload = epc_payload(name=name, iban=station.iban, bic=station.bic, amount_cents=amount_cents, text=text)
    except ValueError:
        return None
    return {"payload": payload, "name": name, "iban": normalize_iban(station.iban), "bic": station.bic,
            "amount_euros": amount_cents / 100, "text": text}


# --- E-Mail -----------------------------------------------------------------

class HtmlWithImages(EmailMultiAlternatives):
    """HTML-Teil als multipart/related mit eingebetteten PNG-Bildern (``cid:…``)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inline_images = []

    def message(self, *args, **kwargs):
        msg = super().message(*args, **kwargs)
        html = msg.get_body(preferencelist=("html",))
        for cid, data in self.inline_images:
            html.add_related(data, "image", "png", cid=f"<{cid}>", disposition="inline", filename=f"{cid}.png")
        return msg


def email_enabled() -> bool:
    return bool(getattr(settings, "EMAIL_HOST", ""))


def send_reminder_email(station, user, *, fund=None, status=None) -> bool:
    """Erinnerung mit Überweisungs-QR an die E-Mail-Adresse der Person."""
    from django.template.loader import render_to_string

    if not email_enabled() or not user.email:
        return False
    fund = fund or fund_for(station)
    status = status or member_status(station, user)
    amount = status.open_cents or fund.monthly_fee_cents
    transfer = transfer_details(station, fund, user, amount)
    site = getattr(settings, "SITE_URL", "")
    with translation.override(settings.LANGUAGE_CODE):
        context = {
            "station": station, "person": user.get_full_name() or user.get_username(),
            "open_euros": status.open_cents / 100, "fee_euros": fund.monthly_fee_cents / 100,
            "open_months": [m.label for m in status.open_months], "transfer": transfer,
            "paypal_url": station.paypal_me_url, "wero_url": station.wero_link, "note": station.payment_note,
            "coffee_url": f"{site}{reverse('coffee')}" if site else "", "app_name": settings.APP_NAME,
        }
        if status.open_cents:
            subject = _("Kaffeekasse %(station)s: %(amount)s offen") % {
                "station": station.name, "amount": euro(status.open_cents)}
        else:
            subject = _("Kaffeekasse %(station)s: Zahlungsangaben") % {"station": station.name}
        text = render_to_string("emails/coffee_reminder.txt", context)
        html = render_to_string("emails/coffee_reminder.html", context)
    message = HtmlWithImages(subject, text, to=[user.email])
    message.attach_alternative(html, "text/html")
    if transfer:
        message.inline_images.append(("girocode", girocode_png(transfer["payload"])))
    message.send()
    return True


# --- Erinnerung ------------------------------------------------------------

def remind_open_fees(now=None) -> int:
    """Erinnert Teilnehmende einmal im Monat an offene Beiträge (Posteingang, Push).

    Der Worker hat keine Anfrage und damit keine Sprache; die Texte folgen der
    Standardsprache der Installation.
    """
    with translation.override(settings.LANGUAGE_CODE):
        return _remind_open_fees(now)


def _remind_open_fees(now=None) -> int:
    from .crew_notifications import _enqueue_channels
    from .notification_models import UserNotification

    created = 0
    funds = CoffeeFund.objects.select_related("station").filter(
        monthly_fee_cents__gt=0, reminder_day__gt=0, station__coffee_enabled=True, station__is_active=True,
    )
    for fund in funds:
        station = fund.station
        today = station_today(station) if now is None else timezone.localtime(now).date()
        ensure_fees(station, today)
        if today.day < fund.reminder_day:
            continue
        key = f"coffee:{today:%Y-%m}"
        if fund.signal_group_reminder:
            created += int(_remind_group(fund, today))
        active = set(Membership.objects.filter(station=station, is_active=True).values_list("user_id", flat=True))
        statuses = station_statuses(station)
        for participant in CoffeeParticipant.objects.filter(station=station).select_related("user"):
            status = statuses.get(participant.user_id)
            if participant.user_id not in active or not status or not status.open_months:
                continue
            months = len(status.open_months)
            title = _("Kaffeekasse: Beitrag offen")
            body = _("Offen: %(amount)s (%(months)s Monat(e)). Bar in die Kasse oder per Überweisung, danach in Wachwerk abhaken.") % {
                "amount": euro(status.open_cents), "months": months,
            }
            url = reverse("coffee")
            try:
                with transaction.atomic():
                    note, was_created = UserNotification.objects.get_or_create(
                        user=participant.user, dedupe_key=key,
                        defaults={"station": station, "kind": UserNotification.Kind.COFFEE_DUE,
                                  "title": title, "body": body[:300], "url": url},
                    )
                    if was_created:
                        _enqueue_channels(note, {"title": title, "body": body[:300], "url": url,
                                                 "notification_id": note.pk})
                        created += 1
            except IntegrityError:
                continue
            if was_created and fund.email_reminder and participant.email_reminders:
                try:
                    send_reminder_email(station, participant.user, fund=fund, status=status)
                except Exception:  # SMTP-Fehler dürfen die übrigen Erinnerungen nicht aufhalten
                    logger.exception("Kaffeekasse: E-Mail-Erinnerung an Nutzer %s fehlgeschlagen", participant.user_id)
    return created


def _remind_group(fund, today: dt.date) -> bool:
    """Anonyme Monatserinnerung in die Signal-Gruppe der Wache (höchstens einmal im Monat)."""
    from .signal_messenger import enqueue_for_group, message_text

    station = fund.station
    month = month_start(today)
    summary = month_summary(station, month)
    text = _("☕ Kaffeekasse: Der Beitrag für %(month)s (%(fee)s) ist fällig. Bar in die Kasse oder per Überweisung, danach in Wachwerk abhaken.") % {
        "month": formats.date_format(month, "F"), "fee": euro(fund.monthly_fee_cents),
    }
    if summary["total"]:
        text += " " + _("%(paid)s von %(total)s haben schon bezahlt.") % summary
    return enqueue_for_group(station, message_text(text, url=reverse("coffee")),
                             dedupe_key=f"coffee-group:{station.pk}:{month:%Y-%m}")


def announce_count(movement) -> bool:
    """Kassensturz-Ergebnis ohne Namen in die Signal-Gruppe, wenn eingeschaltet."""
    from .signal_messenger import enqueue_for_group, signal_enabled

    fund = fund_for(movement.station)
    if not (signal_enabled() and fund.pk and fund.signal_group_counts):
        return False
    with translation.override(settings.LANGUAGE_CODE):
        if movement.amount_cents:
            text = _("☕ Kaffeekasse: Kassensturz am %(date)s – Differenz %(diff)s.") % {
                "date": formats.date_format(timezone.localtime(movement.created_at), "d.m.Y"),
                "diff": euro(movement.amount_cents)}
        else:
            text = _("☕ Kaffeekasse: Kassensturz am %(date)s – die Kasse stimmt.") % {
                "date": formats.date_format(timezone.localtime(movement.created_at), "d.m.Y")}
    return enqueue_for_group(movement.station, text, dedupe_key=f"coffee-count:{movement.pk}")


def former_members_with_balance(station, statuses: dict) -> list:
    active = set(Membership.objects.filter(station=station, is_active=True).values_list("user_id", flat=True))
    return [member_id for member_id, status in statuses.items() if member_id not in active and status.balance_cents]
