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
- Keine Rankings und keine Leistungskennzahlen je Person; Lesestände von
  Neuigkeiten nur als Anzahl. Offen zur Entscheidung: Die Einweisungsmatrix
  (Gerätepass) zeigt allen Inhaltsrollen je Person eine Quote der Einweisungen.
  Alle Ausgaben mit Personenbezug stehen im Datenkatalog.
- Nur technisch notwendige oder ausdrücklich gewählte Cookies (Sitzung, CSRF,
  Sprache, Darstellung; auf Terminal und Display je ein Gerätecookie);
  vollständige Liste im Datenkatalog, Abschnitt „Daten auf Endgeräten“;
  Transparenz unter `/datenschutz/`.
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
- Druckansichten der Papier-Rückfallebene (`/papier/`): Leere Formulare und
  Fristenliste enthalten nur Konfiguration und Fristen, keine Namen und keine
  früheren Ergebnisse. Das Desinfektionsblatt liegt offen im Fahrzeug und hat
  nur Spalten für Datum, Beginn, Mittel, „Frei ab“ und Kürzel; Stufe,
  Einwirkzeit je Durchgang und Bemerkung fehlen (Entscheidung D2). Beginn und
  „Frei ab“ zeigen wie die Sperre in der App, wie lange das Fahrzeug gesperrt
  war (bewusst belassener Rückschluss). Das Telefonbuch enthält die Kontakte
  wie in der App, also auch Ansprechpersonen und Rufnummern. Kein Zugang für
  Auditoren und nicht am Wachenterminal. Ausdrucke bleiben intern im Ordner
  der Wache und, je ein Blatt Übernahme und Desinfektion, im Fahrzeug. Beim
  Neudruck werden nur leere Blätter vernichtet; ausgefüllte Blätter sind
  Nachweise und bleiben als Original bei der Wachleitung (Aufbewahrung offen,
  docs/OFFLINE-BETRIEB.md § 7).

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

Unterlagen dafür:

- [`DATENKATALOG.md`](DATENKATALOG.md): Module, Felder, Rollen, Zugriffswege,
  Auswertungen mit Personenbezug und technische Fristen; für eine Wache mit
  `python manage.py data_catalog --station auto`
- [`DATENFLUESSE.md`](DATENFLUESSE.md): alle Datenflüsse an Dritte mit Schalter
  und Empfehlung für den Pilot
- [`MITBESTIMMUNG-VORLAGE.md`](MITBESTIMMUNG-VORLAGE.md): Bausteine für die
  Vereinbarung mit Betriebsrat, Personalrat oder Mitarbeitervertretung
- [`LOESCHKONZEPT.md`](LOESCHKONZEPT.md), Abschnitt „Vorschlag für den Pilot“:
  Fristen für die Daten des Pilots (Entscheidung #4)

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
- Host-Überwachung (`wachwerk-health`) meldet über eine Statusdatei, die nur
  `web` und `notify-worker` lesend einbinden: nur Codes, Zeiten und Zahlen
  (keine Texte, Hostnamen, Pfade oder Geheimnisse), streng geprüft, nie
  Auslöser einer Aktion. Anzeige und Meldungen nur an Master-Admins echter
  Wachen, nicht in der Demo, am Terminal oder auf dem Display; `/healthz/`
  bleibt öffentlich und unverändert. Die Meldungen enthalten keine Inhalte der
  Wache, nur den technischen Zustand des Servers. E-Mail, Signal und
  `PING_URL` sind Datenflüsse an Dritte und nur aktiv, wenn eingerichtet
  ([`BETRIEB-PI-LAN.md`](BETRIEB-PI-LAN.md)).
- Abhängigkeits-, Container- und Anwendungsscan vor Go-live
- Versionskennung in Footer und `/healthz/`
- Sicherheitsabnahme gegen OWASP ASVS 5.0 Level 2 als Ziel; interne Matrix in
  [`ASVS-L2.md`](ASVS-L2.md)

Ein privates Netz ersetzt weder das Rollenmodell noch eine organisatorische
Freigabe. Offene technische und betriebliche Maßnahmen stehen in
[`REMEDIATION-ROADMAP-2026-08.md`](REMEDIATION-ROADMAP-2026-08.md).
