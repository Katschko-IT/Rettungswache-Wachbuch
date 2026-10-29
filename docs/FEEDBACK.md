# Feedback-Seite

Öffentliches Formular unter `/feedback/` für Wünsche, Anregungen, Lob, Fehler
und Fragen. In der öffentlichen Demo (`DEMO_SANDBOX=true`) automatisch an,
sonst mit `FEEDBACK_ENABLED=true`.

- **Felder:** Art (Wunsch, Anregung, Lob, Fehler, Frage), Nachricht (Pflicht,
  höchstens 3000 Zeichen), freiwillig „Ich bin …“ (Einsatzkraft, Wachleitung
  oder Praxisanleitung, IT oder Datenschutz, anderes), Bewertung 1–5, Name
  und E-Mail für eine Antwort. Einwilligung zum Speichern ist Pflicht.
- **Keine IP-Adresse** in der Datenbank. Gegen Missbrauch: unsichtbares
  Lockfeld für Spam-Programme und höchstens `FEEDBACK_PER_IP_HOUR` (5)
  Rückmeldungen je Anschluss und Stunde (gesalzener Hash im Cache).
- **Lesen:** Einstellungen → Rückmeldungen (`/einstellungen/feedback/`), nur
  für den Betreiber der Installation: Master-Admins der Wache aus der
  Ersteinrichtung (ohne Ersteinrichtung: der Standardwache
  `DEFAULT_STATION_SLUG` bzw. der einzigen echten Wache) und Superuser.
  Master-Admins weiterer Wachen und Besucher der Demo-Wachen sehen weder den
  Posteingang noch den Knopf. Einträge lassen sich als gelesen/erledigt
  markieren oder löschen (Audit).
- **Löschfrist:** `FEEDBACK_RETENTION_DAYS` (Standard 365, 0 = nie) über
  `python manage.py apply_retention`.
- Die Rückmeldungen gehören bewusst zu keiner Wache: Die Seite ist
  öffentlich, Empfänger ist der Betreiber der Installation (wie Impressum und
  Datenschutz-Angaben).
- Datenschutz-Information: Abschnitt 2 erklärt das Formular, sobald es
  eingeschaltet ist.
