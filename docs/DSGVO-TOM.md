# Technische und organisatorische Maßnahmen (TOM) – Vorlage

Stand: 10. August 2026

Diese Vorlage unterstützt die Dokumentation nach Art. 32 DSGVO. Betreiber müssen sie an tatsächliche Infrastruktur, Schutzbedarf, Verträge und Zuständigkeiten anpassen und freigeben.

## 1. Verantwortliche Stelle

- Organisation: `[ausfüllen]`
- Verantwortlicher Bereich: `[ausfüllen]`
- IT-Verantwortung: `[ausfüllen]`
- Datenschutzbeauftragte/r: im Wachbuch-Admin hinterlegt und zusätzlich organisatorisch dokumentiert
- Informationssicherheitsverantwortung: `[ausfüllen]`
- Freigabedatum / nächste Prüfung: `[ausfüllen]`

## 2. Vertraulichkeit

### Zugriffssteuerung

- individuelle Benutzerkonten; keine geteilten Produktivkonten
- stationsbezogene Mitgliedschaften und rollenbasierte Berechtigungen
- Least-Privilege-Prinzip für App-, Feed- und Backup-Datenbankrollen
- MFA für produktive Konten verpflichtend konfigurieren
- regelmäßige Rezertifizierung aktiver Konten und Rollen
- sofortige Sperrung/Aufhebung bei Rollenwechsel oder Ausscheiden

Nachweis: Benutzer-/Rollenreview `[Intervall]`, Verantwortlicher `[Name/Rolle]`.

### Geheimnisse und Schlüssel

- `DJANGO_SECRET_KEY` und `CRYPTO_MASTER_KEY` sind getrennte Geheimnisse
- `CRYPTO_MASTER_KEY`: zufällige 32 Byte / 64 Hex-Zeichen
- Anwendungsschutz ausgewählter Geheimnisse mit AES-256-GCM
- Schlüsselmaterial nicht im Git-Repository, in Tickets, Chats oder Logs
- Produktivschlüssel bevorzugt in Secret-Manager/KMS bzw. sicherem Host-Secret-Speicher
- Rotation mit dokumentiertem Vier-Augen-Prozess und Recovery-Plan

Nachweis: letzte Rotation `[Datum]`; Key-Custodian `[Rolle]`.

### Transport

- öffentlicher Zugriff ausschließlich HTTPS
- TLS-Terminierung am kontrollierten Reverse Proxy
- TLS-Konfiguration an BSI TR-02102-2 / BSI-Mindeststandard TLS ausrichten
- HTTP → HTTPS-Weiterleitung am Edge
- HSTS nach erfolgreicher Domain-/Subdomain-Prüfung aktivieren
- keine Klartext-Zugangsdaten in URLs

Nachweis: TLS-Scan `[Datum/Tool]`, Zertifikatsprozess `[Beschreibung]`.

### Mobile Endgeräte

- Gerätesperre/PIN bzw. biometrischer Schutz
- unterstützte, gepatchte iOS-/Android-Versionen
- keine gerooteten/jailbroken Produktivgeräte
- Organisationsgeräte über MDM verwalten, soweit Schutzbedarf dies erfordert
- Remote-Sperrung/-Löschung für verwaltete Geräte
- App-Tokens ausschließlich im OS-Secure-Storage
- keine produktiven Tokens in Backups oder Screenshots

## 3. Integrität

- HTTPS/TLS und authentifizierte API-Zugriffe
- serverseitige Rollen-/Stationsprüfung für jeden geschützten Datensatz
- append-only Ereignisse für relevante Status-/Inventar-/Auditvorgänge
- signierte Store-/Release-Artefakte
- CI-Gates, Lint, Tests, Dependency-Security und SBOM
- Bilder nur in freigegebenen Formaten/Größen; serverseitige Decodier-/MIME-Prüfung
- Änderungen an Produktion nur über nachvollziehbaren Release-/Change-Prozess

## 4. Verfügbarkeit und Belastbarkeit

- PostgreSQL auf persistentem, verschlüsseltem Storage
- regelmäßige automatisierte Backups
- verschlüsselte Offsite-Kopie
- Backup-Dienst nur mit Leserechten
- Restore-Test in isolierter Umgebung in festgelegtem Intervall
- Monitoring für Verfügbarkeit, Speicher, Zertifikatsablauf und Fehlerraten
- dokumentierte RTO/RPO-Ziele

