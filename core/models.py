import calendar
from datetime import date, timedelta
from urllib.parse import urlparse
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Station(models.Model):
    class Profile(models.TextChoices):
        RESCUE = "rescue", "Rettungsdienst"
        FIRE = "fire", "Feuerwehr"
        POLICE = "police", "Polizei"
        GENERAL = "general", "Allgemein"

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    organization_profile = models.CharField(
        max_length=20,
        choices=Profile.choices,
        default=Profile.RESCUE,
        verbose_name="Organisationsprofil",
    )
    is_active = models.BooleanField(default=True)
    calendar_enabled = models.BooleanField(default=True, verbose_name="Kalender aktiviert")
    birthdays_enabled = models.BooleanField(default=True, verbose_name="Geburtstage aktiviert")
    coffee_enabled = models.BooleanField(default=True, verbose_name="Kaffeekasse aktiviert")
    feeds_enabled = models.BooleanField(default=False, verbose_name="Externe Meldungen aktiviert")
    tasks_enabled = models.BooleanField(default=True, verbose_name="Tagesaufgaben aktiviert")
    chat_enabled = models.BooleanField(default=True, verbose_name="Wachenchat aktiviert")
    pinboard_enabled = models.BooleanField(default=True, verbose_name="Pinnwand aktiviert")
    holidays_enabled = models.BooleanField(default=True, verbose_name="Feiertage (NRW) im Kalender")
    checklists_enabled = models.BooleanField(default=False, verbose_name="Checklisten aktiviert")
    waste_calendar_enabled = models.BooleanField(default=False, verbose_name="Muellkalender aktiviert")
    waste_calendar_url = models.URLField(blank=True, default="", max_length=600, verbose_name="Muellkalender-ICS-URL")
    more_order = models.CharField(
        max_length=400,
        blank=True,
        default="",
        verbose_name="Reihenfolge der Bereiche unter Mehr",
        help_text="Kommagetrennte Liste der Bausteine in gewünschter Reihenfolge.",
    )
    nav_order = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Reihenfolge der Hauptnavigation",
        help_text="Kommagetrennte Liste der Bereiche in gewünschter Reihenfolge.",
    )
    signal_group_url = models.URLField(
        blank=True,
        default="",
        max_length=600,
        verbose_name="Signal-Gruppe (Einladungslink)",
        help_text=(
            "Einladungslink zu einer Signal-Gruppe der Wache. Der Chat läuft "
            "bewusst außerhalb der App."
        ),
    )
    paypal_me_url = models.URLField(blank=True, default="", verbose_name="PayPal.me-Link")
    wero_link = models.URLField(blank=True, default="", verbose_name="Wero-Link")
    iban = models.CharField(max_length=34, blank=True, default="", verbose_name="IBAN")
    bic = models.CharField(max_length=12, blank=True, default="", verbose_name="BIC")
    payment_note = models.TextField(blank=True, default="", verbose_name="Zahlungshinweis")
    employee_count = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Mitarbeiterzahl"
    )
    street = models.CharField(max_length=120, blank=True, default="", verbose_name="Straße und Hausnummer")
    postal_code = models.CharField(max_length=10, blank=True, default="", verbose_name="Postleitzahl")
    city = models.CharField(max_length=80, blank=True, default="", verbose_name="Ort")
    latitude = models.FloatField(null=True, blank=True, verbose_name="Breitengrad")
    longitude = models.FloatField(null=True, blank=True, verbose_name="Längengrad")
    timezone_name = models.CharField(max_length=40, default="Europe/Berlin", verbose_name="Zeitzone")
    weather_enabled = models.BooleanField(default=False, verbose_name="Wettervorhersage aktiviert")
    traffic_enabled = models.BooleanField(
        default=False, verbose_name="Verkehrslage (Baustellen und Sperrungen)"
    )
    dwd_alerts_enabled = models.BooleanField(
        default=False,
        verbose_name="Amtliche DWD-Wetterwarnungen",
        help_text=(
            "Ruft Warnungen über Bright Sky ab. Dabei wird die auf zwei "
            "Nachkommastellen gerundete Koordinate der Wache übermittelt. "
            "Benötigt Koordinaten der Wache."
        ),
    )
    traffic_roads = models.CharField(
        max_length=60,
        blank=True,
        default="",
        verbose_name="Autobahnen und Bundesstraßen",
        help_text="Kommagetrennt, z. B. A2, A33. Benötigt Koordinaten der Wache.",
    )
    traffic_radius_km = models.PositiveSmallIntegerField(
        default=25, verbose_name="Umkreis in km"
    )
    traffic_warning_areas = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Gebiete für Bevölkerungswarnungen",
        help_text="Kommagetrennte Orts- oder Kreisnamen. Leer: Ort der Wache.",
    )
    traffic_local_sources = models.BooleanField(
        default=False,
        verbose_name="Kommunale Quellen Steinhagen und Kreis Gütersloh",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def get_default(cls):
        station = cls.objects.filter(slug=settings.DEFAULT_STATION_SLUG).first()
        if station is None and cls.objects.count() == 1:
            station = cls.objects.first()
        if station is None:
            station = cls.objects.create(
                slug=settings.DEFAULT_STATION_SLUG,
                name=settings.DEFAULT_STATION_NAME,
            )
        return station


class Membership(models.Model):
    class Role(models.TextChoices):
        MEMBER = "member", "Mitglied"
        SHIFT_LEAD = "shift_lead", "Schichtleitung"
        CASHIER = "cashier", "Kassenwart"
        ADMIN = "admin", "Master-Admin"
        AUDITOR = "auditor", "Auditor"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="station_memberships")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "station"], name="unique_station_membership"),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_active=True),
                name="unique_active_membership",
            ),
        ]
        ordering = ["station", "user_id"]

    def __str__(self):
        return f"{self.user} - {self.station} ({self.get_role_display()})"


