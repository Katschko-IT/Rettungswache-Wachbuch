# Android installieren und intern testen

Stand: 10. August 2026

Für die öffentliche Google-Play-Freigabe gilt zusätzlich
[`PLAY-STORE.md`](PLAY-STORE.md). Die verbindliche 1.0-Abnahme steht in
[`STORE-RELEASE-1.0.md`](STORE-RELEASE-1.0.md). Für Upgrades vorhandener Installationen gilt zusätzlich [`SECURE-STORAGE-MIGRATION-1.0.md`](SECURE-STORAGE-MIGRATION-1.0.md).

## Varianten

| Variante | Paket-ID | Anzeige | Verwendung |
| --- | --- | --- | --- |
| Internal | `de.wachbuch.mobile.internal` | Wachbuch Internal | Entwicklung, CI und kontrolliertes Sideloading |
| Production | `de.wachbuch.mobile` | Wachbuch | signierte Freigaben und Google Play |

Die interne APK ist zwar mit dem Android-Debug-Key signiert, trägt aber eine
eigene Paket-ID, einen eindeutigen Namen und das Deep-Link-Schema
`wachbuch-internal://`. Sie wird niemals als produktive oder Play-fähige APK
bezeichnet.

## Voraussetzungen

1. Android 7.0 oder neuer
2. laufender Wachbuch-Server mit `/api/v1/` oder lokaler Demo-Modus
3. für nicht debuggbare Serververbindungen eine gültige HTTPS-Adresse
4. für Sideloading die Installation aus der verwendeten Datei-App erlauben

## CI-Artefakt installieren

1. In GitHub Actions den erfolgreichen Workflow **Flutter CI** öffnen.
2. Artefakt `wachbuch-internal-apks` laden.
3. Die zu deinem Gerät passende APK auswählen:
   - `arm64-v8a`: praktisch alle aktuellen Android-Geräte
   - `armeabi-v7a`: ältere 32-Bit-Geräte
   - `x86_64`: Emulatoren und wenige Spezialgeräte
4. Den Hash aus `SHA256SUMS` prüfen.
5. APK übertragen und installieren.
6. Die App **Wachbuch Internal** starten.

Beispiel:

```bash
sha256sum -c SHA256SUMS
```

## Interne APKs selbst bauen

```bash
./scripts/build-apk.sh
```

Das Skript führt Tests aus und erstellt obfuskierte, R8-optimierte Split-APKs.

## Produktions-AAB 1.0 bauen

Produktionsartefakte benötigen einen eigenen Upload-Key. Es gibt keinen
Debug-Key-Fallback.

```bash
cp android/key.properties.example android/key.properties
# private Werte eintragen
./scripts/build-aab.sh
```

`build-aab.sh` liest Version und Buildnummer standardmäßig direkt aus
`pubspec.yaml` (`1.0.0+12`) und bricht ab, wenn man per `BUILD_NAME` oder
`BUILD_NUMBER` einen davon abweichenden Store-Build anfordert.

Alternativ den geschützten GitHub-Workflow **Android Signed Release** verwenden.
Details und Secret-Namen stehen in [`PLAY-STORE.md`](PLAY-STORE.md).

## Upgrade von Build +11

Build `1.0.0+12` aktualisiert `flutter_secure_storage` kontrolliert auf 10.3.1. Bestehende Installationen **nicht vorher deinstallieren**, wenn der Erhalt von Test-Token/Offline-Cache geprüft werden soll. Auf mindestens einem realen Gerät müssen Sitzung, Offline-Cache, Logout, Serverwechsel und ein unterbrochener erster Storage-Zugriff gemäß [`SECURE-STORAGE-MIGRATION-1.0.md`](SECURE-STORAGE-MIGRATION-1.0.md) getestet werden.

## Erster Start

1. Serveradresse eingeben oder QR-Code scannen – alternativ Demo-Modus öffnen.
2. Die erkannte HTTPS-Adresse kontrollieren und bestätigen.
3. Benutzername und Passwort verwenden; bei MFA einen App-Token einsetzen.
4. Kamera nur bei QR-Scan oder ausdrücklich ausgelöstem Mängelfoto freigeben.
5. Ungefähren Standort nur für das automatische Tag-/Nacht-Design freigeben;
   bei Ablehnung bleibt die Kernfunktion nutzbar.
6. Datenschutzinformationen sind bereits auf dem ersten Bildschirm erreichbar.

QR im Server-Web: **Mein Konto → App-Tokens**.

## Deep Links

| Variante | Schema |
| --- | --- |
| Production | `wachbuch://connect?url=…` |
| Internal | `wachbuch-internal://connect?url=…` |

Die App akzeptiert nur den Host `connect`, keinen zusätzlichen Pfad, genau einen
`url`-Parameter und keine eingebetteten Zugangsdaten. Ein Link zu einem anderen
Server beendet die alte Sitzung und entfernt deren Offline-Cache; ein Link zum
bereits eingerichteten Server lässt die gültige Sitzung bestehen.

## Sicherheitseigenschaften

- kein Klartext-HTTP in nicht debuggbaren Builds
- Token über Secure Storage beziehungsweise Android Keystore
- Secure Storage 10.3.1 mit RSA-OAEP/SHA-256 + AES-GCM und expliziter crash-resistenter Migration
- server-/tokengebundener verschlüsselter Offline-Lesecache
- Logout und Serverwechsel bereinigen Token und zugehörigen Cache
- keine Cloud-Sicherung und keine Geräteübertragung der App-Daten
- kein Zugriff auf Kontakte, Mikrofon oder Hintergrundstandort
- interne und produktive Installationen überschreiben einander nicht
- Produktionsbuilds werden ohne privaten Schlüssel nicht signiert
- Production-AAB muss API 36+ targeten

## Troubleshooting

| Problem | Lösung |
| --- | --- |
| APK lässt sich nicht installieren | passende ABI wählen und Installation aus dieser Quelle erlauben |
| „App nicht installiert“ bei Update | Signatur muss zur bereits installierten Variante passen; gegebenenfalls Internal deinstallieren |
| HTTP wird blockiert | für Internal/Release HTTPS verwenden; nur echter Debug-Build erlaubt LAN-HTTP |
| Kamera verweigert | Serveradresse manuell eingeben; Mängel ohne Foto dokumentieren |
| Standort verweigert | Systemtheme wird verwendet |
| 403 bei MFA | App-Token statt Passwort verwenden |
| 401 nach Tokenablauf | erneut anmelden beziehungsweise Token erneuern |
| Upgrade verliert Sitzung | Rollout stoppen; Migrationsmatrix/CI prüfen und nicht auf 9.x downgraden, bevor der migrierte Storage getestet wurde |
