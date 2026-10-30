"""Handlungsbedarf aus den Fachmodulen für die Übersicht.

Liefert pro aktiviertem Modul höchstens eine Karte mit einer Zahl, die direkt
auf die passend gefilterte Modulseite verlinkt. Es werden nur vorhandene Daten
gezählt; die Funktion legt nichts an und ändert nichts.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

ATTENTION_LEVELS = ("overdue", "critical")


def _card(key, url_name, query, title, subtitle, value, *, attention=None, tone="warning"):
    return {"key": key, "href": f"{reverse(url_name)}?{query}" if query else reverse(url_name),
            "title": title, "subtitle": subtitle, "value": value,
            "attention": bool(value) if attention is None else attention, "tone": tone}


def module_attention_cards(station, user) -> list[dict]:
    cards = []

    if station.fleet_enabled:
        from .fleet_models import Vehicle

        ready = set(Vehicle.READY_STATUSES)
        vehicles = list(Vehicle.objects.filter(station=station, is_active=True))
        if vehicles:
            not_ready = sum(1 for v in vehicles if v.tactical_status not in ready or v.is_disinfection_locked)
            due = sum(1 for v in vehicles if v.urgency["level"] in ATTENTION_LEVELS)
            # Die Zahl nennt den eigentlichen Grund: nicht einsatzbereite
            # Fahrzeuge zuerst, sonst fällige HU/UVV-Fristen. Nullen bleiben weg.
            if not_ready:
                subtitle = _("nicht einsatzbereit")
                if due:
                    subtitle += " · " + (_("1 Frist fällig") if due == 1 else _("%(due)s Fristen fällig") % {"due": due})
                cards.append(_card(
                    "fleet", "fleet_dashboard", "",
                    _("Fahrzeug") if not_ready == 1 else _("Fahrzeuge"),
                    subtitle, not_ready, tone="danger",
                ))
            else:
                cards.append(_card(
                    "fleet", "fleet_dashboard", "filter=urgent_inspections" if due else "",
                    _("Fahrzeugfrist") if due == 1 else _("Fahrzeugfristen"),
                    _("HU oder UVV fällig") if due else _("alle einsatzbereit"), due,
                ))

    if station.mpg_enabled:
        from .mpg_models import MedicalDevice

        devices = list(MedicalDevice.objects.filter(station=station).exclude(
            current_status=MedicalDevice.Status.DECOMMISSIONED,
        ))
        if devices:
            attention = sum(
                1 for d in devices
                if d.urgency["level"] in ATTENTION_LEVELS
                or d.current_status in (MedicalDevice.Status.OOB, MedicalDevice.Status.MAINTENANCE)
            )
            cards.append(_card(
                "mpg", "mpg_dashboard", "filter=urgent" if attention else "",
                _("Medizingerät") if attention == 1 else _("Medizingeräte"),
                _("Prüffrist fällig oder gesperrt"), attention,
            ))

    if station.warehouse_enabled:
        from .warehouse_models import ItemBatch, MedicalItem

        items = MedicalItem.objects.filter(station=station).annotate(
            stock=Sum("stock_items__quantity", filter=Q(stock_items__batch__is_recalled=False)),
        )
        if items.exists():
            low = sum(1 for item in items if (item.stock or 0) < item.min_stock)
            soon = timezone.localdate() + timedelta(days=30)
            expiring = ItemBatch.objects.filter(station=station, is_recalled=False, stock_items__quantity__gt=0).filter(
                Q(calculated_exp_date__lte=soon)
                | Q(calculated_exp_date__isnull=True, manufacturer_exp_date__lte=soon)
            ).distinct().count()
            if low:
                subtitle = _("unter Mindestbestand")
                if expiring:
                    subtitle += " · " + _("%(expiring)s Chargen verfallen bald") % {"expiring": expiring}
                cards.append(_card("warehouse", "warehouse_dashboard", "filter=low_stock",
                                   _("Artikel"), subtitle, low))
            else:
                cards.append(_card(
                    "warehouse", "warehouse_dashboard", "filter=urgent" if expiring else "",
                    _("Charge") if expiring == 1 else _("Chargen"),
                    _("verfallen in 30 Tagen") if expiring else _("Bestand ausreichend"), expiring,
                ))

    if station.orga_enabled:
        from .orga_models import SOPDocument

        sops = SOPDocument.list_with_ack_state(SOPDocument.objects.filter(
            station=station, status=SOPDocument.Status.ACTIVE, requires_acknowledgment=True,
        ), user)
        if sops:
            pending = sum(1 for sop in sops if not sop.user_has_acknowledged(user))
            cards.append(_card(
                "orga", "orga_dashboard", "filter=pending" if pending else "",
                _("Dienstanweisung") if pending == 1 else _("Dienstanweisungen"),
                _("von dir noch nicht quittiert"), pending,
            ))

    return cards
