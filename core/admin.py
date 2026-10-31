from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import (
    AppVersion,
    AuditEvent,
    BirthdayPreference,
    CalendarEvent,
    Checklist,
    ChecklistCompletion,
    ChecklistItem,
    CoffeeEntry,
    FeedItem,
    FeedSource,
    HandoverEntry,
    HandoverRevision,
    Membership,
    Station,
    StationTask,
    StationTaskCompletion,
    WasteCollection,
)
from .privacy_models import DataProtectionOfficer


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DataProtectionOfficerInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_primary = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            if form.cleaned_data.get("is_active") and form.cleaned_data.get("is_primary"):
                active_primary += 1
        if active_primary > 1:
            raise ValidationError(
                "Pro Wache darf nur ein aktiver Datenschutz-Hauptkontakt hinterlegt sein."
            )


class DataProtectionOfficerInline(admin.StackedInline):
    model = DataProtectionOfficer
    formset = DataProtectionOfficerInlineFormSet
    extra = 0
    fields = (
        "display_name",
        "organization",
        "email",
        "phone",
        "postal_address",
        "is_external",
        "is_primary",
        "is_active",
        "publish_in_privacy_notice",
        "internal_notes",
    )
    verbose_name = "Datenschutzbeauftragte/r"
    verbose_name_plural = "Datenschutzbeauftragte / Datenschutzkontakte"


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "is_active",
        "calendar_enabled",
        "birthdays_enabled",
        "coffee_enabled",
        "feeds_enabled",
        "tasks_enabled",
        "checklists_enabled",
        "waste_calendar_enabled",
    )
    list_filter = ("is_active",)
    inlines = [DataProtectionOfficerInline]

    def get_readonly_fields(self, request, obj=None):
        return ("slug",) if obj else ()


@admin.register(DataProtectionOfficer)
class DataProtectionOfficerAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "station",
        "organization",
        "email",
        "is_external",
        "is_primary",
        "is_active",
        "publish_in_privacy_notice",
        "updated_at",
    )
    list_filter = (
        "station",
        "is_external",
        "is_primary",
        "is_active",
        "publish_in_privacy_notice",
    )
    search_fields = ("display_name", "organization", "email", "phone")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Zuordnung",
            {"fields": ("station", "display_name", "organization", "is_external")},
        ),
        (
            "Kontakt",
            {"fields": ("email", "phone", "postal_address")},
        ),
        (
            "Veröffentlichung",
            {
                "fields": (
                    "is_primary",
                    "is_active",
                    "publish_in_privacy_notice",
                ),
                "description": (
                    "Nur als veröffentlichbar markierte aktive Datensätze erscheinen auf "
                    "der öffentlichen Datenschutzseite. Interne Notizen werden nie ausgegeben."
                ),
            },
        ),
        (
            "Intern",
            {"fields": ("internal_notes", "created_at", "updated_at")},
        ),
    )


@admin.register(Membership)
class MembershipAdmin(ReadOnlyAdmin):
    list_display = ("user", "station", "role", "is_active")
    list_filter = ("station", "role", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(HandoverEntry)
class HandoverAdmin(ReadOnlyAdmin):
    list_display = ("title", "station", "category", "priority", "status", "updated_at")
    list_filter = ("station", "category", "priority", "status")


@admin.register(HandoverRevision)
class HandoverRevisionAdmin(ReadOnlyAdmin):
    list_display = ("handover", "version", "changed_by", "created_at")


@admin.register(CalendarEvent)
class CalendarEventAdmin(ReadOnlyAdmin):
    list_display = ("title", "station", "starts_at", "ends_at", "created_by")
    list_filter = ("station",)


@admin.register(WasteCollection)
class WasteCollectionAdmin(ReadOnlyAdmin):
    list_display = ("title", "station", "starts_at", "ends_at")
    list_filter = ("station",)


@admin.register(BirthdayPreference)
class BirthdayPreferenceAdmin(ReadOnlyAdmin):
    list_display = ("user", "station", "is_visible", "updated_at")
    list_filter = ("station", "is_visible")


@admin.register(CoffeeEntry)
class CoffeeEntryAdmin(ReadOnlyAdmin):
    list_display = ("member", "amount_cents", "reason", "created_by", "created_at")
    list_filter = ("station",)


@admin.register(StationTask)
class StationTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "station", "band", "weekday", "is_active", "sort_order")
    list_filter = ("station", "band", "is_active")
    search_fields = ("title", "notes")