class HandoverEntry(models.Model):
    class Category(models.TextChoices):
        STATION = "station", "Wache"
        VEHICLE = "vehicle", "Fahrzeugstatus"
        MATERIAL = "material", "Material"
        TASK = "task", "Offene Aufgabe"
        SAFETY = "safety", "Sicherheit/Mangel"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Wichtig"
        URGENT = "urgent", "Dringend"

    class Status(models.TextChoices):
        OPEN = "open", "Offen"
        IN_PROGRESS = "in_progress", "In Bearbeitung"
        DONE = "done", "Erledigt"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="handovers")
    category = models.CharField(max_length=20, choices=Category.choices)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    title = models.CharField(max_length=160)
    details = models.TextField(max_length=3000)
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="authored_handovers")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]
        indexes = [models.Index(fields=["station", "status", "-created_at"])]

    def __str__(self):
        return self.title


class HandoverRevision(models.Model):
    handover = models.ForeignKey(HandoverEntry, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["handover", "version"], name="unique_handover_version")
        ]
        ordering = ["-version"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Übergaberevisionen dürfen nicht verändert werden.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Übergaberevisionen dürfen nicht gelöscht werden.")


class NewsPost(models.Model):
    """Interne Neuigkeit der Wache, die gelesen und quittiert wird."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="news_posts")
    title = models.CharField(max_length=160)
    body = models.TextField(max_length=4000)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="authored_news"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "created_at"], name="news_station_created_idx")]

    def __str__(self):
        return self.title

    @property
    def is_archived(self):
        return self.archived_at is not None


class NewsAcknowledgement(models.Model):
    post = models.ForeignKey(
        NewsPost, on_delete=models.CASCADE, related_name="acknowledgements"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="news_acknowledgements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="unique_news_acknowledgement")
        ]


class NewsAttachment(models.Model):
    """Bild- oder PDF-Anhang einer Neuigkeit (unveränderlich)."""

    post = models.ForeignKey(NewsPost, on_delete=models.PROTECT, related_name="attachments")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="news_attachments")
    filename = models.CharField(max_length=180)
    content_type = models.CharField(max_length=40)
    data = models.BinaryField(editable=False)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="news_attachments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Anhänge dürfen nicht verändert werden.")
        if self.post_id and self.post.station_id != self.station_id:
            raise ValidationError("Anhang und Neuigkeit gehören zu verschiedenen Wachen.")
        from .api.wachalltag import ATTACHMENT_SUFFIX

        stem = (self.filename or "anhang").rsplit(".", 1)[0].strip(" .") or "anhang"
        suffix = ATTACHMENT_SUFFIX.get(self.content_type, ".bin")
        self.filename = f"{stem[:170]}{suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Anhänge dürfen nicht gelöscht werden.")


class PinboardAttachment(models.Model):
    """Bild- oder PDF-Anhang eines Aushangs."""

    note = models.ForeignKey(
        "PinboardNote", on_delete=models.PROTECT, related_name="attachments"
    )
    station = models.ForeignKey(
        Station, on_delete=models.PROTECT, related_name="pinboard_attachments"
    )
    filename = models.CharField(max_length=180)
    content_type = models.CharField(max_length=40)
    data = models.BinaryField(editable=False)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="pinboard_attachments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Anhänge dürfen nicht verändert werden.")
        if self.note_id and self.note.station_id != self.station_id:
            raise ValidationError("Anhang und Aushang gehören zu verschiedenen Wachen.")
        from .api.wachalltag import ATTACHMENT_SUFFIX

        stem = (self.filename or "anhang").rsplit(".", 1)[0].strip(" .") or "anhang"
        suffix = ATTACHMENT_SUFFIX.get(self.content_type, ".bin")
        self.filename = f"{stem[:170]}{suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Anhänge dürfen nicht gelöscht werden.")


class HandoverAttachment(models.Model):
    """Bild- oder PDF-Anhang einer Übergabe (unveränderlich, wachengebunden)."""

    handover = models.ForeignKey(
        HandoverEntry, on_delete=models.PROTECT, related_name="attachments"
    )
    station = models.ForeignKey(
        Station, on_delete=models.PROTECT, related_name="handover_attachments"
    )
    filename = models.CharField(max_length=180)
    content_type = models.CharField(max_length=40)
    data = models.BinaryField(editable=False)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="handover_attachments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["station", "handover"], name="handover_att_station_idx"
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Übergabe-Anhänge dürfen nicht verändert werden.")
        if self.handover_id and self.handover.station_id != self.station_id:
            raise ValidationError("Anhang und Übergabe gehören zu verschiedenen Wachen.")
        from .api.wachalltag import ATTACHMENT_SUFFIX

        stem = (self.filename or "anhang").rsplit(".", 1)[0].strip(" .") or "anhang"
        suffix = ATTACHMENT_SUFFIX.get(self.content_type, ".bin")
        self.filename = f"{stem[:170]}{suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Übergabe-Anhänge dürfen nicht gelöscht werden.")


class CalendarEvent(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="calendar_events")
    title = models.CharField(max_length=160)
    description = models.TextField(max_length=1500, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            raise ValidationError({"ends_at": "Das Ende darf nicht vor dem Beginn liegen."})

    def __str__(self):
        return self.title


class WasteCollection(models.Model):
    """Abfuhrtermin aus dem stationsspezifischen Muellkalender-ICS-Fallback."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="waste_collections")
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["station", "starts_at"], name="waste_coll_station_idx")]

    def __str__(self):
        return self.title


