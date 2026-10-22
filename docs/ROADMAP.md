# Roadmap

Stand: 3. August 2026.

## Review 22. Oktober 2026

Zwei-Repo-Review mit Debugging der Fachmodule aus 0.23.0 (CSP, API-Vertrag,
CI-Gates): [`REVIEW-2026-10-22.md`](REVIEW-2026-10-22.md), Roadmap-ID R-025.

## Sicherheits-, Betriebs- und Design-Remediation

Die verbindliche Folgeplanung aus der Review vom 3. August 2026 steht in
[`REMEDIATION-ROADMAP-2026-08.md`](REMEDIATION-ROADMAP-2026-08.md).
Arbeitsregeln für weitere Coding-Agenten stehen in [`../AGENTS.md`](../AGENTS.md).

Aktueller Stand der ersten Welle:

- [~] CSP-kompatible Empfängerauswahl für verschlüsselte Post
- [x] sichere JSON-Einbettung ohne `|safe`/`innerHTML`
- [x] Sicherheitsregressionstests
- [x] E2EE-Texte an das reale Vertrauensmodell angepasst
- [~] Race-Condition-Schutz für Tagesaufgaben
- [x] scheme-relative Redirects blockiert
- [~] vierteilige Hauptnavigation, Fokus- und mobile Wochenansicht verbessert
- [ ] Least-Privilege-Backuprolle
- [ ] gemeinsames Rate Limiting hinter explizit vertrautem Proxy
- [~] CI-Baseline; weitere Supply-Chain-Gates, Push-Outbox und zugänglicher Entsperrdialog offen
- [ ] externe ASVS-, Penetrations-, Last-, Restore- und Accessibility-Abnahme

`[~]` bedeutet: Code ist im Review-Branch umgesetzt, die in der Detail-Roadmap
genannte Browser-, Parallelitaets- oder manuelle UX-Abnahme steht noch aus.
Django- und Docker-CI waren auf Commit `6af6689` (Run 59) grün.

## Erreicht (Basis bis 0.14.2)

- Docker, lokaler Login, Rollen, Übergaben, Tagesaufgaben, Geburtstage, Kasse-Ledger
- PWA, öffentliche Startseite, persönlicher Bereich, Wachenchat
- Master-Admin legt Nutzer an/gibt frei; optionale Selbstregistrierung
- Profilbild, Passwort und Zwei-Faktor im persönlichen Bereich
- clientseitig verschlüsselte Speicherung für Wachenchat, private Chats und
  interne Post; Webclient und Server bleiben Teil des Vertrauensmodells
- Krypto an BSI TR-02102 angelehnt (AES-256-GCM, ECDH P-256, Argon2id, TLS 1.3)
- **API-Fundament** `/api/v1/` mit App-Tokens für Mobile-Clients
- **AGPL Flutter-Client** https://github.com/darkspike1988/Wachbuch-Client (Spiegel `clients/wachbuch-mobile/`)
- **Android-APK** sideloadbar (Phone/Tablet-Layout, FOSS-Build)
- Mobile-Onboarding: Server-Adresse/QR -> Login; Play-Richtlinien-Doku; Repos aufeinander abgestimmt
- optionale MFA (TOTP/Passkeys), Web-Push, Wachen-ICS-Abos, Retention, Audit-Diffs
- gesetzliche Feiertage NRW im fortlaufenden Kalender/ICS (`holidays_enabled`)
- Compliance- und ASVS-L2-Matrix dokumentiert

## Nächste Fachbausteine (Fahrplan)

Priorisierte Umsetzung der noch offenen Wuensche. Keine Kalenderzeit-Schätzung;
Reihenfolge nach Nutzen und Abhängigkeiten. Sicherheits- und Betriebsblocker aus
der Remediation-Roadmap haben Vorrang vor neuen Fachmodulen.

### 0. Wachalltag-Kern aus dem RETTpro-Vergleich — teilweise umgesetzt

**Lernpunkt:** Nicht eine komplette kommerzielle Suite nachbauen, sondern vorhandene
Open-Source-Bausteine zu einem klaren stationsbezogenen Lagebild verbinden.

**Sofort umgesetzt:** Das Dashboard zeigt jetzt neben Übergaben und Terminen auch
offene Mängel, eingeschränkte/außer Betrieb befindliche Assets und ausgeliehenes
Inventar. Die Zählung nutzt die vorhandenen Modelle, bleibt stationsisoliert und
legt keinen zweiten Erfassungsweg an.

**Plausibler Code-Schnitt:**

```python
active_defects = Defect.objects.filter(station=station).exclude(status=Defect.Status.DONE)
asset_attention = StationAsset.objects.filter(station=station).exclude(status=StationAsset.Status.READY)
inventory_loans = InventoryItem.objects.filter(station=station, holder__isnull=False)
```

**Nächste kleine Schritte:**

1. Dashboard-Karten um fällige Checklisten und Tagesaufgaben ergänzen; nur Links auf
   bestehende Seiten, keine globale Navigation und keine neue Datenhaltung.
2. Eine gemeinsame „Wachalltag im Blick“-Auswertung als read-only HTML/CSV-Export
   mit Zeitstempel und Stationsfilter anbieten.
3. Erst danach ein minimales Materialmodul prüfen: Artikel, Sollbestand,
   Istbestand, Nachbestellmarke und append-only Korrekturen; keine Lieferanten- oder
   Personenbewertung.
