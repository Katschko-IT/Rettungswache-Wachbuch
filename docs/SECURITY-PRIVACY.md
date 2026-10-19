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
- separate Datenbank ohne veröffentlichten Port
- Abhängigkeits-, Container- und Anwendungsscan vor Go-live
- Versionskennung in Footer und `/healthz/`
- Sicherheitsabnahme gegen OWASP ASVS 5.0 Level 2 als Ziel; interne Matrix in
  [`ASVS-L2.md`](ASVS-L2.md)

Ein privates Netz ersetzt weder das Rollenmodell noch eine organisatorische
Freigabe. Offene technische und betriebliche Maßnahmen stehen in
[`REMEDIATION-ROADMAP-2026-08.md`](REMEDIATION-ROADMAP-2026-08.md).