RTO: `[ausfüllen]`  
RPO: `[ausfüllen]`  
Restore-Test zuletzt: `[ausfüllen]`

## 5. Trennungsgebot / Mandantentrennung

- stationbezogene Foreign Keys und serverseitige Stationsfilter
- Cross-Station-Zugriffe durch Modell-/API-Invarianten verhindern
- Testdaten strikt von Produktionsdaten trennen
- Review-/Demo-System ohne Echtdaten
- Produktions- und Entwicklungsgeheimnisse getrennt halten

## 6. Protokollierung

- Korrelations-IDs für technische Fehleranalyse
- keine Passwörter, API-Tokens, Formular-/Request-Bodies oder Bildinhalte in Logs
- Logzugriff nur für berechtigte Betriebsrollen
- Retention gemäß freigegebenem Löschkonzept
- Audit-Logs nicht als verdeckte Leistungs-/Verhaltenskontrolle verwenden
- sicherheitsrelevante Ereignisse und Admin-Aktionen regelmäßig prüfen

## 7. Datensicherung und Löschung

- Datenklassen und Fristen in `LOESCHKONZEPT.md` konkretisieren
- `RETENTION_AUDIT_DAYS` und weitere Retention-Einstellungen an das freigegebene Konzept anpassen
- Backups besitzen eigene Ablauf-/Löschfristen
- Löschung ausgeschiedener Benutzer organisatorisch und technisch dokumentieren
- rechtliche Aufbewahrungspflichten gehen vor automatischer Löschung; Begründung dokumentieren

## 8. Datenschutz durch Technikgestaltung

- keine Werbung/Tracking-SDKs im Produktkern
- Standort nur lokal und nur für Designfunktion
- produktive App-Verbindungen nur über HTTPS
- minimale mobile Berechtigungen
- keine Patienten-/Einsatzdaten im Produktmodell
- öffentliche Datenschutzkontakte nur nach explizitem Admin-Schalter
- interne DPO-Notizen werden nie öffentlich gerendert
- Datenminimierung bei Formularen und Auswertungen

## 9. Auftragsverarbeitung / Dienstleister

Für jeden externen Dienst prüfen und dokumentieren:

- Rolle Verantwortlicher/Auftragsverarbeiter/eigenständig Verantwortlicher
- Vertrag nach Art. 28 DSGVO, falls erforderlich
- Unterauftragsverarbeiter
- Hosting-/Backup-/Mail-/Push-/DNS-/Monitoring-Anbieter
- Drittlandtransfer und Transfermechanismus, falls einschlägig
- Lösch-/Rückgaberegeln bei Vertragsende

Alle externen Dienste mit Daten, Schalter und Standard: [`DATENFLUESSE.md`](DATENFLUESSE.md).

## 10. Schwachstellen- und Patchmanagement

- Security-Meldungen über privaten Kanal gemäß `SECURITY.md`
- Dependency-/Container-/Code-Scans in CI
- kritische Schwachstellen priorisiert bewerten und beheben
- Betriebssystem, Reverse Proxy, Datenbank, Docker/Runtime und Anwendung regelmäßig patchen
- Ausnahmen mit Risikoakzeptanz, Verantwortlichem und Ablaufdatum dokumentieren

## 11. Datenschutzverletzungen

Incident-Prozess muss mindestens enthalten:

1. technische Eindämmung
2. Beweissicherung ohne unnötige Datenduplizierung
3. Bewertung betroffener Daten/Konten/Zeitraum
4. Information Datenschutzbeauftragte/r und Verantwortliche
5. Prüfung Art. 33/34 DSGVO und ggf. Meldung/Benachrichtigung
6. Abhilfemaßnahmen
7. dokumentierter Abschluss und Lessons Learned

## 12. Regelmäßige Wirksamkeitsprüfung

Mindestens festlegen:

- Zugriffsreview: `[Intervall]`
- Restore-Test: `[Intervall]`
- Patch-/Vulnerability-Review: `[Intervall]`
- TLS-/Zertifikatsreview: `[Intervall]`
- TOM-/VVT-/DSFA-Review: `[Intervall]`
- Geräte-/MDM-Compliance: `[Intervall]`

Freigabe Verantwortlicher: `[Name/Datum]`  
Freigabe Datenschutz: `[Name/Datum]`  
Freigabe Informationssicherheit: `[Name/Datum]`
