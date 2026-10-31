"""Lesbare Bezeichnungen für das Audit-Log (Ansicht für Auditoren und Admins).

Gespeichert bleibt der technische Code (``handover.status_changed``,
``HandoverEntry``, ``open``); die Ansicht übersetzt ihn nur. Unbekannte Codes
erscheinen unverändert. Bewusst keine Objektnamen oder Titel: Auditoren
erhalten keine fachlichen Freitexte (AGENTS.md, Abschnitt 4).
"""
from __future__ import annotations

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.utils.translation import gettext_lazy as _

ACTION_LABELS = {
    "demo.seeded": _("Demo-Wache mit Musterdaten angelegt"),
    "handover.created": _("Übergabe angelegt"),
    "handover.status_changed": _("Status einer Übergabe geändert"),
    "handover.content_updated": _("Übergabe bearbeitet"),
    "handover.acknowledged": _("Übergabe als gelesen bestätigt"),
    "handover.attachment_added": _("Anhang zu einer Übergabe hinzugefügt"),
    "defect.created": _("Mangel gemeldet"),
    "defect.updated": _("Mangel bearbeitet"),
    "defect.status_changed": _("Status eines Mangels geändert"),
    "defect.attachment_added": _("Foto zu einem Mangel hinzugefügt"),
    "asset.created": _("Ausstattung angelegt"),
    "asset.status_changed": _("Status der Ausstattung geändert"),
    "inventory.created": _("Poolartikel angelegt"),
    "inventory.checkout": _("Poolartikel ausgegeben"),
    "inventory.checkin": _("Poolartikel zurückgegeben"),
    "mpg.routine_check": _("Funktionskontrolle eingetragen"),
    "mpg.device_locked": _("Medizingerät gesperrt"),
    "mpg.device_released": _("Medizingerät freigegeben"),
    "mpg.device_retired": _("Medizingerät außer Betrieb genommen"),
    "mpg.device_reactivated": _("Medizingerät wieder in Betrieb genommen"),
    "fleet.status_changed": _("Fahrzeugstatus geändert"),
    "fleet.vehicle_retired": _("Fahrzeug außer Betrieb genommen"),
    "fleet.vehicle_reactivated": _("Fahrzeug wieder in Betrieb genommen"),
    "orga.sop_status_changed": _("Status einer Dienstanweisung geändert"),
    "fleet.disinfection_crew_notified": _("Besatzung über Desinfektion benachrichtigt"),
    "checklist.completed": _("Checkliste abgeschlossen"),
    "checklist.schedule_updated": _("Checklisten-Rhythmus geändert"),
    "checklist.schedule_removed": _("Checklisten-Rhythmus entfernt"),
    "calendar.created": _("Termin angelegt"),
    "station_task.created": _("Wachaufgabe angelegt"),
    "station_task.updated": _("Wachaufgabe geändert"),
    "station_task.completed": _("Wachaufgabe erledigt"),
    "station_task.reopened": _("Wachaufgabe wieder geöffnet"),
    "coffee.payment_reported": _("Zahlung in der Kaffeekasse gemeldet"),
    "coffee.entry_created": _("Buchung in der Kaffeekasse"),
    "coffee.entry_corrected": _("Buchung der Kaffeekasse korrigiert"),
    "coffee.month_waived": _("Monatsbeitrag erlassen"),
    "coffee.purchase_recorded": _("Einkauf aus der Kaffeekasse"),
    "coffee.movement_recorded": _("Kassenbewegung gebucht"),
    "coffee.movement_corrected": _("Kassenbewegung korrigiert"),
    "coffee.cash_counted": _("Kassensturz"),
    "coffee.settings_updated": _("Einstellungen der Kaffeekasse geändert"),
    "coffee.participant_added": _("Teilnahme an der Kaffeekasse begonnen"),
    "coffee.participant_changed": _("Teilnahme an der Kaffeekasse geändert"),
    "coffee.exported": _("Kaffeekasse exportiert"),
    "chat.message_created": _("Chatnachricht gesendet"),
    "chat.message_hidden": _("Chatnachricht ausgeblendet"),
    "pinboard.note_created": _("Aushang angelegt"),
    "pinboard.note_updated": _("Aushang bearbeitet"),
    "pinboard.note_pinned": _("Aushang angeheftet"),
    "pinboard.note_archived": _("Aushang archiviert"),
    "news.created": _("Neuigkeit veröffentlicht"),
    "membership.user_created": _("Konto angelegt"),
    "membership.updated": _("Rolle oder Zugang geändert"),
    "mfa.reset": _("Zwei-Faktor-Anmeldung zurückgesetzt"),
    "station.settings_updated": _("Einstellungen der Wache geändert"),
    "birthday.preference_changed": _("Geburtstagsanzeige geändert"),
    "terminal.unlocked_by_code": _("Wachenterminal mit Wachen-Code entsperrt"),
    "terminal.code_failed": _("Falscher Wachen-Code am Terminal"),
    "terminal.code_changed": _("Wachen-Code geändert"),
    "terminal.created": _("Wachenterminal angelegt"),
    "terminal.revoked": _("Wachenterminal widerrufen"),
    "terminal.unlocked": _("Sperre eines Wachenterminals aufgehoben"),
    "terminal.pairing_created": _("Handy-Kopplung für eine Person erstellt"),
    "wiki.article_created": _("Wiki-Artikel angelegt"),
    "wiki.article_updated": _("Wiki-Artikel bearbeitet"),
    "wiki.article_archived": _("Wiki-Artikel archiviert"),
    "wiki.article_restored": _("Wiki-Artikel wiederhergestellt"),
    "membership.created": _("Mitgliedschaft freigegeben"),
    "membership.reactivated": _("Mitgliedschaft erneut freigegeben"),
    "activation.created": _("Einladung erstellt"),
    "activation.completed": _("Einladung angenommen, Konto aktiviert"),
    "activation.revoked": _("Einladung widerrufen"),
    "registration.submitted": _("Registrierung angefragt"),
    "registration.rejected": _("Registrierungsanfrage abgelehnt"),
    "setup.completed": _("Ersteinrichtung abgeschlossen"),
    "legal.updated": _("Impressum und Datenschutz geändert"),
    "api.token_created": _("App-Zugang erstellt"),
    "api.token_revoked": _("App-Zugang widerrufen"),
    "api.tokens_revoked_password": _("App-Zugänge nach Passwortänderung widerrufen"),
    "webauthn.registered": _("Passkey registriert"),
    "qr_login.created": _("Anmeldung per QR-Code angefordert"),
    "qr_login.approved": _("Anmeldung per QR-Code bestätigt"),
    "qr_login.denied": _("Anmeldung per QR-Code abgelehnt"),
    "qr_login.consumed": _("Anmeldung per QR-Code abgeschlossen"),
    "qr_login.revoked": _("Anmeldung per QR-Code widerrufen"),
    "profile.avatar_updated": _("Profilbild geändert"),
    "profile.avatar_cleared": _("Profilbild entfernt"),
    "birthday.withdrawn_on_exit": _("Geburtstagsanzeige beim Austritt entfernt"),
    "chat_group.created": _("Chatgruppe angelegt"),
    "chat_group.members_changed": _("Mitglieder einer Chatgruppe geändert"),
    "chat_group.message_created": _("Nachricht in einer Chatgruppe gesendet"),
    "private_chat.message_created": _("Verschlüsselte Direktnachricht gesendet"),
    "secure_mail.created": _("Verschlüsselte Nachricht gesendet"),
    "crypto.keys_upserted": _("Schlüssel für verschlüsselte Nachrichten hinterlegt"),
    "coffee.reminder_emailed": _("Zahlungserinnerung der Kaffeekasse per E-Mail gesendet"),
    "signal.contact_verified": _("Signal-Kontakt bestätigt"),
    "signal.contact_removed": _("Signal-Kontakt entfernt"),
    "signal.group_changed": _("Signal-Gruppe geändert"),
    "feedback.status": _("Status einer Rückmeldung geändert"),
    "feedback.deleted": _("Rückmeldung gelöscht"),
    "push.outbox_failed": _("Push-Benachrichtigung nicht zustellbar"),
}