class BirthdayPreference(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="birthday_preferences")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="birthdays")
    day = models.PositiveSmallIntegerField(null=True, blank=True)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    is_visible = models.BooleanField(default=False)
    consented_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "station"], name="unique_station_birthday")
        ]

    def clean(self):
        if self.is_visible and (not self.day or not self.month):
            raise ValidationError("Für die Anzeige werden Tag und Monat benötigt.")
        if self.day and not 1 <= self.day <= 31:
            raise ValidationError({"day": "Ungültiger Tag."})
        if self.month and not 1 <= self.month <= 12:
            raise ValidationError({"month": "Ungültiger Monat."})
        if self.day and self.month:
            try:
                # Schaltjahr, damit der 29. Februar zulaessig bleibt.
                date(2000, self.month, self.day)
            except ValueError as exc:
                raise ValidationError("Tag und Monat ergeben kein gültiges Datum.") from exc


class CoffeeEntry(models.Model):
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="coffee_entries")
    member = models.ForeignKey(User, on_delete=models.PROTECT, related_name="coffee_entries")
    amount_cents = models.IntegerField()
    reason = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_coffee_entries")
    correction_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(amount_cents=0), name="coffee_amount_nonzero"),
            models.UniqueConstraint(
                fields=["correction_of"],
                condition=Q(correction_of__isnull=False),
                name="unique_coffee_correction",
            ),
        ]

    def clean(self):
        if self.correction_of:
            if self.correction_of.station_id != self.station_id:
                raise ValidationError("Die Korrektur muss zur gleichen Wache gehören.")
            if self.correction_of.member_id != self.member_id:
                raise ValidationError("Die Korrektur muss dieselbe Person betreffen.")
            if self.amount_cents != -self.correction_of.amount_cents:
                raise ValidationError("Eine Korrektur muss den exakten Gegenbetrag buchen.")
            if self.correction_of.correction_of_id:
                raise ValidationError("Eine Korrekturbuchung kann nicht erneut korrigiert werden.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Kassenbuchungen dürfen nicht verändert werden.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Kassenbuchungen dürfen nicht gelöscht werden.")

    @property
    def amount_euros(self):
        return self.amount_cents / 100


