"""Persistente Wachalltag-Modelle für die Mobile-/Web-API.

Die Modelle halten die Produktgrenze bewusst ein: keine Patienten-, Einsatz-,
Alarmierungs- oder Vorgangsdaten. Statusänderungen und Bewegungen werden in
append-only Ereignistabellen nachvollziehbar gemacht.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .models import Checklist, HandoverEntry, Station


def _require_same_station(parent, station_id, label):
    if parent is not None and station_id and parent.station_id != station_id:
        raise ValidationError(f"{label} und Wache müssen übereinstimmen.")


# Fachliche Rangfolge statt alphabetischer Sortierung der Schlüssel:
# offen → in Bearbeitung → wartend → erledigt, darin dringend → wichtig → normal.
# Abfragen mit GROUP BY (z. B. Anhangszählung) ignorieren Meta.ordering und
# müssen ``order_by(*DEFECT_WORKFLOW_ORDERING)`` selbst setzen.
DEFECT_WORKFLOW_ORDERING = [
    models.Case(
        models.When(status="open", then=0),
        models.When(status="in_progress", then=1),
        models.When(status="waiting", then=2),
        default=3,
        output_field=models.IntegerField(),
    ).asc(),
    models.Case(
        models.When(priority="urgent", then=0),
        models.When(priority="important", then=1),
        default=2,
        output_field=models.IntegerField(),
    ).asc(),
    models.F("due_at").asc(nulls_last=True),
    "-updated_at",
    "-id",
]


class Defect(models.Model):
    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Wichtig"
        URGENT = "urgent", "Dringend"

    class Status(models.TextChoices):
        OPEN = "open", "Offen"
        IN_PROGRESS = "in_progress", "In Bearbeitung"
        WAITING = "waiting", "Wartend"
        DONE = "done", "Erledigt"

    class Category(models.TextChoices):
        VEHICLE = "vehicle", "Fahrzeug"
        MATERIAL = "material", "Material"
        SAFETY = "safety", "Sicherheit"
        FACILITY = "facility", "Gebaeude"
        KEY = "key", "Schluessel"
        DEVICE = "device", "Geraet"
        TASK = "task", "Aufgabe"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="defects")
    title = models.CharField(max_length=160)
    description = models.TextField(max_length=3000, blank=True, default="")
    asset_ref = models.CharField(max_length=160, blank=True, default="")
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="owned_station_defects",
        null=True,
        blank=True,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.TASK)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_station_defects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Gesperrtes Medizinprodukt: Solange der Mangel offen ist, bleibt das Gerät
    # außer Betrieb (siehe core/device_status.py).
    medical_device = models.ForeignKey(
        "core.MedicalDevice",
        on_delete=models.SET_NULL,
        related_name="defects",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = DEFECT_WORKFLOW_ORDERING
        indexes = [
            models.Index(fields=["station", "status", "due_at"], name="defect_station_status_idx"),
            models.Index(fields=["station", "priority"], name="defect_station_prio_idx"),
        ]

    def __str__(self):
        return self.title


class DefectEvent(models.Model):
    class Kind(models.TextChoices):
        CREATED = "created", "Angelegt"
        UPDATED = "updated", "Bearbeitet"
        STATUS = "status", "Status"
        ATTACHMENT = "attachment", "Anhang"

    defect = models.ForeignKey(Defect, on_delete=models.PROTECT, related_name="events")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="defect_events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="defect_events")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "-created_at"], name="defect_event_station_idx")]

    @staticmethod
    def _status_label(value):
        return Defect.Status(value).label if value in Defect.Status.values else value

    @property
    def from_status_label(self):
        return self._status_label(self.from_status)

    @property
    def to_status_label(self):
        return self._status_label(self.to_status)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Mangel-Ereignisse dürfen nicht verändert werden.")
        _require_same_station(self.defect if self.defect_id else None, self.station_id, "Mangel-Ereignis")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Mangel-Ereignisse dürfen nicht gelöscht werden.")


class StationAsset(models.Model):
    class Kind(models.TextChoices):
        VEHICLE = "vehicle", "Fahrzeug"
        DEVICE = "device", "Geraet"
        KEY = "key", "Schluessel"

    class Status(models.TextChoices):
        READY = "ready", "Einsatzklar"
        LIMITED = "limited", "Eingeschraenkt"
        OOB = "oob", "Ausser Betrieb"
        WORKSHOP = "workshop", "Werkstatt"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="station_assets")
    asset_id = models.SlugField(max_length=64)
    label = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.DEVICE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.READY)
    note = models.CharField(max_length=300, blank=True, default="")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="updated_station_assets",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "label"]
        constraints = [
            models.UniqueConstraint(fields=["station", "asset_id"], name="unique_station_asset_id"),
        ]
        indexes = [models.Index(fields=["station", "status"], name="asset_station_status_idx")]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "status" in update_fields:
            from .device_status import mirror_to_device

            mirror_to_device(self)


class AssetEvent(models.Model):
    asset = models.ForeignKey(StationAsset, on_delete=models.PROTECT, related_name="events")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="asset_events")
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20)
    note = models.CharField(max_length=300, blank=True, default="")
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="asset_events")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Asset-Ereignisse dürfen nicht verändert werden.")
        _require_same_station(self.asset if self.asset_id else None, self.station_id, "Asset-Ereignis")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Asset-Ereignisse dürfen nicht gelöscht werden.")


class HandoverAck(models.Model):
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="handover_acks")
    handover = models.ForeignKey(HandoverEntry, on_delete=models.PROTECT, related_name="acknowledgements")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="handover_acknowledgements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["handover", "user"], name="unique_handover_user_ack"),
        ]
        indexes = [models.Index(fields=["station", "handover"], name="ack_station_handover_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Quittierungen dürfen nicht verändert werden.")
        _require_same_station(self.handover if self.handover_id else None, self.station_id, "Quittierung")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Quittierungen dürfen nicht gelöscht werden.")


class InventoryItem(models.Model):
    class Kind(models.TextChoices):
        KEY = "key", "Schluessel"
        DEVICE = "device", "Geraet"
        VEHICLE = "vehicle", "Fahrzeug"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="inventory_items")
    item_id = models.SlugField(max_length=64)
    label = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.DEVICE)
    holder = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="checked_out_station_items",
        null=True,
        blank=True,
    )
    checked_out_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, default="")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="updated_inventory_items",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "label"]
        constraints = [
            models.UniqueConstraint(fields=["station", "item_id"], name="unique_station_inventory_id"),
            models.CheckConstraint(
                condition=(
                    (Q(holder__isnull=True) & Q(checked_out_at__isnull=True))
                    | (Q(holder__isnull=False) & Q(checked_out_at__isnull=False))
                ),
                name="inventory_holder_time_match",
            ),
        ]

    def __str__(self):
        return self.label


class InventoryEvent(models.Model):
    class Action(models.TextChoices):
        CHECKOUT = "checkout", "Ausgabe"
        CHECKIN = "checkin", "Rueckgabe"

    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="events")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="inventory_events")
    action = models.CharField(max_length=20, choices=Action.choices)
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="inventory_events")
    holder = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="inventory_event_holdings",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "-created_at"], name="inventory_event_station_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Inventar-Ereignisse dürfen nicht verändert werden.")
        _require_same_station(self.item if self.item_id else None, self.station_id, "Inventar-Ereignis")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Inventar-Ereignisse dürfen nicht gelöscht werden.")


class ChecklistSchedule(models.Model):
    class Interval(models.TextChoices):
        DAILY = "daily", "Taeglich"
        WEEKLY = "weekly", "Woechentlich"
        MONTHLY = "monthly", "Monatlich"

    checklist = models.OneToOneField(Checklist, on_delete=models.PROTECT, related_name="schedule")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="checklist_schedules")
    interval = models.CharField(max_length=20, choices=Interval.choices)
    due_next = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_next", "checklist_id"]

    def clean(self):
        super().clean()
        _require_same_station(self.checklist if self.checklist_id else None, self.station_id, "Checklistenplan")

    def save(self, *args, **kwargs):
        _require_same_station(self.checklist if self.checklist_id else None, self.station_id, "Checklistenplan")
        super().save(*args, **kwargs)


class DefectAttachment(models.Model):
    """Kleiner Bildanhang im DB-Backend; bewusst kein allgemeines Dateiarchiv."""

    defect = models.ForeignKey(Defect, on_delete=models.PROTECT, related_name="attachments")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="defect_attachments")
    filename = models.CharField(max_length=180)
    content_type = models.CharField(max_length=40)
    data = models.BinaryField(editable=False)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="defect_attachments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["station", "defect"], name="attachment_station_def_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Mangel-Anhänge dürfen nicht verändert werden.")
        _require_same_station(self.defect if self.defect_id else None, self.station_id, "Anhang")
        # Endung folgt dem Inhaltstyp: Bilder als JPEG, PDFs als PDF.
        stem = (self.filename or "anhang").rsplit(".", 1)[0].strip(" .") or "anhang"
        # Bilder werden beim Speichern immer zu JPEG normalisiert; ohne diese
        # Regel bliebe eine irreführende Endung wie .png stehen.
        suffix = ".pdf" if self.content_type == "application/pdf" else ".jpg"
        self.filename = f"{stem[:170]}{suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Mangel-Anhänge dürfen nicht gelöscht werden.")