OBJECT_LABELS = {
    "Station": _("Wache"),
    "HandoverEntry": _("Übergabe"),
    "Defect": _("Mangel"),
    "StationAsset": _("Ausstattung"),
    "InventoryItem": _("Poolartikel"),
    "MedicalDevice": _("Medizingerät"),
    "Vehicle": _("Fahrzeug"),
    "SOPDocument": _("Dienstanweisung"),
    "ChecklistCompletion": _("Checklisten-Abschluss"),
    "Checklist": _("Checkliste"),
    "CalendarEvent": _("Termin"),
    "StationTask": _("Wachaufgabe"),
    "StationTaskCompletion": _("Erledigte Wachaufgabe"),
    "CoffeeEntry": _("Kaffeekasse"),
    "CoffeeCashMovement": _("Kassenbewegung"),
    "CoffeeFund": _("Kaffeekasse"),
    "CoffeeParticipant": _("Teilnahme Kaffeekasse"),
    "ChatMessage": _("Chatnachricht"),
    "PinboardNote": _("Aushang"),
    "NewsPost": _("Neuigkeit"),
    "Membership": _("Mitgliedschaft"),
    "BirthdayPreference": _("Geburtstagsanzeige"),
    "StationTerminal": _("Wachenterminal"),
    "WikiArticle": _("Wiki-Artikel"),
    "ChecklistSchedule": _("Checklisten-Rhythmus"),
    "User": _("Konto"),
    "EmployeeActivation": _("Einladung"),
    "ApiToken": _("App-Zugang"),
    "WebAuthnCredential": _("Passkey"),
    "QrLoginRequest": _("Anmeldung per QR-Code"),
    "SiteProfile": _("Impressum und Datenschutz"),
    "ChatGroup": _("Chatgruppe"),
    "GroupMessage": _("Gruppennachricht"),
    "PrivateMessage": _("Direktnachricht"),
    "SecureMail": _("Verschlüsselte Nachricht"),
    "UserCryptoIdentity": _("Schlüssel für verschlüsselte Nachrichten"),
    "SignalContact": _("Signal-Kontakt"),
    "Feedback": _("Rückmeldung"),
    "PushOutbox": _("Push-Benachrichtigung"),
}

