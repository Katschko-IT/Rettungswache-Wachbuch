# Lösch- und Aufbewahrungskonzept – Betreiber-Vorlage

Stand: 31. Oktober 2026 (Vorschlag für den Pilot ergänzt)

Dieses Dokument legt **keine pauschalen gesetzlichen Fristen** fest. Der Betreiber muss für jede Datenklasse Zweck, Rechtsgrundlage, erforderliche Aufbewahrung, Löschtrigger und technische Umsetzung festlegen und durch Datenschutz/Verantwortliche freigeben.

Welche Tabelle zu welcher Datenklasse gehört und welche Frist heute technisch greift, steht im Datenkatalog: [`DATENKATALOG.md`](DATENKATALOG.md) (alle Module) bzw. `python manage.py data_catalog --station auto` (nur die Module einer Wache). Den Vorschlag für den Pilot enthält der Abschnitt [Vorschlag für den Pilot](#vorschlag-für-den-pilot-entscheidung-4--nicht-freigegeben).

## Grundprinzipien

1. So kurz wie möglich, so lange wie erforderlich.
2. Keine unbegrenzte Speicherung ohne dokumentierte Begründung.
3. Produktivdaten, Auditdaten und Backups getrennt betrachten.
4. Sperr-/Aufbewahrungspflichten können einer sofortigen Löschung entgegenstehen.
5. Löschung muss auch Replikate, Exporte, Testkopien und Backups berücksichtigen.
6. Freitext und Fotos dürfen keine sachfremden sensiblen Daten enthalten.

## Datenklassen

| Datenklasse | Zweck | Löschtrigger | Sollfrist | Technische Maßnahme | Verantwortlich |
| --- | --- | --- | --- | --- | --- |
| Benutzerkonto | Authentifizierung | Ausscheiden/Sperrung | `[festlegen]` | deaktivieren, personenbezogene Restdaten prüfen | `[Rolle]` |
| Mitgliedschaft/Rolle | Berechtigung | Rollenende | `[festlegen]` | Mitgliedschaft deaktivieren/entfernen | `[Rolle]` |
| Übergaben | Wachorganisation | Zweckfortfall/Archivende | `[festlegen]` | definierter Bereinigungsjob/Review | `[Rolle]` |
| Übergaberevisionen | Nachvollziehbarkeit | Ende zulässiger Nachweisfrist | `[festlegen]` | kontrollierte Archiv-/Löschroutine | `[Rolle]` |
| AuditEvent | IT-Sicherheit/Nachvollziehbarkeit | Ablauf Sicherheitszweck | `[festlegen]` | `RETENTION_AUDIT_DAYS` | `[Rolle]` |
| Mängel/Ereignisse | Instandhaltung | Abschluss + Nachweisfrist | `[festlegen]` | Lösch-/Archivprozess | `[Rolle]` |
| Mängelfotos | Mängelnachweis | Abschluss/Zweckfortfall | `[festlegen]` | Anhang löschen, Backup-Retention beachten | `[Rolle]` |
| Inventarereignisse | Ausgabe/Rückgabe | Ablauf Nachweiszweck | `[festlegen]` | kontrollierte Archiv-/Löschroutine | `[Rolle]` |
| Checklistenabschlüsse | Organisationsnachweis | Ablauf Zweck/Nachweisfrist | `[festlegen]` | Bereinigungsjob | `[Rolle]` |
| Geburtstagspräferenz | freiwillige Anzeige | Widerruf/Ausscheiden | unverzüglich nach Prozess | bestehende Clear-/Withdraw-Funktion | `[Rolle]` |
| Kaffeekasse | freiwillige Gemeinschaftskasse (Monatsbeiträge, Einzahlungen, Kassenbewegungen; siehe docs/KAFFEEKASSE.md) | Zweck-/Aufbewahrungsende | `[festlegen]` | Korrekturbuchungen berücksichtigen | `[Rolle]` |
| Feed-Daten | externe Information | Ablauf Aktualitätszweck | `[festlegen]` | `RETENTION_FEED_DAYS` | `[Rolle]` |
| Session/API-Token | Zugriff | Logout, Widerruf, Ablauf | technisch sofort/bei Ablauf | Token löschen/widerrufen | System/Admin |
| Serverlogs | Betrieb/Sicherheit | Ablauf Fehler-/Security-Zweck | `[festlegen]` | Logrotate/Logbackend-Retention | `[Rolle]` |
| Backups | Wiederherstellung | Ablauf Backup-Retention | `[festlegen]` | verschlüsseltes Pruning + Offsite-Löschung | `[Rolle]` |

## Pflichtkonfiguration vor Produktion

- `RETENTION_AUDIT_DAYS`: `[Wert]`
- `RETENTION_FEED_DAYS`: `[Wert]`
- lokale Backup-Retention: `[Wert]`
- Offsite-Backup-Retention: `[Wert]`
- Log-Retention Reverse Proxy/System: `[Wert]`
- Restore-Test-Retention/Testkopien: `[Wert]`

`0 = unbegrenzt` darf bei personenbezogenen Daten nur mit dokumentierter und freigegebener Begründung verwendet werden.

## Vorschlag für den Pilot (Entscheidung #4 – nicht freigegeben)

> **Vorschlag – Entscheidung #4 durch Betreiber/DSB offen.** Diese Tabelle ist
> eine Diskussionsgrundlage für die Pilotwache. Sie wird erst verbindlich, wenn
> Betreiber und Datenschutzbeauftragte sie unten freigeben. Ohne Freigabe ist
> die Startbedingung „Löschfristen für die Daten des Pilots verbindlich“
> (`ROADMAP.md`, Startkriterien) nicht erfüllt.

Grundsätze des Vorschlags:

1. **Automatische Fristen bleiben**, wie sie heute technisch umgesetzt sind (Spalte „heute technisch“).
2. **Keine Löschung von Nachweis- und Organisationsdaten während der 12 Pilotwochen.** Wo eine Tabelle append-only ist (Datenkatalog, Zeile „Nachweis“), sind Korrekturen neue Einträge. Was Wachwerk heute selbst ersetzt oder löscht, steht in der Tabelle unten.
3. **Ausstieg:** Spätestens 3 Monate nach Pilotende entscheidet der Betreiber: Weiterbetrieb (dann gilt das Löschkonzept 1.0) oder Löschung aller Pilotdaten. Bei Löschung laufen Sicherungen mit ihrer eigenen Frist aus (`BACKUP_RETENTION_DAYS`, Offsite laut Zielsystem).
4. **Ausscheiden:** Konten ausgeschiedener Personen werden innerhalb von 7 Tagen deaktiviert (Checkliste unten). Ihre Nachweise bleiben.
5. **Freiwillige Angaben** (Geburtstag, Signal-Nummer, Kaffeekasse-Erinnerung per E-Mail) werden beim Widerruf sofort entfernt; das ist heute umgesetzt.
6. **Keine neue Löschautomatik in 0.27.** Für die Lücken unten folgt nach der Entscheidung ein eigener PR.

| Datenklasse | Tabellen | heute technisch (Einstellung/Befehl, Standard) | Vorschlag Pilot | Ziel 1.0 (Diskussionsgrundlage) | Lücke |
| --- | --- | --- | --- | --- | --- |
| Sitzungen | `sessions.Session` | `housekeeping`, Ablauf nach 12 h | wie heute | wie heute | – |
| Anmeldeprotokolle | `axes.AccessLog`, `axes.AccessFailureLog` | `housekeeping`, `LOGIN_LOG_RETENTION_DAYS` = 30 | wie heute | 30 Tage | – |
| Sperrzähler | `axes.AccessAttempt` | django-axes, nach Sperrzeit (1 h) bzw. Erfolg | wie heute | wie heute | – |
| QR-Anmeldung | `QrLoginRequest`, `QrTotpUse` | `housekeeping`, 24 h | wie heute | wie heute | – |
| Fehlerereignisse | `ErrorEvent` | `housekeeping`, `ERROR_EVENT_RETENTION_DAYS` = 30 | wie heute | 30 Tage | – |
| Push-/Signal-Warteschlange | `PushOutbox`, `SignalOutbox` | 30 Tage nach Versand | wie heute | wie heute | – |
| Meldungen (Feeds) | `FeedItem` | `RETENTION_FEED_DAYS` = 90 | wie heute | 90 Tage | – |
| Rückmeldungen | `Feedback` | `FEEDBACK_RETENTION_DAYS` = 365 | wie heute | 365 Tage | – |
| Rate-Limit-Zähler | `RateLimit` | `housekeeping`, stündlich | wie heute | wie heute | – |
| Audit | `AuditEvent` | `RETENTION_AUDIT_DAYS` = 0 (unbegrenzt), `apply_retention` nur mit Owner-Rechten | keine Löschung | 365 Tage | Standard unbegrenzt |
| Konten und Rollen | `auth.User`, `UserProfile`, `Membership`, `TotpDevice`, `WebAuthnCredential` | keine Automatik; Deaktivieren durch Master-Admin | deaktivieren ≤ 7 Tage nach Ausscheiden | Löschung bzw. Anonymisierung nach Ablauf der Nachweisfristen | keine Löschautomatik |
| Übergaben | `HandoverEntry`, `HandoverAttachment` | keine Automatik | keine Löschung | `[festlegen]` | – |
| Nachweise | `HandoverRevision`, `HandoverAck`, `ChecklistCompletion`, `DefectEvent`, `AssetEvent`, `InventoryEvent`, `WikiRevision`, `CoffeeEntry`, `CoffeeCashMovement`, `StockMovement`, `MaintenanceLog`, `DeviceRoutineCheck`, `DeviceTrainingRecord`, `VehicleHandover`, `DisinfectionProtocol`, `SOPRevision`, `SOPReceipt` | keine Löschautomatik; Web und App bieten kein Löschen an. Append-only sind nur die im Datenkatalog so markierten Tabellen (in der Anwendung, einige zusätzlich per Datenbankrechten). Ausnahme: Eine neue Einweisung ersetzt die vorige derselben Person am selben Gerät (`DeviceTrainingRecord`) | keine Löschung | laut Fach- und Nachweispflicht, `[festlegen]` | – |
| Erledigt-Vermerke, Lesestatus (kein Nachweis) | `StationTaskCompletion`, `NewsAcknowledgement` | keine Löschautomatik; „Wieder öffnen“ löscht einen Erledigt-Vermerk (Audit `station_task.reopened`) | wie heute | `[festlegen]` | keine Löschautomatik |
| Mängel | `Defect` | keine Automatik | keine Löschung | `[festlegen]` | – |
| Mängelfotos | `DefectAttachment` | keine Automatik | keine Löschung | 90 Tage nach Abschluss des Mangels | keine Löschautomatik |
| Anhänge Neuigkeiten/Pinnwand | `NewsAttachment`, `PinboardAttachment` | keine Automatik | keine Löschung | mit dem Aushang | keine Löschautomatik |
| Persönliche Hinweise | `UserNotification` | keine Automatik | keine Löschung | 30 Tage nach dem Lesen, 90 Tage ungelesen | **Lücke** |
| Django-Admin-Protokoll | `admin.LogEntry` | keine Automatik | keine Löschung | 365 Tage | **Lücke** |
| Einladungen | `EmployeeActivation` | keine Automatik | keine Löschung | 90 Tage nach Nutzung oder Ablauf | **Lücke** |
| Registrierungsanfragen | `RegistrationRequest` | keine Automatik | keine Löschung | `[festlegen]` nach Entscheidung | **Lücke** |
| App-Zugänge | `ApiToken` | widerrufene/abgelaufene Einträge bleiben (nur Hash) | keine Löschung | `[festlegen]` | **Lücke** |
| Kalender | `CalendarEvent` | keine Automatik | keine Löschung | `[festlegen]` für vergangene Termine | **Lücke** |
| Pinnwand | `PinboardNote` (auch archivierte) | keine Automatik | keine Löschung | `[festlegen]` für archivierte Aushänge | **Lücke** |
| Chat, Privat, Post | `ChatMessage`, `PrivateMessage`, `GroupMessage`, `SecureMail` und Zuordnungen | keine Automatik (Inhalt verschlüsselt) | im Pilot ausgeschaltet (Startkriterium) | `[festlegen]` | **Lücke** |
| Geburtstag, Signal-Nummer | `BirthdayPreference`, `SignalContact` | beim Widerruf sofort | wie heute | wie heute | – |
| Gerätebindungen | `PushSubscription`, `MobilePushDevice` | beim Abmelden des Geräts oder bei ungültiger Adresse | wie heute | wie heute | – |
| Docker-Protokolle | – | nur Größe: 3 × 10 MB je Dienst, keine Zeitgrenze | wie heute | `[festlegen]` (Zeitgrenze) | **Lücke** |
| Sicherungen | Backup-Volume, `./backups`, Offsite | `BACKUP_RETENTION_DAYS` = 7; Offsite laut Zielsystem | wie heute | `[festlegen]` | – |
| Papier-Rückfallebene | ausgefüllte Ausdrucke | – (nicht im System) | `[festlegen]`: Aufbewahrung und Vernichtung der Blätter | `[festlegen]` | offen |

Hinweise:

- **Nachweise löscht Wachwerk nicht automatisch.** Gegen Ändern und Löschen gesperrt (append-only) sind nur die im Datenkatalog so markierten Tabellen; Stammdaten wie Fahrzeuge, Medizingeräte, Chargen und Dienstanweisungen werden bearbeitet, ihre Nachweise hängen an ihnen. Eine Löschfrist für Nachweise setzt eine eigene Entscheidung und einen eigenen Löschweg mit Owner-Rechten voraus.
- **Einmalige Altdaten-Bereinigung** (Entscheidung D1, Befehl aus Paket C): Sie neutralisiert alte Fahrzeugstatus im Audit und entfernt IP-Adresse und Browser aus alten Lesequittungen. Sicherungen behalten den alten Stand, bis sie nach `BACKUP_RETENTION_DAYS` bzw. der Offsite-Frist auslaufen.
- **Sichtbarkeit von Namen:** Lesebestätigungen von Übergaben (Name und Zeit) sehen alle Inhaltsrollen; erledigte Tagesaufgaben und Checklisten zeigen im Web den Vornamen, die App beim letzten Abschluss einer Checkliste den vollen Namen. Das bleibt im Pilot so und ist in der Vorlage für die Vereinbarung (`MITBESTIMMUNG-VORLAGE.md`) aufgeführt.

Freigabe Pilot-Fristen (Entscheidung #4):

- Betreiber: `[Name/Datum]`
- Datenschutzbeauftragte/r: `[Name/Datum]`
- Interessenvertretung zur Kenntnis: `[Name/Datum]`

## Ausscheiden eines Benutzers

Checkliste:

- [ ] Konto sperren/deaktivieren.
- [ ] aktive Membership entziehen.
- [ ] API-Tokens widerrufen.
- [ ] Push-/Gerätebindungen prüfen.
- [ ] freiwillige Sichtbarkeiten (z. B. Geburtstag) entfernen.
- [ ] personenbezogene Inhalte anhand Zweck/Aufbewahrung prüfen.
- [ ] offene Inventar-/Schlüsselzuordnungen klären.
- [ ] Löschung/Anonymisierung terminieren, soweit zulässig.
- [ ] Bearbeitung dokumentieren.

## Mängelfotos

Fotos besitzen erhöhtes Fehlverwendungsrisiko. Daher:

- nur für dokumentierte Mängel,
- keine Patienten-/Einsatz-/Bildschirm-/Personalfotos,
- Client entfernt vor Upload Metadaten durch Pixel-Neucodierung,
- Server validiert Format/Größe und Stationszuordnung,
- nach Zweckfortfall möglichst früher löschen als textliche Vorgangsdaten,
- Löschung in Backups über Backup-Retention nachvollziehbar auslaufen lassen.

## Betroffenenanfrage / Löschsperre

Wenn eine Betroffenenanfrage, Rechtsstreit, Sicherheitsuntersuchung oder gesetzliche Aufbewahrung eine Löschung beeinflusst:

1. Datensatz/Datenklasse identifizieren,
2. Rechtsgrundlage der weiteren Aufbewahrung dokumentieren,
3. Zugriff soweit möglich einschränken,
4. Frist/Review-Termin setzen,
5. nach Wegfall der Sperre Löschung nachholen.

## Backups

Eine Löschung muss nicht jedes unveränderliche Backup sofort physisch umschreiben, sofern:

- Backup nur Wiederherstellungszwecken dient,
- Zugriff streng begrenzt ist,
- definierte kurze Retention greift,
- gelöschte Daten nach Restore nicht erneut produktiv genutzt werden bzw. die Löschung wieder angewendet wird,
- Prozess dokumentiert ist.

Die konkrete rechtliche Bewertung ist vom Betreiber festzulegen.

## Review

Löschkonzept mindestens jährlich sowie bei neuen Modulen, neuen Rechtsgrundlagen, neuen Dienstleistern oder Schutzbedarfsänderungen prüfen.

Freigabe Verantwortlicher: `[Name/Datum]`  
Freigabe Datenschutz: `[Name/Datum]`