class StationTask(models.Model):
    """Wachaufgaben analog zur Wandtafel: gruen taeglich, gelb Wochentag, blau zusaetzlich."""

    class Band(models.TextChoices):
        DAILY = "daily", "Täglich"
        WEEKDAY = "weekday", "Wochentag"
        EXTRA = "extra", "Zusätzlich"

    WEEKDAY_LABELS = (
        (0, "Montag"),
        (1, "Dienstag"),
        (2, "Mittwoch"),
        (3, "Donnerstag"),
        (4, "Freitag"),
        (5, "Samstag"),
        (6, "Sonntag"),
    )

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="station_tasks")
    title = models.CharField(max_length=160)
    band = models.CharField(max_length=20, choices=Band.choices, default=Band.DAILY)
    weekday = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=WEEKDAY_LABELS,
        help_text="Nur für Wochentagsaufgaben nötig (0=Montag).",
    )
    class Repeat(models.TextChoices):
        ONCE = "once", "Einmalig"
        DAILY = "daily", "Täglich"
        WEEKLY = "weekly", "Wöchentlich"
        MONTHLY = "monthly", "Monatlich"

    color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Eigene Farbe als Hex-Wert (z. B. #1f7a4d). Leer = Farbe des Bereichs.",
    )
    repeat = models.CharField(
        max_length=10,
        choices=Repeat.choices,
        default=Repeat.DAILY,
        help_text="Wie oft die Aufgabe fällig wird – analog zu Kalendereinträgen.",
    )
    repeat_interval = models.PositiveSmallIntegerField(
        default=1,
        help_text="Jede 1., 2., 3. … Wiederholung (Tag, Woche oder Monat).",
    )
    weekdays = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Mehrere Wochentage als Zahlen, z. B. 0,2,4 (Montag = 0).",
    )
    month_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Tag im Monat (1–31). 31 trifft den letzten Tag eines kürzeren Monats.",
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Erster möglicher Termin; Bezugspunkt für Wiederholungen.",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Letzter möglicher Termin (optional).",
    )
    notes = models.CharField(max_length=240, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["band", "weekday", "sort_order", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        # Die Pflichtfelder je Wiederholungsart prüft das Formular; hier bleibt
        # nur die Prüfung, die ohne Formularkontext immer gilt.
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Der letzte Termin liegt vor dem ersten."})

    def weekday_list(self):
        """Wochentage als Liste von 0 (Montag) bis 6 (Sonntag)."""
        values = []
        for raw in (self.weekdays or "").split(","):
            raw = raw.strip()
            if raw.isdigit() and 0 <= int(raw) <= 6 and int(raw) not in values:
                values.append(int(raw))
        if not values and self.weekday is not None:
            values.append(self.weekday)
        return sorted(values)

    def set_weekdays(self, days):
        cleaned = sorted({int(day) for day in days if 0 <= int(day) <= 6})
        self.weekdays = ",".join(str(day) for day in cleaned)
        self.weekday = cleaned[0] if cleaned else None
        return cleaned

    def applies_to_date(self, work_date):
        if not self.is_active:
            return False
        if self.start_date and work_date < self.start_date:
            return False
        if self.end_date and work_date > self.end_date:
            return False
        repeat = self.repeat or self.Repeat.DAILY
        interval = max(1, self.repeat_interval or 1)
        anchor = self.start_date
        if repeat == self.Repeat.ONCE:
            return anchor == work_date
        if repeat == self.Repeat.DAILY:
            if anchor is None:
                return True
            return (work_date - anchor).days % interval == 0
        if repeat == self.Repeat.WEEKLY:
            if work_date.weekday() not in self.weekday_list():
                return False
            if anchor is None:
                return True
            anchor_monday = anchor - timedelta(days=anchor.weekday())
            weeks = (work_date - anchor_monday).days // 7
            return weeks >= 0 and weeks % interval == 0
        if repeat == self.Repeat.MONTHLY:
            if self.month_day is None:
                return False
            last_day = calendar.monthrange(work_date.year, work_date.month)[1]
            if work_date.day != min(self.month_day, last_day):
                return False
            if anchor is None:
                return True
            months = (work_date.year - anchor.year) * 12 + (work_date.month - anchor.month)
            return months >= 0 and months % interval == 0
        return True

    @property
    def display_color(self):
        return self.color if self.color else ""

    @property
    def band_css(self):
        return {
            self.Band.DAILY: "band-daily",
            self.Band.WEEKDAY: "band-weekday",
            self.Band.EXTRA: "band-extra",
        }.get(self.band, "band-extra")


class StationTaskCompletion(models.Model):
    task = models.ForeignKey(StationTask, on_delete=models.CASCADE, related_name="completions")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="task_completions")
    work_date = models.DateField()
    completed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="station_task_completions"
    )
    completed_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-work_date", "-completed_at"]
        constraints = [
            models.UniqueConstraint(fields=["task", "work_date"], name="unique_task_completion_day"),
        ]

    def __str__(self):
        return f"{self.task_id} @ {self.work_date}"


