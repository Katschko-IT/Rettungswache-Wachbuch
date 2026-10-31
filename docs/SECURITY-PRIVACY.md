# Datenschutz und Sicherheit

Ergänzende Compliance-Hinweise stehen in [`COMPLIANCE.md`](COMPLIANCE.md).
Dieses Dokument ist keine Rechtsberatung.

## Privacy by Design

- Keine Felder für Patienten-, Diagnose-, Einsatznummern- oder Alarmdaten.
- Übergabeformular mit sichtbarem Verbot solcher Inhalte.
- Geburtstage standardmaessig aus und jederzeit widerrufbar.
- Kaffeekasse als nachvollziehbares Ledger statt stiller Änderungen.
- Audit speichert Feldnamen und Ereignisse, nicht die fachlichen Freitexte.
  Zahlungsangaben (`iban`, `bic`, `payment_note`, Zahlungslinks) erscheinen im
  Audit nur als `changed`, ohne Werte.
- Keine Rankings, Lesestatistiken oder personenbezogene Leistungskennzahlen.
- Nur technisch notwendige Cookies (`rwsth_session`, `rwsth_csrf`); Transparenz
  unter `/datenschutz/`.
- Produkt ohne eingebettetes KI-System; kein Social Scoring über Auditdaten.
- Fahrzeugzustand mit fünf neutralen Zuständen (Einsatzbereit, Eingeschränkt,
  Desinfektion, Werkstatt, Außer Dienst), ohne Einsatzphasen und ohne
  FMS-Codes in Datenbank, Display-JSON, CSS-Klassen oder Formularwerten (0.27).
- Desinfektion nach Stufen, benannt nach Umfang oder Wirkbereich statt nach
  Erregern; Erregernamen lehnt das Modell als Stufennamen ab. Stufe,
  Einwirkzeit und Bemerkung eines Protokolls sehen bis zum Funktionsmodell
  (0.28) nur die durchführende Person, Schichtleitung und Admin; alle anderen
  sehen „Desinfektion“ mit Datum, Mittel und Person. Bekannter Restbezug: Die
  laufende Sperre („Desinfektion bis HH:MM“), ihre Dauer und die
  Benachrichtigung der Besatzung bleiben für den Betrieb sichtbar und lassen
  erkennen, dass eine Stufe mit Einwirkzeit gewählt wurde.
- Einzige Ausnahme von append-only: die einmalige Bereinigung der Altdaten
  nach Betreiberentscheid vom 30.10.2026 (`cleanup_legacy_data`, frühere
  Einsatzphasen im Audit, IP/Browser alter Lesebestätigungen, Bemerkungen aus
  der Zeit des Felds „Transportgrund“). Sie braucht Eigentümerrechte, schreibt
  je Wache einen Audit-Eintrag mit Zahl, Person und Zeit; Backups behalten den
  alten Stand bis zu ihrem Ablauf (docs/OPERATIONS.md).

## Nachweise

- Verzeichnis aller Nachweis-Tabellen in `core/evidence.py`; jeder ihrer
  Fremdschlüssel ist `PROTECT`, nie `CASCADE` oder `SET_NULL`. Ein Negativtest
  löscht jedes Objekt, auf das ein Nachweis zeigt (`core/test_evidence_protection.py`).
- Fahrzeuge und Medizingeräte werden außer Betrieb genommen, Dienstanweisungen
  außer Kraft gesetzt – mit Audit-Eintrag, ohne Freitext. Danach nehmen sie
  keine neuen Nachweise an. Desinfektionsmittel werden im Django-Admin aus dem
  Gebrauch genommen (Admin-Protokoll) und nicht mehr angeboten.
- Prüfungen, Funktionskontrollen und Versionen von Dienstanweisungen sind
  append-only; für Prüfungen und Funktionskontrollen entzieht die Datenbank der
  App-Rolle zusätzlich `UPDATE` und `DELETE`.
- Folge für Löschanfragen: Ein Konto mit Nachweisen wird deaktiviert, nicht
  gelöscht; die Pseudonymisierung ausgeschiedener Personen regelt das
  Löschkonzept.

## Vor einem betrieblichen Pilotbetrieb klären

