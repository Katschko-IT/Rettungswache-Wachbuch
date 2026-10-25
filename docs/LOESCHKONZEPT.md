# Lösch- und Aufbewahrungskonzept – Betreiber-Vorlage

Stand: 10. August 2026

Dieses Dokument legt **keine pauschalen gesetzlichen Fristen** fest. Der Betreiber muss für jede Datenklasse Zweck, Rechtsgrundlage, erforderliche Aufbewahrung, Löschtrigger und technische Umsetzung festlegen und durch Datenschutz/Verantwortliche freigeben.

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