class FeedSource(models.Model):
    class Kind(models.TextChoices):
        NEWS_RSS = "news_rss", "Nachrichten (RSS)"
        CLOSURE_CSV = "closure_csv", "Verkehrsmeldungen (CSV)"

    name = models.CharField(max_length=120, unique=True)
    url = models.URLField(max_length=600)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    locality = models.CharField(max_length=80)
    attribution = models.CharField(max_length=200)
    is_enabled = models.BooleanField(default=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        parsed = urlparse(self.url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValidationError({"url": "Die Portangabe ist ungültig."}) from exc
        if parsed.scheme != "https" or port not in {None, 443}:
            raise ValidationError({"url": "Quellen müssen HTTPS auf Port 443 verwenden."})
        if parsed.hostname not in settings.FEED_ALLOWED_HOSTS:
            raise ValidationError({
                "url": "Der Host muss zuerst in FEED_ALLOWED_HOSTS freigegeben werden."
            })


class FeedItem(models.Model):
    source = models.ForeignKey(FeedSource, on_delete=models.CASCADE, related_name="items")
    external_id = models.CharField(max_length=300)
    title = models.CharField(max_length=300)
    summary = models.TextField(max_length=1500, blank=True)
    url = models.URLField(max_length=600, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    first_imported_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "external_id"], name="unique_feed_item")
        ]
        ordering = [F("published_at").desc(nulls_last=True), "-last_seen_at"]
        indexes = [models.Index(fields=["source", "-published_at"])]

    def __str__(self):
        return self.title


class TotpDevice(models.Model):
    """Optional TOTP second factor for a local account (RFC 6238)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="totp_device")
    secret = models.CharField(max_length=255)
    is_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        state = "aktiv" if self.is_confirmed else "unbestätigt"
        return f"TOTP {self.user_id} ({state})"


class WebAuthnCredential(models.Model):
    """Passkey / WebAuthn public-key credential for phishing-resistant login or MFA."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="webauthn_credentials")
    credential_id = models.CharField(max_length=512, unique=True)
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    device_name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.device_name or f"Passkey {self.pk}"


class PushSubscription(models.Model):
    """Browser Web-Push subscription for urgent station alerts."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["endpoint"], name="unique_push_endpoint"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Push {self.user_id}@{self.station_id}"


class PushOutbox(models.Model):
    """Transactional outbox row for Web-Push delivery.

    A request that creates an urgent handover writes one PushOutbox per
    subscription in the same DB transaction. A separate worker picks the
    rows, performs the external HTTP call, and updates the status. The
    Gunicorn request never opens a network connection to a push service.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DISCARDED = "discarded", "Discarded"

    BACKOFF_SECONDS = (60, 300, 900, 3600, 21600)
    MAX_ATTEMPTS = 10
    RETENTION_DAYS = 30

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="push_outbox")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_outbox")
    # SET_NULL keeps the forensic outbox row when a subscription is purged.
    # The worker nulls the reference first so the cascade never fires.
    subscription = models.ForeignKey(
        PushSubscription, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="outbox_entries",
    )
    payload = models.JSONField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["station", "status"]),
        ]

    def __str__(self):
        return f"PushOutbox {self.id} ({self.status})"

    @property
    def next_backoff_seconds(self) -> int:
        """Return the wait time for the next attempt.

        ``attempts`` counts the deliveries that already failed. After the
        first failure we wait ``BACKOFF_SECONDS[0]`` (60s), after the second
        ``BACKOFF_SECONDS[1]`` (5 min), and so on. Beyond the defined
        schedule the last step is reused so ``MAX_ATTEMPTS`` still leaves
        room for a final retry.
        """
        idx = min(self.attempts, len(self.BACKOFF_SECONDS) - 1)
        return self.BACKOFF_SECONDS[idx]


class CalendarFeedToken(models.Model):
    """Read-only token for external calendar apps (webcal/ICS subscribe)."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="calendar_feed_tokens")
    token = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="calendar_feed_tokens")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.label or f"Kalender-Abo {self.pk}"


class ApiToken(models.Model):
    """Revocable app token for /api/v1/ (Paperless/Nextcloud-style mobile clients)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    label = models.CharField(max_length=120)
    token_prefix = models.CharField(max_length=16)
    token_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label} ({self.token_prefix}…)"