- verantwortliche Stelle und anwendbares Recht: DSG NRW/LPVG,
  BDSG/BetrVG oder kirchliches Datenschutzrecht
- konkrete Rechtsgrundlage je Modul und Verzeichnis der Verarbeitungstätigkeiten
- DSFA-Schwellenwertpruefung, gegebenenfalls vollständige DSFA
- Beteiligung und Freigabe durch Datenschutz, Informationssicherheit und
  Betriebs-/Personalrat beziehungsweise Mitarbeitervertretung
- abgestimmte Rollen, Löschfristen, Korrekturverfahren und Auswertungsverbote
- Betroffeneninformationen und Verfahren für Auskunft, Berichtigung, Löschung
  sowie Datenschutzverletzungen
- Cookie-/TDDDG- und AI-Act-Dokumentation an die konkrete Stelle anpassen

## Technische Baseline

- TLS durch einen kontrollierten Reverse-Proxy vor dem Docker-Port
- lokaler HTTP-Zugriff nur über Loopback; sichere Cookies bei jedem TLS-Betrieb
- persönliche lokale Konten, Login-Drosselung und keine gemeinsam genutzten Zugänge
- optionales Profilbild nur als kleines JPEG in der Datenbank (kein allgemeiner Upload)
- CSV-Stammdatenimport nur für Master-Admins: Datei höchstens 1 MB, nur im
  Arbeitsspeicher gelesen und nie gespeichert (auch nicht in Sitzung oder
  Backups; Zwischenpuffer des Proxys werden nach der Anfrage verworfen),
  Trockenlauf in einer zurückgerollten Transaktion, Import in einer
  Transaktion (alles oder nichts), signierte Vorschau (Wache, Person, Art,
  SHA-256; 1 h); im Audit nur Anzahl und SHA-256; Werte mit `= + - @` am Anfang
  werden abgelehnt; kein allgemeiner Upload
  ([`STAMMDATEN-IMPORT.md`](STAMMDATEN-IMPORT.md))
- Chat, Privat und Post werden clientseitig mit **AES-256-GCM** + ECDH P-256
  verschlüsselt gespeichert; Datenbank und Backups enthalten Ciphertext
- der ausgelieferte Webclient und der Anwendungsserver bleiben bei der Web-PWA
  Teil des Vertrauensmodells; ein aktiv kompromittierter Server ist ohne
  unabhängige Schlüsselverifikation nicht durch das heutige Modell abgedeckt
- Login-Passwörter mit **Argon2id**; TOTP-Geheimnisse AES-256-GCM at rest
- Krypto-Zuordnung und Bedrohungsmodell: [`CRYPTO-BSI.md`](CRYPTO-BSI.md)
- sichere Session-Cookies, CSRF-Schutz, CSP (`connect-src` nur `'self'` und
  Hosts aus `PUSH_ALLOWED_ENDPOINT_HOSTS`) und restriktive Browser-Header
- serverseitige Objekt- und Rollenprüfung
- optionale Verkehrslage je Wache (Standard aus): der Server fragt nur fest
  eingetragene HTTPS-Hosts auf Port 443 ab (Autobahn GmbH, BBK/NINA und – nur
  wenn die Wache sie zuschaltet – Gemeinde Steinhagen und Kreis Gütersloh),
  ohne Weiterleitungen, mit Größen- und Zeitlimit; Straßenkennungen sind auf
  `^[AB]\d{1,3}$` begrenzt. Übermittelt wird nur die Serveranfrage, keine
  Personen- oder Wachendaten; Koordinaten und Warngebiete bleiben auf dem Server.
- separate Datenbank ohne veröffentlichten Port
- Abhängigkeits-, Container- und Anwendungsscan vor Go-live
- Versionskennung in Footer und `/healthz/`
- Sicherheitsabnahme gegen OWASP ASVS 5.0 Level 2 als Ziel; interne Matrix in
  [`ASVS-L2.md`](ASVS-L2.md)

Ein privates Netz ersetzt weder das Rollenmodell noch eine organisatorische
Freigabe. Offene technische und betriebliche Maßnahmen stehen in
[`REMEDIATION-ROADMAP-2026-08.md`](REMEDIATION-ROADMAP-2026-08.md).
