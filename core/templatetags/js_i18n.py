"""Sprachkatalog fuer die JavaScript-Oberflaeche (F4).

Die msgids stehen als literale ``gettext``-Aufrufe im Renderingpfad, damit
``gettext`` erst zur Rendertime in der aktivierten Sprache aufloest und der
Katalog-Extraktor dieselben 50 msgids wie zuvor aus dem Template findet.
Das Template gibt das Ergebnis ueber ``json_script`` aus.
"""

from django import template
from django.utils.translation import gettext

register = template.Library()


@register.simple_tag
def js_i18n_data():
    """Liefert die 50 JS-Texte in der aktuell aktiven Sprache."""
    return {
        "request_failed": gettext("Anfrage fehlgeschlagen."),
        "passkey_checking": gettext("Passkey wird geprüft …"),
        "passkey_unavailable": gettext("Passkeys sind hier nicht verfügbar."),
        "passkey_confirm_impossible": gettext("Passkey-Bestätigung nicht möglich."),
        "passkey_registering": gettext("Passkey wird registriert …"),
        "passkey_register_impossible": gettext("Passkey-Registrierung nicht möglich."),
        "notifications_not_allowed": gettext("Benachrichtigungen wurden nicht erlaubt."),
        "offline_banner": gettext("Offline – angezeigte Daten können veraltet sein"),
        "passkey_login_failed": gettext("Passkey-Anmeldung fehlgeschlagen."),
        "passkey_confirm_failed": gettext("Passkey-Bestätigung fehlgeschlagen."),
        "passkey_register_failed": gettext("Passkey-Registrierung fehlgeschlagen."),
        "push_enable_failed": gettext("Push konnte nicht aktiviert werden."),
        "push_disable_failed": gettext("Push konnte nicht deaktiviert werden."),
        "key_envelope_corrupt": gettext("Gespeicherter Schlüsselumschlag ist beschädigt."),
        "no_envelope": gettext("Kein Schlüsselumschlag für dich – Nachricht nicht lesbar."),
        "unlock_cancelled": gettext("Entsperren abgebrochen."),
        "setup_keys_first": gettext("Bitte zuerst unter Mein Konto Schlüssel einrichten."),
        "keys_unlocking": gettext("Schlüssel werden entsperrt …"),
        "passphrase_too_short": gettext("Passphrase mindestens 10 Zeichen."),
        "passphrases_mismatch": gettext("Passphrasen stimmen nicht überein."),
        "keys_generating": gettext("Schlüssel werden erzeugt …"),
        "key_setup_failed": gettext("Schlüsselsetup fehlgeschlagen."),
        "keys_unlocked": gettext("Schlüssel entsperrt."),
        "unlock_failed": gettext("Entsperren fehlgeschlagen."),
        "decrypt_failed": gettext("Entschlüsseln fehlgeschlagen."),
        "encrypted_unreadable": gettext("Verschlüsselt – nicht entschlüsselbar (fehlende Schlüssel)."),
        "no_keyed_colleagues": gettext("Noch keine Kollegen mit Schlüsseln."),
        "send_failed": gettext("Senden fehlgeschlagen."),
        "recipient_and_text_required": gettext("Empfänger und Text sind nötig."),
        "mail_undecryptable": gettext("Mail nicht entschlüsselbar."),
        "copied": gettext("Kopiert"),
        "qr_expired_renew": gettext("QR-Code ist abgelaufen. Bitte erneuern."),
        "qr_expired": gettext("QR-Code ist abgelaufen."),
        "qr_approved_closing": gettext("Anmeldung freigegeben! Anmeldung wird abgeschlossen …"),
        "qr_denied": gettext("Anmeldung wurde auf dem Mobilgerät abgelehnt."),
        "qr_revoked": gettext("Anmeldung wurde widerrufen."),
        "qr_complete_failed": gettext("Anmeldung konnte nicht abgeschlossen werden."),
        "qr_connection_error_exchange": gettext("Verbindungsfehler beim Austausch."),
        "qr_wait_init": gettext("Warte auf Initialisierung …"),
        "qr_start_failed": gettext("QR-Login konnte nicht gestartet werden."),
        "qr_wait_confirm": gettext("Warte auf Bestätigung durch das Smartphone …"),
        "qr_connection_error_start": gettext("Verbindungsfehler beim Start."),
        "passkey_requesting": gettext("Passkey wird abgefragt …"),
        "passkey_options_unavailable": gettext("Passkey-Optionen nicht verfügbar."),
        "passkey_check_failed": gettext("Passkey-Prüfung fehlgeschlagen."),
        "passkey_verified_submit": gettext("Passkey erfolgreich geprüft. Bitte Freigabe absenden."),
        "passkey_verified": gettext("Passkey verifiziert ✓"),
        "passkey_check_cancelled": gettext("Passkey-Prüfung abgebrochen."),
        "unlock": gettext("Entsperren"),
        "passphrase_required": gettext("Bitte Passphrase eingeben."),
    }