class RegistrationRequest(models.Model):
    """Optional self-service signup waiting for Master-Admin approval."""

    class Status(models.TextChoices):
        PENDING = "pending", "Wartend"
        APPROVED = "approved", "Freigegeben"
        REJECTED = "rejected", "Abgelehnt"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="registration_request")
    preferred_station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_requests",
    )
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_registrations",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Registrierung {self.user_id} ({self.status})"


class UserProfile(models.Model):
    """Personal extras for /konto/. Avatar bytes only – no general uploads."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    # Bevorzugte UI-Sprache (ISO-639-1); leer = Systemstandard.
    language = models.CharField(
        max_length=8,
        blank=True,
        default="",
        help_text="Bevorzugte UI-Sprache (ISO-639-1); leer = Systemstandard.",
    )
    avatar = models.BinaryField(null=True, blank=True, editable=False)
    avatar_content_type = models.CharField(max_length=32, blank=True, default="")
    avatar_updated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.language:
            valid_codes = {code for code, _ in settings.LANGUAGES}
            if self.language not in valid_codes:
                raise ValidationError({"language": f"Ungültige Sprache '{self.language}'."})

    def __str__(self):
        return f"Profil {self.user_id}"

    @property
    def has_avatar(self):
        return bool(self.avatar)

    @classmethod
    def for_user(cls, user):
        profile, _ = cls.objects.get_or_create(user=user)
        return profile


class UserCryptoIdentity(models.Model):
    """Public identity + passphrase-wrapped private key for E2EE messaging."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="crypto")
    public_jwk = models.JSONField()
    wrapped_private_jwk = models.TextField()
    kdf_salt = models.CharField(max_length=128)
    kdf_iterations = models.PositiveIntegerField(default=210_000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Crypto {self.user_id}"


class ChatMessage(models.Model):
    """Station-scoped short colleague messages. Bodies are E2EE ciphertext when encrypted."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="chat_messages")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="chat_messages")
    body = models.TextField(max_length=1000, blank=True, default="")
    ciphertext = models.TextField(blank=True, default="")
    nonce = models.CharField(max_length=64, blank=True, default="")
    key_wraps = models.JSONField(default=dict, blank=True)
    algo = models.CharField(max_length=40, blank=True, default="")
    is_encrypted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "-created_at"])]

    def __str__(self):
        return f"Chat {self.pk}"


class PrivateConversation(models.Model):
    """1:1 private thread. Only the two participants can fetch ciphertext."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="private_conversations")
    user_low = models.ForeignKey(User, on_delete=models.CASCADE, related_name="private_conversations_low")
    user_high = models.ForeignKey(User, on_delete=models.CASCADE, related_name="private_conversations_high")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["station", "user_low", "user_high"],
                name="unique_private_conversation_pair",
            ),
            models.CheckConstraint(
                condition=~Q(user_low=F("user_high")),
                name="private_conversation_distinct_users",
            ),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Privat {self.pk}"

    def other_user(self, user):
        return self.user_high if user.id == self.user_low_id else self.user_low


class PrivateMessage(models.Model):
    conversation = models.ForeignKey(
        PrivateConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="private_messages")
    ciphertext = models.TextField()
    nonce = models.CharField(max_length=64)
    key_wraps = models.JSONField(default=dict)
    algo = models.CharField(max_length=40, default="A256GCM+ECDH-ES")
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["conversation", "-created_at"])]

    @property
    def is_encrypted(self):
        return True

    def __str__(self):
        return f"PrivateMessage {self.pk}"


class SecureMail(models.Model):
    """Encrypted internal mail. Only sender and recipients hold key wraps."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="secure_mails")
    sender = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sent_secure_mails")
    ciphertext = models.TextField()
    nonce = models.CharField(max_length=64)
    key_wraps = models.JSONField(default=dict)
    algo = models.CharField(max_length=40, default="A256GCM+ECDH-ES")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "-created_at"])]

    @property
    def is_encrypted(self):
        return True

    @property
    def author_id(self):
        return self.sender_id

    def __str__(self):
        return f"SecureMail {self.pk}"


class SecureMailRecipient(models.Model):
    mail = models.ForeignKey(SecureMail, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_secure_mails")
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["mail", "user"], name="unique_secure_mail_recipient"),
        ]

    def __str__(self):
        return f"MailRecipient {self.mail_id}:{self.user_id}"


class Checklist(models.Model):
    """Wiederkehrende Prüfvorlage einer Wache (admin-gepflegt)."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="checklists")
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class ChecklistItem(models.Model):
    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=200)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.text


