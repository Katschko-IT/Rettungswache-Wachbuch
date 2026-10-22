# AGPL-Client (iOS / Android)

Stand: 10. August 2026.

## Kanonische Repositories

| | |
| --- | --- |
| **Server** | https://github.com/Katschko-IT/Rettungswache-Wachbuch · `0.24.x` |
| **Client** | https://github.com/Katschko-IT/Wachbuch-Client · `1.0.x` |
| **API** | `/api/v1/` · OpenAPI `1.2.2` |
| **Historischer Spiegel** | `clients/wachbuch-mobile/` – nicht als Quelle verwenden |

**Wachbuch-Client ist die einzige Quelle der Wahrheit für Flutter/iOS/Android.** Der Server koppelt sich über den versionierten API-Vertrag an die App. Der historische Client-Ordner im Server-Repository darf keine neueren Client-Commits überschreiben; der frühere Publish-Workflow ist deshalb deaktiviert.

## Versionspaarung

| Server | Client | Hinweis |
| --- | --- | --- |
| `0.16.x` | `0.6.x` | realer Wachalltag: Mängel, Fotos, Assets, Inventar, Quittierungen, wiederkehrende Checks, Reports, Offline-Lesen |
| `0.15.x` | `0.5.1+` | vorheriger Kern-/Demo-Stand |
| `0.14.1` | `0.5.0+` | API v1, App-Tokens, MFA |

## Verbindungsablauf

```text
App                         Wachbuch-Server
────────────────────────    ──────────────────────────────────
1. Adresse oder QR          GET  /api/v1/             Discovery
2. App-Token / Login        POST /api/v1/token/       MFA-Regeln gelten
3. Sitzung                  GET  /api/v1/me/          User + Station + Module
4. Übergaben                /handovers/ + /acks/
5. Wachalltag               /defects/ /assets/ /inventory/
6. Checks/Reports           /checklisten/ /reports/
7. Mängelfotos              /defects/{id}/attachments/
8. Logout                   DELETE /api/v1/token/     best-effort, danach lokal
```

Header: `Authorization: Token <wb_…>`.

## MFA

Für produktive Nutzung ist ein im Web unter `/konto/api/` erzeugtes App-Token der bevorzugte Weg. Der Login-/Token-Endpunkt unterscheidet `mfa_required` und `mfa_setup_required`, damit der Client einen konkreten Hinweis statt eines generischen Fehlers anzeigen kann.

## Offline-Modell

Der `0.6.x`-Client besitzt einen verschlüsselten Lesecache, der an Server und Token gebunden ist. Er wird nur bei Netzwerkfehlern als Fallback benutzt. Authentifizierungs-/Autorisierungsfehler (`401`/`403`) dürfen nicht durch Cache-Daten kaschiert werden.

Offline-Schreiben bzw. eine allgemeine Synchronisationswarteschlange ist bewusst nicht Teil dieses Vertrags; damit entstehen keine schwer auflösbaren Konflikte bei Mängeln, Fotos, Inventar oder Checklisten.

## Mutationen und Wiederholung

Automatische Retries sind nur für GETs bzw. serverseitig nachweislich idempotente Aktionen erlaubt. Token-Erzeugung, neue Mängel, Foto-Uploads, Stammdaten und Checklistenabschluss werden nicht automatisch erneut gesendet. Quittierung und bestimmte Zustandsoperationen besitzen serverseitige Schutzmechanismen gegen Duplikate.

## Produktiver Wachalltag

Der Client `0.6.x` kann gegen Server `0.16.x`:

- Übergaben lesen, filtern und quittieren
- eine Übergabe als Mangel übernehmen
- Mängel anlegen, priorisieren, terminieren und bearbeiten
- Mängelfotos aus Kamera/Mediathek hochladen
- Fahrzeug-/Gerätestatus anzeigen und ändern
- Schlüssel-/Poolgeräte ausgeben/zurückgeben
- wiederkehrende Checklisten abarbeiten
- Stationsauswertung öffnen
- erfolgreiche Leseantworten offline verfügbar halten

Demo-Profile verwenden denselben fachlichen UI-Pfad, werden aber lokal simuliert. Ziel der Demo ist damit nicht mehr ein separater Funktionsumfang, sondern die Vorschau auf reale Serverfunktionen.

## Wachenspezifisch

- Mitgliedschaften werden nur auf dem Server verwaltet.
- Die App liest `membership.station` und aktivierte Module aus `/me/`.
- Alle produktiven Ressourcen sind stationsisoliert.
- Es gibt keinen stillen stationsübergreifenden Offline-Fallback.

## Android / iOS

Android und iOS werden ausschließlich im `Wachbuch-Client`-Repository gebaut und getestet. Vor Freigabe müssen Flutter-Analyse/Tests, Android-Build/Lint/Sicherheitsgates, iOS-CI und Dependency-Security grün sein.

Für Pilot-/Store-Abläufe gelten die aktuellen Dokumente im Client-Repository, insbesondere `docs/E2E-WACHALLTAG.md`, `docs/PILOT-WACHALLTAG.md`, `docs/PLAY-STORE.md` und `docs/IOS-TESTFLIGHT.md`.

## Produktgrenze

Nicht Teil des Clients/API-Vertrags sind Patienten-/Einsatz-/Alarmierungsdaten, ePCR, Personalakten, vollständige Dienstplanung, Abrechnung oder individuelle Leistungskennzahlen.

## Lizenz

AGPL-3.0-or-later in beiden Repositories.
