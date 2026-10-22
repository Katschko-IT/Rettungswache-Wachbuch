# Wachbuch Client Roadmap

Stand: 9. August 2026

## Behörden-Wachalltag (RD · Feuerwehr · FFW · Polizei)

Fachlicher Fahrplan inkl. Webapp-Umsetzung:

→ **[docs/FAHRPLAN-BEHOERDEN.md](docs/FAHRPLAN-BEHOERDEN.md)**

Kurz: Mängel-Workflow → Statusboard → Quittierung → Anhänge → wiederkehrende
Checks → Schlüssel/Pools → Offline-Cache → Auswertung. Prototyp Phase A–D in
`landing/app/`.

## Server-Parität (Review 22. Oktober 2026)

- [x] ~~Kaffeekasse liest `balance_euros`/`results`/`amount_euros`/`reason`.~~
- [x] ~~Checklisten verarbeiten Text-Prüfpunkte und `last_completed_at`/`_by`.~~
- [x] ~~Abschluss einer Checkliste ergänzt die Karte statt sie zu leeren.~~
- [x] ~~Modul-Chips kennen alle Schlüssel aus `/api/v1/me/`.~~
- [ ] Schreibende Server-Endpunkte nutzen: Übergabe anlegen/Status,
  `PATCH /defects/{id}/`, Kalender- und Kassen-Einträge.
- [ ] `next`-Paginierung auswerten, sobald der Server sie liefert.
- [ ] Upload-Grenze mit dem Server vereinheitlichen (Client 2 MiB, Server 5 MiB).

Bericht: `docs/REVIEW-2026-10-22.md` im Server-Repository.

## Android-Ziel: 10/10 Release Engineering

Die technische Android-Härtung ist abgeschlossen und in `main` integriert.
Die Bewertung bezieht sich auf die Qualität des Repositorys und der erzeugten
Android-Artefakte. Ein öffentlicher Play-Store-Release benötigt zusätzlich
Konten, Schlüssel, Angaben und Freigaben außerhalb des Quellcodes.

### Bewertungsmatrix

| Bereich | Ziel | Status |
| --- | --- | --- |
| Signierung | Produktionsbuild nie mit Debug-Schlüssel | umgesetzt und CI-geprüft |
| Varianten | interne Test-App klar von Produktion getrennt | umgesetzt und CI-geprüft |
| Datenschutz | keine Sicherung oder Geräteübertragung sensibler App-Daten | umgesetzt und CI-geprüft |
| Transport | HTTPS-only in nicht debuggbaren Builds | umgesetzt und getestet |
| Berechtigungen | exakt genehmigte minimale Merged-Manifest-Permission-Liste | umgesetzt und CI-geprüft |
| Deep Links | strikte Strukturprüfung und getrennte interne URI | umgesetzt, 76 Tests grün |
| Optimierung | R8, Resource Shrinking, ABI-Splits und AAB | umgesetzt und CI-geprüft |
| Qualität | Analyse, Tests, warnungsfreies Lint, Größen- und Signatur-Gates | vollständig grün |
| Lieferkette | OSV-Scan, Dependabot und CycloneDX-SBOM | umgesetzt und OSV-grün |
| Auditierbarkeit | Hashes, Symbole, Zertifikats- und Abhängigkeitsberichte | umgesetzt und als Artefakte geprüft |
| Auslieferung | geschützter reproduzierbarer Signed-Release-Workflow | technisch umgesetzt; externe Secrets offen |

## Phase 0 – Ausgangslage und Risikoanalyse

- [x] ~~Tatsächlich erzeugte APK aus GitHub Actions statisch analysieren.~~
- [x] ~~APK-Größe, native Architekturen und eingebettete Scanner-Bibliotheken erfassen.~~
- [x] ~~Debug-Signierung im bisherigen Release-Build als kritischen Fehler dokumentieren.~~
- [x] ~~Fehlende Backup-Regeln, deaktiviertes Shrinking und fehlendes AAB-Gate erfassen.~~

## Phase 1 – Identität und Signierung

- [x] ~~Varianten `internal` und `production` einführen.~~
- [x] ~~Interne App mit Paket-ID `de.wachbuch.mobile.internal` kennzeichnen.~~
- [x] ~~Interne App als „Wachbuch Internal“ sichtbar machen.~~
- [x] ~~Internes Deep-Link-Schema `wachbuch-internal://` vom Produktionsschema trennen.~~
- [x] ~~Produktionssignierung aus `key.properties` oder geschützten Umgebungsvariablen laden.~~
- [x] ~~Debug-Key-Fallback aus dem Produktionsbuild entfernen.~~
- [x] ~~Build mit `REQUIRE_RELEASE_SIGNING=true` ohne vollständige Schlüsselkonfiguration hart abbrechen.~~
- [x] ~~Keystores, Zertifikate und lokale Signing-Dateien in `.gitignore` sperren.~~

## Phase 2 – Datenschutz und Angriffsfläche

- [x] ~~Cloud-Backups unter Android 11 und älter vollständig ausschließen.~~
- [x] ~~Cloud-Backup und Geräteübertragung unter Android 12+ vollständig ausschließen.~~
- [x] ~~`android:allowBackup="false"` setzen.~~
- [x] ~~Klartext-HTTP für Release und Produktion blockieren.~~
- [x] ~~Deep Links auf exakten Host, leeren Pfad und genau einen `url`-Parameter begrenzen.~~
- [x] ~~Server-URLs mit eingebetteten Zugangsdaten ablehnen.~~
- [x] ~~Kamera weiterhin als optionales Gerätefeature deklarieren.~~
- [x] ~~Unnötige Manifestangaben und veraltete API-spezifische Ressourcen entfernen.~~
- [x] ~~Merged-Manifest auf die exakt genehmigte minimale Permission-Liste begrenzen.~~
- [x] ~~Transitive `ACCESS_NETWORK_STATE`- und paketgebundene AndroidX-Receiver-Berechtigung explizit prüfen.~~