class ChecklistCompletion(models.Model):
    """Append-only Abschluss einer Checkliste."""

    station = models.ForeignKey(
        Station, on_delete=models.PROTECT, related_name="checklist_completions"
    )
    checklist = models.ForeignKey(
        Checklist, on_delete=models.PROTECT, related_name="completions"
    )
    completed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="checklist_completions"
    )
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "-created_at"])]

    def clean(self):
        super().clean()
        if self.checklist_id and self.station_id and self.checklist.station_id != self.station_id:
            raise ValidationError("Checkliste gehört nicht zu dieser Wache.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Checklisten-Abschlüsse dürfen nicht verändert werden.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Checklisten-Abschlüsse dürfen nicht gelöscht werden.")


class AuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    station = models.ForeignKey(Station, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["station", "-created_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit-Ereignisse dürfen nicht verändert werden.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit-Ereignisse dürfen nicht gelöscht werden.")


class RateLimit(models.Model):
    bucket = models.CharField(max_length=64)
    key_hash = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("bucket", "key_hash", "window_start"),)
        indexes = [
            models.Index(fields=["bucket", "window_start"]),
        ]

    def __str__(self):
        return f"{self.bucket}:{self.key_hash}:{self.window_start.isoformat()}"


class ChatGroup(models.Model):
    """Station-scoped group chat room. Messages are E2EE ciphertext, wrapped for
    every current member who has keys (plus the author)."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="chat_groups")
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_chat_groups"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class ChatGroupMember(models.Model):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_group_memberships")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="unique_chat_group_member"),
        ]
        ordering = ["id"]


class GroupMessage(models.Model):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="group_messages")
    ciphertext = models.TextField()
    nonce = models.CharField(max_length=64)
    key_wraps = models.JSONField(default=dict)
    algo = models.CharField(max_length=40, default="A256GCM+ECDH-ES")
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def is_encrypted(self):
        return True

    def __str__(self):
        return f"GroupMessage({self.group_id})"


class PinboardNote(models.Model):
    """Stationsinterne Pinnwand fuer kurze Aushaenge/Hinweise.

    Bewusst getrennt von den strukturierten Uebergaben und ausserhalb der
    Einsatz-/Patienten-Domaene (nur Wachalltag-Organisation). Aenderungen werden
    ueber ``services`` auditiert.
    """

    class Category(models.TextChoices):
        INFO = "info", "Info"
        IMPORTANT = "important", "Wichtig"
        EVENT = "event", "Termin/Hinweis"

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="pinboard_notes")
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="pinboard_notes"
    )
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=2000)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.INFO)
    is_pinned = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-updated_at"]
        indexes = [
            models.Index(fields=["station", "is_archived", "-is_pinned", "-updated_at"]),
        ]

    def __str__(self):
        return self.title
class AppVersion(models.Model):
    """Stores version information for different platforms with changelogs."""

    class Platform(models.TextChoices):
        WEB = "web", "Web"
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        verbose_name="Plattform"
    )
    version = models.CharField(max_length=20, verbose_name="Version")
    version_code = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Versionscode"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Aktiv",
        help_text="Nur aktive Versionen werden für Updates angezeigt"
    )
    release_date = models.DateField(verbose_name="Veröffentlichungsdatum")
    download_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="Download-URL",
        help_text="URL zum Herunterladen dieser Version"
    )
    changelog = models.TextField(
        blank=True,
        verbose_name="Änderungsprotokoll",
        help_text="Markdown-Format: ## Version (Datum)\n- Änderung 1\n- Änderung 2"
    )
    is_forced = models.BooleanField(
        default=False,
        verbose_name="Erzwungenes Update",
        help_text="Nutzer müssen diese Version installieren"
    )
    min_required_version = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Mindestversion",
        help_text="Nutzer mit älteren Versionen müssen updaten"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Aktualisiert am")

    class Meta:
        ordering = ["-release_date"]
        unique_together = ["platform", "version"]
        verbose_name = "App-Version"
        verbose_name_plural = "App-Versionen"

    def __str__(self):
        return f"{self.get_platform_display()} {self.version}"

    @property
    def parsed_changelog(self) -> list[dict]:
        """Parse the changelog text into structured data."""
        import re
        if not self.changelog:
            return []

        lines = self.changelog.strip().split('\n')
        result = []
        current_entry = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this is a version header (e.g., "## 0.15.0 (2026-08-05)")
            version_match = re.match(r'^##\s*(\d+\.\d+\.\d+)\s*\(([^)]+)\)$', line)
            if version_match:
                if current_entry is not None:
                    result.append(current_entry)
                current_entry = {
                    "version": version_match.group(1),
                    "date": version_match.group(2),
                    "changes": [],
                }
            elif line.startswith('- ') or line.startswith('• ') or line.startswith('* '):
                # This is a change item
                if current_entry is not None:
                    change_text = line[2:].strip() if line.startswith('- ') else line[1:].strip()
                    current_entry["changes"].append(change_text)
            else:
                # This is a regular line - add to last change
                if current_entry is not None and current_entry["changes"]:
                    current_entry["changes"][-1] += ' ' + line

        if current_entry is not None:
            result.append(current_entry)

        return result


class InstallationSetup(models.Model):
    """Singleton guard for the one-time first installation.

    The row is created lazily. ``completed_at`` is claimed with a conditional
    UPDATE inside the same transaction that creates station and admin user, so
    a second concurrent completion cannot create a second installation.
    """

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    station = models.OneToOneField(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installation_setup",
    )
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # SHA-256 hex of the bootstrap token that completed the setup. The raw
    # token is never stored, logged or rendered.
    bootstrap_fingerprint = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(singleton=1), name="installation_setup_singleton"),
        ]

    def __str__(self):
        return "Erstinstallation abgeschlossen" if self.completed_at else "Erstinstallation offen"


class EmployeeActivation(models.Model):
    """One-time, expiring, revocable account activation for one employee.

    Only the SHA-256 hash of the raw token is persisted. Consumption is an
    atomic conditional UPDATE, so replay and parallel double-use both fail.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="employee_activations")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="employee_activations")
    token_hash = models.CharField(max_length=64, unique=True)
    # Only invitable roles are valid here; ``consume_activation`` also enforces
    # this whitelist so a tampered row can never grant admin/auditor rights.
    role = models.CharField(
        max_length=20,
        choices=[
            (Membership.Role.MEMBER, Membership.Role.MEMBER.label),
            (Membership.Role.SHIFT_LEAD, Membership.Role.SHIFT_LEAD.label),
            (Membership.Role.CASHIER, Membership.Role.CASHIER.label),
        ],
        default=Membership.Role.MEMBER,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(used_at__isnull=True, revoked_at__isnull=True),
                name="unique_open_activation_per_user",
            ),
        ]

    def __str__(self):
        return f"Aktivierung {self.user_id} ({self.station_id})"

    @property
    def is_open(self):
        from django.utils import timezone as _tz

        return (
            self.used_at is None
            and self.revoked_at is None
            and self.expires_at > _tz.now()
        )


