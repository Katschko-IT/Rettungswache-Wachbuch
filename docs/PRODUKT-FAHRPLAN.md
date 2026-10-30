# Produkt-Fahrplan: homogenes Wachbuch (Server + Client)

> **Abgelöst** am 30.10.2026 durch [ROADMAP.md](ROADMAP.md). Diese Datei bleibt als Verlauf erhalten.

Stand: 2026-08. Dieser Fahrplan verzahnt den Django-Server
(`Rettungswache-Wachbuch`) mit dem Flutter-Client
(`Wachbuch-Client`) zu einem homogenen Produkt. Er wird Stück für Stück in
kleinen, getesteten PRs abgearbeitet.

Statuskonvention (wie `AGENTS.md`):

- `[ ]` offen
- `[~]` begonnen / nicht vollständig abgenommen
- `[x]` umgesetzt und durch Tests belegt
- `[!]` blockiert (Grund + nächste Aktion daneben)

## Produktgrenze (nicht verhandelbar)

Alle Phasen bleiben im Wachalltag/Organisations-Rahmen. **Keine** Patienten-,
Einsatz-, Alarmierungs-, Diagnose- oder Leistungsdaten. Karten dienen
Infrastruktur (Standorte, Hydranten, Sammelplätze), nicht Einsatz-/Personen-
Tracking. Es gelten weiterhin alle Invarianten aus `AGENTS.md`
(Stationsbindung, Append-only-Audit, CSP ohne `unsafe-inline`, kein `|safe`,
E2EE-Vertrauensmodell).

## Ist-Stand (Ausgangspunkt)

- Server: Übergaben, Mängel, Geräte/Statusboard, Inventar, Checklisten,
  Kalender, Kaffeekasse, Aufgaben/Wandtafel, Feeds, Team/Rollen, Audit,
  **öffentlicher Chat (E2EE), privater 1:1-Chat (E2EE), Secure Mail (E2EE)** –
  Chat bisher nur im Web, keine Gruppen, keine Chat-API.
- Client: Übergaben, Maengel, Geraete/Inventar, Checklisten, Kalender,
  Kaffeekasse, Auswertung, Konto, Demo-Profile – **kein Chat, keine Pinnwand**.
- Fehlt gesamthaft: **Pinnwand**, **Chatgruppen**, **Chat im Client**,
  Prüf-/Wartungsfristen mit Erinnerungen, Qualifikationsverwaltung, Karten.

## Phasen

### Phase 0 – Fundament (Dev-Umgebung) `[x]`

Cloud-Agent-Umgebung für Server + Client (venv/Django + Flutter-SDK,
`install`/`start`, Terminals für beide Dev-Server). Belegt durch grünen
Environment-Build + Fresh-Agent-Verifikation.

### Phase 1 – Digitale Pinnwand (Aushänge/Notizen) `[~]`

Umgesetzt in Server-PR #66 und Client-PR (Wachbuch-Client) #44; Abnahme durch
Tests (Server 226, Client 221) und Browser-Demo. Offen: Merge.


Stationsinterne Pinnwand für kurze Aushaenge/Hinweise, getrennt von den
strukturierten Übergaben.

- Server: Modell `PinboardNote` (station-gebunden, Autor, Titel, Text,
  angepinnt, archiviert), Service + Audit, Views/Templates, Modul-Toggle
  `Station.pinboard_enabled`, Negativ-/Scope-Tests.
- API: `/api/v1/pinnwand/` (Liste/Erstellen/Pin/Archiv), Scopes, `/me`-Modulflag.
- Client: `WachbuchApi`-Methoden + Modell + Screen + l10n + Demo-Parity + Tests.
- Abnahme: Server-Tests + `flutter test` + Browser-Demo.

### Phase 2 – Chat im Client (öffentlich/privat/Secure Mail) `[~]`

