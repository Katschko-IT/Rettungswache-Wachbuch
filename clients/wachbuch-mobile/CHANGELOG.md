# Changelog

Alle wesentlichen Änderungen an Wachbuch Mobile werden hier dokumentiert.

## Unreleased

- API-Vertrag mit dem Server abgeglichen (Review 2026-10-22):
  - Kaffeekasse liest die echten Serverfelder `balance_euros`, `results`,
    `amount_euros` und `reason` (zuvor immer „0,00 €“ und keine Buchungen).
  - Kassenstand zeigte statt des Währungssymbols einen Funktionsnamen
    (`Closure: …`); behoben.
  - Checklisten übernehmen Prüfpunkte, die der Server als Texte liefert, und
    leiten „erledigt“ aus `last_completed_at` und Turnus ab; der Name der
    abschließenden Person wird angezeigt.
  - Ein Abschluss ersetzt die Karte nicht mehr durch eine leere Liste,
    sondern ergänzt Zeitpunkt, Turnus und nächste Fälligkeit.
  - Modul-Chips zeigen Wachenchat, Pinnwand, Feiertage und Wetter mit Namen
    und blenden Zusatzangaben wie `holiday_state` aus.
- Gemeinsame Palette mit der Web-PWA: Primary `#0D47A1`, Fläche `#F7F9FC`.
- High-Contrast-Emergency-Themes sind an `MaterialApp` verdrahtet
  (`highContrastTheme` / `highContrastDarkTheme`).
- Logout ruft `DELETE /api/v1/token/` best-effort auf und räumt den lokalen
  Speicher danach in jedem Fall. Demo-Sitzungen bleiben ohne Netzaufruf.
- Die Vibe-P0-P3-Änderungen (nicht existierendes `geolocator 14.1.0`,
  unwirksames Certificate Pinning) sind von `main` zurückgenommen.

## 1.0.0 – Store-Release-Kandidat

### Wachalltag

- Reale Server-Parität für Übergaben, Quittierungen, Mängel, Mängelfotos,
  Geräte-/Fahrzeugstatus, Inventar/Pools, wiederkehrende Checklisten und
  Auswertungen.
- Übergaben können direkt als Mangel übernommen werden.
- Demo-Profile für Rettungsdienst, Feuerwehr, Freiwillige Feuerwehr und Polizei
  spiegeln die produktiven Kernabläufe ohne externen Demo-Server.
- Verschlüsselter, server- und tokengebundener Offline-Lesecache mit sauberer
  Bereinigung bei Logout und Serverwechsel.

### Sicherheit und Robustheit

- Strukturierter API-Fehlervertrag inklusive MFA-Codes und Correlation-ID.
- Schreibende, nicht idempotente API-Aufrufe werden nicht automatisch
  wiederholt.
- Mängelfotos werden auf Dateityp, Inhalt, Dateigröße und Serverkontingente
  begrenzt.
- Cold-Start-/Deep-Link-Sessionwechsel bereinigen alte Credentials und Caches;
  ein Link zum bereits konfigurierten Server widerruft die Sitzung nicht.

### Store-Release

- Version `1.0.0+11`.
- Production-ID Android: `de.wachbuch.mobile`.
- Bundle-ID iOS/iPadOS: `de.wachbuch.wachbuchMobile`.
- Android Signed Release mit echtem Upload-Key, API-36-, Permission-,
  Signatur-, Lint-, Größen- und SBOM-Gates.
- iOS-/TestFlight-Gates für Xcode 26+, iOS-SDK 26+, Bundle-/Build-Metadaten,
  Provisioning Profile, Codesignatur, Privacy-Manifeste und App-Validierung vor
  Upload.
- Datenschutzinformationen bereits vor Login in der App erreichbar.
- Öffentliche Datenschutz-/Support-Dokumente, Store-Metadaten, Review-Hinweise
  und verbindliche 1.0-Abnahmecheckliste ergänzt.

## Unreleased – Landingpage & Behörden-Demo

### CI

- Android-/Dependency-Workflows auf **JDK 21** (AGP 9.3 Lint braucht
  `List.removeLast()`); `BidiSpoofing` in `lint.xml` abgesichert.

### Neu

- Statische Landingpage unter `landing/` mit Projektvorstellung und interaktivem
  Demo-Modus für Rettungsdienst, Feuerwehr und Polizei.
- Webapp unter `landing/app/` im Landingpage-Design: Organisationswahl, Übersicht,
  Übergaben, Mängel-Workflow, Statusboard, Gerätepools, Quittierung, Kalender,
  Kaffeekasse, Checklisten; Profile inkl. Freiwillige Feuerwehr.
- Fachfahrplan `docs/FAHRPLAN-BEHOERDEN.md` (Phasen A–I, Server-/Mobile-Pfad).
- Offline-Demo in der App: Startbildschirm → „Demo-Modus ausprobieren“ mit
  Organisationsprofilen (RD, Feuerwehr, FFW, Polizei) und Muster-Übergaben,
  Kalender, Kaffeekasse und Checklisten.