# Schlüssel, die Metadaten beschreiben statt Werte zu tragen, und Feldnamen ohne
# deutschen verbose_name.
FIELD_LABELS = {
    "status": _("Status"),
    "priority": _("Dringlichkeit"),
    "category": _("Kategorie"),
    "title": _("Titel"),
    "details": _("Details"),
    "owner": _("Verantwortlich"),
    "due_at": _("Frist"),
    "tactical_status": _("Fahrzeugstatus"),
    "current_status": _("Gerätestatus"),
    "role": _("Rolle"),
    "is_active": _("Aktiv"),
    "amount_cents": _("Betrag"),
    "method": _("Zahlungsweg"),
    "member": _("Person"),
    "handovers": _("Übergaben"),
    "calendar": _("Kalender"),
    "coffee": _("Kaffeekasse"),
    "checklists": _("Checklisten"),
    "chat": _("Chat"),
    "news": _("Neuigkeiten"),
    "pinboard": _("Pinnwand"),
    "wiki": _("Wiki"),
    "defects": _("Mängel"),
    "modules": _("Module"),
}


def _model(object_type: str):
    try:
        return apps.get_model("core", object_type)
    except (LookupError, ValueError):
        return None


def _field(model, name: str):
    if model is None:
        return None
    try:
        return model._meta.get_field(name)
    except FieldDoesNotExist:
        return None


def field_label(model, name: str) -> str:
    if name in FIELD_LABELS:
        return FIELD_LABELS[name]
    field = _field(model, name)
    verbose = str(getattr(field, "verbose_name", "") or "")
    # Ohne eigenen verbose_name erzeugt Django ihn aus dem (englischen) Feldnamen.
    if verbose and verbose != name.replace("_", " "):
        return verbose
    return name


def value_label(model, name: str, value) -> str:
    field = _field(model, name)
    if field is not None and field.choices and not isinstance(value, (list, dict)):
        choices = {str(key): label for key, label in field.flatchoices}
        if str(value) in choices:
            return str(choices[str(value)])
    if value is True:
        return str(_("ja"))
    if value is False:
        return str(_("nein"))
    if value in (None, ""):
        return "—"
    return str(value)


def _change_rows(model, metadata: dict) -> list[dict]:
    changes = metadata.get("changes")
    if not isinstance(changes, dict) and "from" in metadata and "to" in metadata:
        # Ältere Ereignisse speichern einen einzelnen Statuswechsel direkt.
        fields = metadata.get("fields") or []
        name = fields[0] if isinstance(fields, list) and len(fields) == 1 else "status"
        changes = {name: {"from": metadata["from"], "to": metadata["to"]}}
    rows = []
    for name, diff in (changes or {}).items():
        if not isinstance(diff, dict):
            continue
        label = field_label(model, name)
        if "from" in diff or "to" in diff:
            rows.append({
                "field": label,
                "from": value_label(model, name, diff.get("from")),
                "to": value_label(model, name, diff.get("to")),
            })
        else:
            rows.append({"field": label, "changed": True})
    return rows


def annotate(events) -> list:
    """Hängt ``action_label``, ``object_label``, ``field_labels`` und ``change_rows`` an."""
    events = list(events)
    for event in events:
        model = _model(event.object_type)
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        event.action_label = ACTION_LABELS.get(event.action, event.action)
        event.object_label = OBJECT_LABELS.get(event.object_type, event.object_type)
        fields = metadata.get("fields")
        event.field_labels = [field_label(model, str(name)) for name in fields] if isinstance(fields, list) else []
        event.change_rows = _change_rows(model, metadata)
    return events