Server-API in PR #67 (Wachenchat/privat/Secure Mail + Krypto-Identität über
`/api/v1/`), Client-E2EE + Wachenchat in Wachbuch-Client-PR #45. Die Dart-E2EE
ist byte-kompatibel und bidirektional gegen die Referenz des Web-/Server-Schemas
getestet. Offen: private/Secure-Mail-Screens im Client (API bereits vorhanden),
Merge.


Vorhandenen Server-Chat mobil verfügbar machen.

- API: versionierte Endpunkte für Wachenchat, private Threads und Secure Mail
  (Envelope-Weitergabe wie im Web, Server entschlüsselt nie).
- Client: E2EE in Dart (ECDH P-256, AES-256-GCM, HKDF-SHA-256), Schluessel-
  Entsperrung mit Passphrase im Secure Storage, Chat-/Mail-Screens.
- Abnahme: Vertrags-Tests API, Krypto-Roundtrip-Tests im Client.

### Phase 3 – Chatgruppen `[~]`

Server (Modelle + `/api/v1/chat/groups/`) in PR #68, Client (Gruppenliste +
Gruppen-Thread, Wiederverwendung der E2EE) in Wachbuch-Client-PR #46. Offen:
optionaler Web-Client für Gruppen, Merge.


Mehrpersonen-Gruppenräume zusätzlich zu 1:1 und Wachenchat.

- Server: `ChatGroup` + Mitglieder + `GroupMessage` (E2EE, `key_wraps` je
  Mitglied), Rollen/Verwaltung, Web-UI, Scope-Tests.
- Client: Gruppen-UI + Gruppen-E2EE (Rewrap bei Mitgliederänderung).

### Phase 4 – Prüf-/Wartungsfristen + QR-Geraetekarten + Erinnerungen `[ ]`

Größter Pain Point (Haftung, DGUV). Baut auf `Geraete`/`Maengel`/
`Checklisten`/Web-Push auf.

- Server: Prüffristen/Intervalle je Asset/PSA, Ablauf-Erinnerungen (Push),
  QR-Code je Gerät → Gerätekarte/Prüfhistorie/Sofort-Mangelmeldung, API.
- Client: Gerätekarte per QR-Scan (Client hat bereits `mobile_scanner`),
  Prüflisten, Erinnerungsanzeige.

### Phase 5 – Qualifikations-/Tauglichkeitsverwaltung `[ ]`

Qualifikationen/Tauglichkeiten/Lehrgänge (z. B. G26, Führerschein,
Fortbildungen) mit Ablauf-Erinnerungen. Klar abgegrenzt von voller
tarif-/arbeitszeitrechtlicher Dienstplanung.

### Phase 6 – Karten (Leaflet/MapLibre) `[ ]`

Lokal gebündelt, self-hostbare Tiles. Standorte Gerätehäuser/Wachen,
Hydranten/Löschwasser, Sammelplätze, Abfallkalender-Routen. CSP-konform via
`json_script`; Client via `flutter_map`/MapLibre. Innerhalb der Produktgrenze.

### Phase 7 – Homogenisierung `[ ]`

Einheitliche Navigation/Design-Parität Server↔Client, Modul-Toggles überall,
Barrierefreiheit, Doku (`README`, `docs/`), Aktualisierung der
Go-live-Checkliste.

## Arbeitsweise je Phase

1. Server: Modell/Migration → Service+Audit → Views/Templates → Modul-Toggle →
   Tests (inkl. Cross-Station-Negativtests).
2. API: versionierte Endpunkte + Vertrags-Tests, `/me`-Modulflag.
3. Client: `WachbuchApi` + Modell + Screen + l10n (de/en) + Demo-Parity + Tests.
4. Abnahme: Server-Tests, `flutter analyze` + `flutter test`, Browser-/Manuelltest.
5. Diesen Fahrplan-Status aktualisieren; PR mit Ursache/Risiko/Tests/Grenzen.