- Flutter Phase A–D (Demo): Modelle `Defect` / `StationAsset` / `HandoverAck`,
  Contract `docs/SCHEMA-WACHALLTAG.md`, Mängel-Screen, Statusboard auf der
  Übersicht, Quittierung im Übergabe-Detail.
- Flutter HTTP für `defects` / `assets` / `inventory` / `acks` verdrahtet
  (404 = Modul nicht verfügbar); Demo-API + Inventar-Checkout; Checklisten mit
  `interval` / `due_next` / `overdue`.
- Webapp: Demo-Anhänge (Phase E), Fälligkeitsbereich Checklisten (F),
  Auswertung (I), Inventar bereits unter Geräte (G).
- Gelbes Demo-Banner in der App-Shell, analog zum Server-Demo-Modus.

## Unreleased – Module API (Kalender, Kaffeekasse, Checklisten)

### Neu

- Doku-Sync: Server-Versionspaarung dokumentiert
- `GET /api/v1/kalender/` – Wachenkalender mit Terminen (Titel, Beschreibung, Start/Ende, Ganztag, Ort).
- `GET /api/v1/kaffeekasse/` – Kassenstand, Zahlungshinweise und letzte Buchungen (Ledger).
- `GET /api/v1/checklisten/` – Checklisten mit Punkten und Abhak-Status.
- `POST /api/v1/checklisten/{id}/abschluss/` – Checklisten serverseitig abschließen (append-only) mit optimistischer UI und Rollback bei Fehler.
- Getypte Datenmodelle für die drei neuen Bereiche mit defensiver JSON-Serialisierung.
- Schnellzugriff-Kacheln auf dem Übersicht-Dashboard, die nur für aktivierte Module erscheinen und per Navigator die jeweiligen Screens öffnen.
- Responsive Material-3-Screens mit Ladefehler-/Leerzustand, `RefreshIndicator` und Fehler-Banner.
- Bottom-Navigation (Phone) und NavigationRail (Tablet) bleiben erhalten; die neuen Screens werden zusätzlich über tappbare Kacheln erreichbar.

### Tests

- Modell-Tests (JSON-Serialisierung, Alias-Felder, fehlerhafte Eingaben).
- API-Service-Tests mit Mock-Responses für alle vier Endpunkte.
- Widget-Tests für die drei neuen Screens inkl. Abschluss- und Fehlerrollback-Flow.
- Dashboard-Test für die Modul-Kacheln und die Navigation in die neuen Screens.

## Unreleased – Android Release Hardening

### Sicherheit und Auslieferung

- Interne und produktive Android-Varianten besitzen getrennte Paket-IDs, Namen und Deep-Link-Schemas.
- Produktionsbuilds fallen nicht mehr auf den Android-Debug-Key zurück.
- Produktive Signierung wird ausschließlich aus privater lokaler Konfiguration oder geschützten CI-Secrets geladen.
- Cloud-Backup und Geräteübertragung sind für sämtliche App-Daten ausgeschlossen.
- Deep-Links prüfen jetzt exakten Host, leeren Pfad, genau einen URL-Parameter und lehnen eingebettete Zugangsdaten ab.
- R8-Minifizierung, Resource Shrinking, ABI-Splits und Dart-Obfuskation sind für Release-Builds aktiviert.

### Qualität und Nachvollziehbarkeit

- Android-Lint, Signatur-, Paket-ID-, Debbugable- und Größenprüfungen wurden als CI-Gates ergänzt.
- CI erzeugt SHA-256-Hashes, Obfuskationssymbole und Flutter-/Android-Abhängigkeitsberichte.
- Geschützter Workflow für signierte AAB- und APK-Artefakte mit temporärem Upload-Keystore ergänzt.
- Dauerhafte Android-10/10-Roadmap sowie Installations- und Play-Store-Dokumentation ergänzt.

## 0.5.1 – 2026-08-02

### Sicherheit und Robustheit

- Deep-Links im laufenden Betrieb fragen nach, bevor eine aktive Sitzung auf einen anderen Server umgestellt wird.
- Gespeicherte Server-URLs werden beim Start erneut gegen die HTTPS-Regeln geprüft.
- App-Tokens speichern und prüfen `expires_at`; abgelaufene Sitzungen landen auf dem Login mit Hinweis.
- MFA-Antworten werden über den API-Code `mfa_required` erkannt, nicht nur über den Text.
- Discovery akzeptiert nur Antworten, die wie ein Wachbuch-`/api/v1/`-Root aussehen.
- Standort für das Solar-Theme wird nicht mehr ungefragt angefordert (System-Theme-Fallback).

### Optimierungen

- Übersicht und Übergaben laden parallel (`Future.wait`).
- Tab-Wechsel behält Filterzustand (`IndexedStack`).
- Überlappende Reloads werden per Generationszähler verworfen.
- Modul-Chips zeigen deutsche Bezeichnungen statt API-Schlüssel.
- Passwort-/Token-Felder werden nach erfolgreicher Anmeldung geleert.

