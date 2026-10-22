# Google Play Store – Freigabehandbuch

Stand: 10. August 2026

Der verbindliche 1.0-Abnahmeplan liegt in [`STORE-RELEASE-1.0.md`](STORE-RELEASE-1.0.md). Für bestehende Installationen ist zusätzlich [`SECURE-STORAGE-MIGRATION-1.0.md`](SECURE-STORAGE-MIGRATION-1.0.md) verbindlich.

## Offizielle Grundlagen

- [Target-API-Anforderungen](https://support.google.com/googleplay/android-developer/answer/11926878)
- [App-Signierung und Play App Signing](https://developer.android.com/studio/publish/app-signing)
- [Android App Bundles](https://developer.android.com/guide/app-bundle)
- [Automatische Sicherung](https://developer.android.com/identity/data/autobackup)
- [Network Security Configuration](https://developer.android.com/privacy-and-security/security-config)
- [Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469)
- [App access / Review-Zugang](https://support.google.com/googleplay/android-developer/answer/15748846)

Ab dem 31. August 2026 müssen neue Apps und Updates Android 16 beziehungsweise API 36 oder höher als Ziel verwenden. Das Projekt übernimmt `targetSdk` aus Flutter Stable und der Produktions-Release-Workflow bricht ab, wenn der fertige APK-Build unter API 36 liegt.

## 1.0-Identität

| Variante | Paket-ID | Name | Signierung | Zweck |
| --- | --- | --- | --- | --- |
| `internal` | `de.wachbuch.mobile.internal` | Wachbuch Internal | Android-Debug-Key | CI, Entwicklung und kontrolliertes Sideloading |
| `production` | `de.wachbuch.mobile` | Wachbuch | eigener Upload-Key | Google Play und produktive APK-Verteilung |

Die interne Variante ist bewusst als eigene App installierbar und verwendet das separate URI-Schema `wachbuch-internal://`.

## Upload-Key erzeugen

Der Upload-Key darf nicht ins Repository gelangen. Beispiel:

```bash
keytool -genkeypair -v \
  -keystore wachbuch-upload.jks \
  -alias wachbuch-upload \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10000
```

Den Keystore verschlüsselt offline sichern. Für Google Play **Play App Signing** aktivieren, damit der App-Signaturschlüssel getrennt vom Upload-Key verwaltet wird.

## Lokale Signing-Konfiguration

```bash
cp android/key.properties.example android/key.properties
```

Danach die realen Werte in `android/key.properties` eintragen. Die Datei und übliche Keystore-Endungen sind durch `.gitignore` ausgeschlossen.

Alternativ akzeptiert Gradle:

- `ANDROID_KEYSTORE_PATH`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Mit `REQUIRE_RELEASE_SIGNING=true` bricht der Build ab, falls ein Wert fehlt. Einen Debug-Key-Fallback für `production` gibt es nicht.

## Lokaler 1.0-Produktionsbuild

```bash
BUILD_NAME=1.0.0 BUILD_NUMBER=12 ./scripts/build-aab.sh
```

Direkter Flutter-Aufruf:

```bash
REQUIRE_RELEASE_SIGNING=true flutter build appbundle \
  --release \
  --flavor production \
  --build-name 1.0.0 \
  --build-number 12 \
  --obfuscate \
  --split-debug-info=build/symbols/production
```

## Secure-Storage-Migrationsbuild

Build `1.0.0+12` aktualisiert `flutter_secure_storage` auf 10.3.1 und aktiviert die kontrollierte Android-Migration mit `migrateOnAlgorithmChange=true` sowie `migrateWithBackup=true`. Die Produktions-App bleibt von Android-Cloud-Backup/Geräteübertragung ausgeschlossen.

Vor einem breiten Rollout muss mindestens ein echtes Upgrade **von einer bestehenden +11/9.x-Installation auf +12** geprüft werden. Dabei müssen bestehender App-Token und Offline-Cache erhalten bleiben; zusätzlich sind Logout, Serverwechsel sowie ein absichtlich unterbrochener erster Storage-Zugriff und anschließendes Recovery zu testen. Details: [`SECURE-STORAGE-MIGRATION-1.0.md`](SECURE-STORAGE-MIGRATION-1.0.md).

Ein späteres Upgrade auf `flutter_secure_storage` 11.x ist ein eigener Breaking-Change und wird nicht zusammen mit diesem Release freigegeben.

## Geschützter GitHub-Release

GitHub Environment `google-play` mit mindestens einem Required Reviewer anlegen. Secrets:

| Secret | Inhalt |
| --- | --- |
| `ANDROID_UPLOAD_KEYSTORE_BASE64` | Base64-kodierter Upload-Keystore |
| `ANDROID_UPLOAD_KEYSTORE_PASSWORD` | Keystore-Passwort |
| `ANDROID_UPLOAD_KEY_ALIAS` | Alias des Upload-Schlüssels |
| `ANDROID_UPLOAD_KEY_PASSWORD` | Schlüsselpasswort |

Der Workflow **Android Signed Release**:

1. darf nur von `main` laufen,
2. verlangt, dass Build-Name/-Nummer exakt `pubspec.yaml` entsprechen,
3. validiert alle Signing-Secrets,
4. installiert den Keystore nur temporär,
5. führt Analyse, L10n-Generierung und Tests aus,
6. baut signiertes Production-AAB und signierte ABI-APKs,
7. führt Android-Lint aus,
8. prüft Paket-ID, `debuggable=false`, min/target SDK, Permission-Allowlist, Signaturen und Größenbudgets,
9. erzeugt Hashes, Zertifikatsbericht, Abhängigkeitsberichte, Symbole und CycloneDX-SBOM,
10. entfernt den temporären Keystore auch bei Fehlern.

Das erzeugte `.aab` zunächst **manuell in den internen Play-Test-Track** hochladen. Eine automatische Produktionseinreichung ist absichtlich nicht im Repository aktiviert.

## Datenschutz und Berechtigungen

| Permission | Zweck | Verhalten ohne Freigabe |
| --- | --- | --- |
| `INTERNET` | Verbindung zum selbst gehosteten Wachbuch-Server | Servermodus nicht nutzbar; Demo bleibt lokal |
| `CAMERA` | QR-Scan und ausdrücklich ausgelöstes Mängelfoto | Serveradresse manuell; Mangel ohne Kamera möglich |
| `ACCESS_COARSE_LOCATION` | lokale Sonnenaufgang-/Sonnenuntergangsberechnung | Systemtheme als Fallback |
| `ACCESS_NETWORK_STATE` | Offline-/Online-Status | technische Netzwerkfunktion |

Nicht vorgesehen sind Hintergrundstandort, Kontakte, Mikrofon, SMS/Anruflisten oder breite Datei-/Medienspeicherberechtigungen.

QR-Kameraframes werden nicht als Foto gespeichert/hochgeladen. Ausdrücklich ausgewählte Mängelfotos werden dagegen an den eingerichteten selbst gehosteten Server übertragen. Aktuelle Serverstände normalisieren gespeicherte Mängelfotos serverseitig als metadata-freies JPEG. Standortdaten verlassen nach aktuellem App-Konzept das Gerät nicht.

Android-Appdaten sind von Cloud-Backups und Geräteübertragungen ausgeschlossen.

## Datenschutzerklärung und Data Safety

Öffentliche Datenschutzerklärung:

`https://github.com/Katschko-IT/Wachbuch-Client/blob/main/docs/PRIVACY-POLICY.md`

Die App zeigt die wesentlichen Datenschutzinformationen zusätzlich **vor dem Login** an.

Konservativer Data-Safety-Abgleich für 1.0:

- kein Werbe-/Tracking-SDK und keine externe Analytics-/Crash-Telemetrie,
- Login-/App-Token-Kommunikation nur mit dem vom Nutzer gewählten Wachbuch-Server,
- Organisations-/Benutzerkennungen und nutzergenerierte Wachalltag-Inhalte können auf diesem Server für App-Funktion gespeichert werden,
- ausdrücklich ausgewählte Mängelfotos können auf diesem Server gespeichert werden,
- QR-Kameraframes lokal,
- ungefährer Standort lokal und nicht übertragen,
- Transportverschlüsselung per HTTPS im Produktionsmodus.

Die endgültigen Play-Console-Antworten müssen mit dem tatsächlich betriebenen Review-/Produktionsserver übereinstimmen.

## App access / Google Review

Der Demo-Modus ist ohne Login vom ersten Bildschirm erreichbar. In der Play Console die englische Review-Anweisung aus [`STORE-METADATA.md`](STORE-METADATA.md) übernehmen.

Wenn Google zusätzlich den echten Serverfluss prüfen soll, einen **dedizierten Review-Server** und dauerhaft gültige, wiederverwendbare Zugangsdaten hinterlegen. Keine Produktionsnutzer und keine Einmal-MFA-Codes verwenden.

## Store Listing

Texte, Positionierung und Screenshotplan liegen in [`STORE-METADATA.md`](STORE-METADATA.md). Wichtig:

- nicht als offizielle Behörden-App darstellen,
- nicht als Medizin-/Patienten-/Einsatzleit-App darstellen,
- nur echte Screenshots des 1.0-Builds mit Demo-Daten,
- keine echten Namen, Tokens, Serveradressen, Patienten- oder Einsatzdaten.

## Upload-Reihenfolge

1. App `de.wachbuch.mobile` in Play Console anlegen.
2. Play App Signing aktivieren.
3. GitHub **Android Signed Release** auf `main` für `1.0.0+12` ausführen.
4. Signiertes AAB in den internen Test-Track laden.
5. App access, Data Safety, Datenschutz, Altersfreigabe/Zielgruppe und Store Listing ausfüllen.
6. Upgrade von +11 auf +12 auf echtem Gerät inklusive Secure-Storage-Recovery testen.
7. Interne Tester auf Login, Demo, QR, Deep Link, Standort-/Kameraverweigerung, Tablet, Rotation, Offline/Logout/Serverwechsel testen lassen.
8. Pre-Launch-Report prüfen und kritische Abstürze, ANRs, Permission- oder Policyfehler beheben.
9. Erst danach Production-Release einreichen beziehungsweise stufenweise ausrollen.