## Phase 3 – Größe, Performance und Artefakte

- [x] ~~R8-Minifizierung für Release aktivieren.~~
- [x] ~~Android Resource Shrinking aktivieren.~~
- [x] ~~Optimierte Standard-ProGuard-Konfiguration verwenden.~~
- [x] ~~Interne APKs getrennt pro ABI bauen.~~
- [x] ~~Produktion als Android App Bundle prüfen und ausliefern.~~
- [x] ~~Dart-Obfuskation mit getrennten Symbolen aktivieren.~~
- [x] ~~SHA-256-Prüfsummen für veröffentlichte Artefakte erzeugen.~~
- [x] ~~50-MiB-Budget pro interner Split-APK und 100-MiB-Budget für das AAB erzwingen.~~
- [x] ~~Minimum SDK 24 und Ziel-SDK mindestens 36 im Artefakt prüfen.~~

## Phase 4 – CI, Lieferkette und Release-Gates

- [x] ~~Flutter-Analyse und vollständige Tests als Voraussetzung beibehalten.~~
- [x] ~~Android-Lint für `productionRelease` ergänzen und alle nicht begründeten Warnungen als Fehler behandeln.~~
- [x] ~~Optionale ungenutzte Geolocator-Hintergrundklasse eng begründet aus dem Lint ausschließen, statt zusätzliche Berechtigungen anzufordern.~~
- [x] ~~Flutter-Stable-Toolchain AGP 9.0.1/Gradle 9.1.0 als kompatibles Paar dokumentieren.~~
- [x] ~~Interne APK-Signaturen mit `apksigner` prüfen.~~
- [x] ~~Paket-ID und `debuggable=false` automatisiert prüfen.~~
- [x] ~~Berechtigungs-Allowlist, Minimum-SDK und Ziel-SDK direkt aus jeder APK prüfen.~~
- [x] ~~Unsigned Production-AAB im normalen PR-CI erzwingen, damit keine Schlüssel benötigt werden.~~
- [x] ~~Flutter- und Android-Abhängigkeitsberichte als Audit-Artefakt erzeugen.~~
- [x] ~~Deterministisches CycloneDX-SBOM für Dart- und Android-Abhängigkeiten erzeugen.~~
- [x] ~~Vollständige Pub-/Maven-Abhängigkeiten mit Google OSV als hartes Schwachstellen-Gate prüfen.~~
- [x] ~~Dependabot für Pub, Gradle und GitHub Actions wöchentlich konfigurieren.~~
- [x] ~~Obfuskationssymbole als geschütztes Artefakt aufbewahren.~~
- [x] ~~Separaten, manuell auslösbaren Signed-Release-Workflow mit GitHub-Environment `google-play` ergänzen.~~
- [x] ~~Produktionszertifikat gegen signiertes AAB und jede Produktions-APK vergleichen.~~
- [x] ~~Alle neuen Flutter-, Android-, OSV- und iOS-CI-Jobs auf PR #6 erfolgreich abschließen.~~
- [x] ~~PR #6 per Squash in `main` mergen (`7fb3255`).~~

## Phase 5 – Externe Play-Store-Freigabe

Diese Punkte können nicht im Repository selbst erledigt werden und bleiben bis
zur tatsächlichen Einrichtung bewusst offen.

- [ ] Langfristigen Upload-Keystore erzeugen und offline sichern.
- [ ] GitHub-Environment `google-play` mit erforderlichen Reviewern anlegen.
- [ ] Secrets `ANDROID_UPLOAD_KEYSTORE_BASE64`, `ANDROID_UPLOAD_KEYSTORE_PASSWORD`, `ANDROID_UPLOAD_KEY_ALIAS` und `ANDROID_UPLOAD_KEY_PASSWORD` hinterlegen.
- [ ] Geschützten Workflow **Android Signed Release** erfolgreich ausführen.
- [ ] Play App Signing für `de.wachbuch.mobile` aktivieren.
- [ ] Signiertes AAB zunächst in den internen Test-Track hochladen.
- [ ] Datenschutzerklärung, Data-Safety-Formular und Berechtigungsangaben finalisieren.
- [ ] Store-Texte, Screenshots, App-Icon und Feature Graphic einreichen.
- [ ] Play-Pre-Launch-Report ohne kritische Abstürze, ANRs oder Sicherheitswarnungen abschließen.
- [ ] Optional eine eigene öffentliche Domain für verifizierte Android App Links bereitstellen.

## Definition of Done

**Technische Android-Bewertung 10/10:** Erreicht. Alle Punkte der Phasen 0 bis 4
sind abgehakt, die CI ist grün und die Änderungen sind in `main`.

**Öffentlicher Play-Store-Release abgeschlossen:** Noch offen. Zusätzlich müssen
alle verbindlichen Punkte der Phase 5 abgehakt werden. Das Repository kann diese
externen Schritte vorbereiten und prüfen, aber keine Google-Konten, Schlüssel
oder rechtlichen Erklärungen selbst erzeugen.