## 0.5.0 – 2026-08-02

### Design und Lesbarkeit

- Durchgängiges, deterministisches Weiß-Blau-Designsystem für helles und dunkles Erscheinungsbild.
- Lesbare Typografie mit mindestens 14 sp für Hinweise, Metadaten und Statusbeschriftungen.
- Neu gestaltete Übersicht mit Wachen-Header und drei schnell erfassbaren Statuskarten.
- Übergabekarten mit klarer Prioritätsmarkierung, größeren Abständen und kontrastgesicherten Chips.
- Strukturierte Suche und Filter mit größeren Touch-Zielen und eindeutiger visueller Hierarchie.
- Kontrastreiche Fehlerbanner mit Icon und Screenreader-Live-Region auf allen betroffenen Screens.
- Lange Wachennamen werden in der App-Bar kontrolliert gekürzt; Karten bleiben bei 200 % Textskalierung überlauffrei.

### Qualität

- Reale Smartphone-Screenshots vor und nach der Überarbeitung mit Vision geprüft.
- Theme-, Kontrast-, Semantik-, Dashboard- und Lesbarkeits-Regressionstests ergänzt.
- Offizielle Flutter-Material-3- und Accessibility-Muster sowie offene Designsysteme als Referenz ausgewertet.

## 0.4.0 – 2026-08-02

### Neu

- Material-3-Suche über Titel, Kategorie, Status und Priorität der aktiven Übergaben.
- Kombinierbare Status- und Prioritätsfilter mit einsatzgerechter Reihenfolge „Dringend → Wichtig → Normal“.
- Lokalisierte, farbige Chips statt technischer API-Werte.
- Ergebniszähler und eigener Leerzustand für Filter ohne Treffer.
- Antippbare Übergabekarten mit Detail-Bottom-Sheet für Beschreibung, Autor, Änderungszeit und Version.
- Dashboard-Zusammenfassung für offene, laufende und dringende Übergaben.

### Qualität

- Filterlogik als reine, defensiv gegen fehlende Felder getestete Funktion ausgelagert.
- API-Vertrag für `GET /api/v1/handovers/{id}/` durch Regressionstest abgesichert.
- Smartphone- und Tablet-Layouts für die neuen Karten und Filter getestet.
- Detailaufrufe bleiben auch bei UI-Rebuilds auf genau einen HTTP-Request begrenzt.
- Aktive Filter bleiben nach einem Daten-Reload sichtbar und entfernbar.
- Unerwartete optionale API-Feldtypen führen nicht zum Absturz der Karten oder Detailansicht.
- Übergabekarten passen ihre Höhe bis mindestens 200 % Textskalierung ohne Überlauf an.

## 0.3.0 – 2026-08-02

### Neu

- Responsives Material-3-Layout für Smartphone und Tablet durch Regressionstests abgesichert.
- Automatischer Wechsel zwischen hellem und dunklem Design anhand lokal berechnetem Sonnenaufgang und Sonnenuntergang.
- Ungefährer Vordergrundstandort wird ausschließlich auf dem Gerät verarbeitet; keine externe Wetter- oder Standort-API.
- Fallback auf das Systemdesign, wenn Standortdienste deaktiviert oder die Berechtigung verweigert sind.
- Automatische Neuberechnung beim nächsten Sonnenwechsel und nach Rückkehr in die App.
- Vollständige Deep-Link-Unterstützung für `wachbuch://connect?url=…` unter Android und iOS.

### Sicherheit

- Ein Serverwechsel über Deep-Link löscht den alten App-Token, bevor die neue Adresse übernommen wird.
- Release-Builds lehnen unsichere HTTP-Server ab; HTTP bleibt nur in Debug-Builds explizit möglich.
- Temporäre und langlebige HTTP-Clients werden deterministisch geschlossen.

## 0.2.1 – 2026-08-02

### Geändert

- Flutter-Projekt vollständig in das eigenständige Client-Repository übernommen.
- API-Aufrufe erhalten ein konfigurierbares Zeitlimit von standardmäßig 20 Sekunden.
- Verständliche Meldungen für Netzwerkfehler, Zeitüberschreitungen, Reverse-Proxy-Fehler und ungültige Serverantworten.
- Lifecycle-Race behoben: späte API-Antworten lösen nach dem Schließen eines Screens kein `setState()` mehr aus.
- QR- und Serveradressen lehnen fremde Schemes, unvollständige Wachbuch-Links und beschädigte JSON-Payloads sauber ab.

### Tests

- API-Vertrag: Discovery, Token-Anmeldung, Auth-Header und Fehlerpfade.
- Secure Storage und Shared Preferences.
- Startflow, Formvalidierung und responsive Hauptnavigation.
- Regressionstest für späte API-Fehler nach Widget-Dispose.

### Android

- Installierbare Sideload-APK für Android 7.0 und neuer.
- Release-Build bleibt für lokale/CI-Verteilung mit Debug-Key signiert; Play-Store-Veröffentlichung benötigt einen eigenen Upload-Key.