@admin.register(StationTaskCompletion)
class StationTaskCompletionAdmin(ReadOnlyAdmin):
    list_display = ("task", "station", "work_date", "completed_by", "completed_at")
    list_filter = ("station", "work_date")


@admin.register(FeedSource)
class FeedSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "locality", "is_enabled", "last_success_at")
    list_filter = ("kind", "is_enabled")
    readonly_fields = ("last_success_at", "last_error_at", "last_error")


@admin.register(FeedItem)
class FeedItemAdmin(ReadOnlyAdmin):
    list_display = ("title", "source", "published_at", "first_imported_at", "last_seen_at")
    list_filter = ("source",)


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 3


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ("title", "station", "is_active", "created_at")
    list_filter = ("station", "is_active")
    search_fields = ("title",)
    readonly_fields = ("created_at",)
    inlines = [ChecklistItemInline]


@admin.register(ChecklistCompletion)
class ChecklistCompletionAdmin(ReadOnlyAdmin):
    list_display = ("checklist", "station", "completed_by", "created_at")
    list_filter = ("station",)


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "actor", "station", "action", "object_type", "object_id")
    list_filter = ("station", "action", "object_type")


admin.site.site_header = "Wachbuch-Verwaltung"
admin.site.site_title = "Wachbuch"


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = (
        "platform",
        "version",
        "version_code",
        "is_active",
        "is_forced",
        "release_date",
    )
    list_filter = ("platform", "is_active", "is_forced")
    search_fields = ("platform", "version")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("platform", "version", "version_code", "is_active", "is_forced")
        }),
        ("Veröffentlichung", {
            "fields": ("release_date", "download_url", "min_required_version")
        }),
        ("Änderungsprotokoll", {
            "fields": ("changelog",)
        }),
        ("Metadaten", {
            "fields": ("created_at", "updated_at")
        }),
    )


from django import forms  # noqa: E402
from django.utils.translation import gettext_lazy as _  # noqa: E402

from .fleet_models import DisinfectantMaster  # noqa: E402


class DisinfectantMasterAdminForm(forms.ModelForm):
    class Meta:
        model = DisinfectantMaster
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        station = cleaned_data.get("station")
        if station is None and self.instance.station_id:
            station = self.instance.station
        if station is not None and cleaned_data.get("is_active") is False:
            others = DisinfectantMaster.objects.filter(station=station, is_active=True)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if not others.exists():
                # Ohne Mittel in Gebrauch ließe sich keine Desinfektion mehr erfassen.
                raise ValidationError({"is_active": _(
                    "Mindestens ein Mittel muss in Gebrauch bleiben, sonst kann niemand eine Desinfektion "
                    "erfassen. Bitte zuerst ein anderes Mittel auf „In Gebrauch“ setzen."
                )})
        return cleaned_data


@admin.register(DisinfectantMaster)
class DisinfectantMasterAdmin(admin.ModelAdmin):
    """Desinfektionsmittel je Wache: Name, Wirkspektrum und Einwirkzeit.

    Nicht löschen, sondern „In Gebrauch“ abwählen: Desinfektionsprotokolle
    verweisen auf das Mittel und bleiben als Nachweis erhalten.
    """

    form = DisinfectantMasterAdminForm
    list_display = ("name", "station", "default_exposure_minutes", "is_vah_listed", "is_active")
    list_filter = ("station", "is_vah_listed", "is_active")
    search_fields = ("name", "manufacturer")

    def has_delete_permission(self, request, obj=None):
        return False


from .notification_models import SignalOutbox  # noqa: E402


@admin.register(SignalOutbox)
class SignalOutboxAdmin(ReadOnlyAdmin):
    """Signal-Postausgang: gescheiterte Nachrichten mit Fehlertext (docs/SIGNAL.md)."""

    list_display = ("created_at", "station", "attempts", "sent_at", "last_error")
    list_filter = ("sent_at",)