4. CIRS und Fahrtenbuch nur als getrennte, datensparsame Module mit eigener
   Aufbewahrung, Rollenprüfung, Audit und bewusstem Ausschluss von Patienten-,
   Einsatz- und Personaldaten planen.

**Bewertung:** Dashboard-Konsolidierung = hoher Nutzen / geringe Komplexität;
Material = mittlerer Nutzen / mittlere Komplexität; CIRS/Fahrtenbuch = hoher
fachlicher Nutzen, aber hohe Datenschutz- und Abnahme-Komplexität.
### 1. Kaffeekasse: Zahlungsweg-Hinweise (PayPal.me, Wero, IBAN) — umgesetzt

**Ziel:** Beim Kassenstand klar zeigen, wohin freiwillig eingezahlt werden kann –
ohne Zahlungsabwicklung oder Gebührenlogik im Produkt.

| Schritt | Inhalt | Status |
| --- | --- | --- |
| 1.1 | Stationseinstellungen: Felder `paypal_me_url`, `wero_link`, `iban`, `bic` (optional), `payment_note` | ✓ |
| 1.2 | Anzeige in Kaffeekasse und optional auf „Mehr": Links / kopierbare IBAN | ✓ |
| 1.3 | Nur HTTPS-Links fuer PayPal.me/Wero; IBAN-Formatpruefung; keine Speicherung von Transaktions-IDs Dritter | ✓ |
| 1.4 | Datenschutzhinweis: oeffentliche Team-Zahlungsdaten, Zweck Gemeinschaftskasse | ✓ |
| 1.5 | Tests + Kurz-Doku in OPERATIONS/COMPLIANCE | ✓ |

**Nicht im Scope:** automatischer Abgleich mit PayPal/Wero, QR-Payment-API, SEPA-Mandate.

### 2. Fortlaufender Kalender: Feiertage (NRW) + Müllkalender

**Ziel:** Der Wachenkalender zeigt neben eigenen Terminen gesetzliche Feiertage
(NRW) und später Abfuhrtermine; alles auch als iCal/Abo.

| Schritt | Inhalt |
| --- | --- |
| 2.0 | **Feiertage NRW** im fortlaufenden Kalender + ICS (Modul `holidays_enabled`) – erledigt in 0.6.1 |
| 2.1 | Recherche/Freigabe der offiziellen Muell-Quelle (AbfallNavi / RegioIT-iCal) |
| 2.2 | Stationsfelder: Gemeinde/Ort, Strasse bzw. Quellen-ID, gewaehlte Fraktionen |
| 2.3 | Admin-UI: Auswahl Ort -> Strasse/Standort |
| 2.4 | Sync -> Abfuhren im selben fortlaufenden Kalender/ICS |
| 2.5 | Token-Abo analog Wachenkalender |
| 2.6 | Dashboard: naechste Abfuhren; Kennzeichnung externe Quelle |

**Abhängigkeit Müll:** Freigabe der Datenquelle. Fallback: manuelle ICS-URL
pro Station. Feiertage sind unabhängig davon nutzbar.

### 3. Empfohlene Reihenfolge

```text
0. Review-Remediation Wave 0-2
1. Kaffeekasse-Zahlungshinweise
2. Feiertage im fortlaufenden Kalender   (umgesetzt)
3. Muellkalender: manueller ICS-URL-Fallback je Station   (umgesetzt)
4. Muellkalender: Ort/Strasse-Auswahl Kreis GT + Sync
5. API v1 / AGPL-Client ausbauen (E2EE-Chat über API, Stores/F-Droid; Schreiben für Übergaben/Kalender/Kasse/Checklisten ist in 0.14; Demo-Modus in 0.15)
6. Feinschliff UX (Dashboard, Kopieren-Buttons)
7. Review-Remediation Wave 3 und formale Produktionsfreigabe
```

### 4. Bewusst weiterhin außerhalb

- Patientendaten, Einsatz-/Alarmierung, Dienstplanung
- allgemeine Datei-Uploads (Ausnahme: kleines Profilbild im Konto)
- Messenger außerhalb von Wachenchat / Privat / interner Post
- automatische Zahlungseinzüge und Banking-APIs
- volles CalDAV-Serverprodukt (ICS-Abo bleibt der Weg)

## Phase 1 - geschlossener Test (Betrieb)

- reale Arbeitsabläufe mit Testdaten
- MFA/Passkeys und Push im Team erproben
- Remediation Wave 0–2 und ASVS-Matrix abarbeiten
- Backup/Restore und Updates testen

## Phase 2 - formaler Pilot

- Datenschutz-/Mitbestimmung, MFA-Pflicht ggf. aktivieren
- Audit-Export, Barrierearmut / Wachenterminals
- Müllkalender-Quelle schriftlich freigeben
- erste AGPL-Mobile-Clients gegen `/api/v1/`

## Phase 3 - Produktion

- Remediation Wave 3
- unabhängige ASVS-L2-Pruefung und Lasttest
- Go-live-Checkliste; erst danach öffentlicher DNS-Name

Siehe auch [`AUDIT-2026-07.md`](AUDIT-2026-07.md), [`COMPLIANCE.md`](COMPLIANCE.md),
[`ASVS-L2.md`](ASVS-L2.md) und
[`REMEDIATION-ROADMAP-2026-08.md`](REMEDIATION-ROADMAP-2026-08.md).