class QrLoginRequest(models.Model):
    class State(models.TextChoices):
        CREATED = "created", "Erstellt"
        SCANNED = "scanned", "Gescannt"
        APPROVED = "approved", "Freigegeben"
        DENIED = "denied", "Abgelehnt"
        EXPIRED = "expired", "Abgelaufen"
        REVOKED = "revoked", "Widerrufen"
        CONSUMED = "consumed", "Verbraucht"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    secret_hash = models.CharField(max_length=64)
    manual_code_hash = models.CharField(max_length=64, unique=True)
    browser_session_hash = models.CharField(max_length=64)
    browser_nonce_hash = models.CharField(max_length=64)
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="qr_login_requests")
    origin = models.CharField(max_length=255)
    state = models.CharField(max_length=16, choices=State.choices, default=State.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_qr_logins"
    )
    approved_session_hash = models.CharField(max_length=64, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    check_word = models.CharField(max_length=32)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["state", "expires_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"QR-Login {self.id} ({self.state})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class QrTotpUse(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="qr_totp_uses")
    time_step = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "time_step"], name="unique_user_totp_step"),
        ]

    def __str__(self):
        return f"QrTotpUse {self.user_id}:{self.time_step}"


# Die Wiki-Modelle liegen in einem eigenen Modul. Der Import an dieser Stelle
# registriert sie fuer Django, ohne die bestehende Modelldatei zu vergroessern.
from .wiki_models import WikiArticle, WikiRevision  # noqa: E402,F401

# Bereinigte technische Fehlerereignisse (H4) liegen in einem eigenen Modul.
from .diagnostics_models import ErrorEvent  # noqa: E402,F401

# Widerrufbare Display-Zugaenge fuer Wandmonitore liegen in einem eigenen Modul.
from .display_models import DisplayToken  # noqa: E402,F401
