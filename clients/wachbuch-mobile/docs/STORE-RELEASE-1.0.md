# Store Release 1.0 – Abnahmeplan

Stand: 10. August 2026  
Geplanter Build: **1.0.0+12**

Dieses Dokument trennt automatisch prüfbare Release-Gates von Schritten, die zwingend in Apple Developer / App Store Connect beziehungsweise Google Play Console durchgeführt werden müssen.

## 1. Fest verdrahtete Identitäten

| Plattform | Produktions-ID | Store-Artefakt |
| --- | --- | --- |
| Android | `de.wachbuch.mobile` | signiertes Android App Bundle (`.aab`) |
| iOS/iPadOS | `de.wachbuch.wachbuchMobile` | signierte App-Store-IPA / App-Store-Connect-Build |

Diese IDs nach der ersten Store-Anlage **nicht mehr ändern**.

## 2. Automatische Merge-Gates

Vor Merge des 1.0-Branches müssen erfolgreich sein:

- `flutter pub get`
- unverändertes, committed `pubspec.lock`
- `flutter gen-l10n`
- `flutter analyze`
- vollständige Flutter-Test-Suite
- Secure-Storage-Regressionsprüfung (`flutter_secure_storage` 10.3.1, explizite Migration + Crash-Backup)
- Android Internal APKs
- Android Production-AAB-Kompilierung
- Android Lint
- Paket-ID-, Permission-, debuggable-, SDK-, Signatur- und Größenprüfungen
- CycloneDX-SBOM / Dependency-Security
- iOS Simulator-Build
- iOS Release-Build ohne Signierung
- Xcode **26+** und iOS SDK **26+** im iOS-CI
- Validierung aller im finalen Bundle vorhandenen `PrivacyInfo.xcprivacy`-Dateien

## 3. Secure-Storage-Migration 9.x → 10.3.1

Build `1.0.0+12` ist der verpflichtende Migrationsschritt für bestehende lokale App-Tokens und Offline-Caches. Android verwendet zentral:

```dart
AndroidOptions(
  migrateOnAlgorithmChange: true,
  migrateWithBackup: true,
)
```

Vor öffentlichem Rollout muss die Upgrade-Testmatrix in [`SECURE-STORAGE-MIGRATION-1.0.md`](SECURE-STORAGE-MIGRATION-1.0.md) auf echten Geräten bestanden sein. Ein direkter Sprung einer bestehenden 9.x-Installation auf eine spätere 11.x-Linie ist für Wachbuch nicht freigegeben.

Die iOS-Keychain-Policy wird in diesem Schritt bewusst nicht gleichzeitig auf Secure Enclave oder andere Accessibility-Attribute umgestellt. Das reduziert die Zahl gleichzeitig migrierter Sicherheitsmechanismen.

## 4. Store-Signing

### Android

GitHub Environment: `google-play`

Erforderliche Secrets:

- `ANDROID_UPLOAD_KEYSTORE_BASE64`
- `ANDROID_UPLOAD_KEYSTORE_PASSWORD`
- `ANDROID_UPLOAD_KEY_ALIAS`
- `ANDROID_UPLOAD_KEY_PASSWORD`

Der Release-Workflow akzeptiert keinen Debug-Key als Fallback und darf nur auf `main` gestartet werden. Build-Name und Build-Nummer müssen exakt `pubspec.yaml` entsprechen.

Empfehlung: Play App Signing aktivieren und den lokalen/GitHub-Schlüssel nur als **Upload Key** verwenden. Upload-Key verschlüsselt offline sichern.

### iOS

GitHub Environment: `testflight`

Erforderliche Secrets:

- `APPLE_TEAM_ID`
- `APP_STORE_CONNECT_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`
- `APP_STORE_CONNECT_PRIVATE_KEY_BASE64`
- `IOS_DISTRIBUTION_CERTIFICATE_BASE64`
- `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD`
- `IOS_PROVISIONING_PROFILE_BASE64`
- `IOS_KEYCHAIN_PASSWORD`

Der Workflow prüft Xcode/iOS-SDK, Version, Provisioning-Profile-Bundle-ID, archivierte Bundle-ID/Version/Build, Export-Compliance-Flag, Codesignatur und vorhandene Privacy-Manifeste. Die exportierte IPA wird mit `altool --validate-app` validiert, bevor sie zu App Store Connect hochgeladen wird.

## 5. Öffentliche Store-Dokumente

Für 1.0 vorhanden:

- [`PRIVACY-POLICY.md`](PRIVACY-POLICY.md)
- [`SUPPORT.md`](SUPPORT.md)
- [`STORE-METADATA.md`](STORE-METADATA.md)
- [`SECURE-STORAGE-MIGRATION-1.0.md`](SECURE-STORAGE-MIGRATION-1.0.md)

Direkt verwendbare öffentliche Übergangs-URLs:

- Datenschutz: `https://github.com/Katschko-IT/Wachbuch-Client/blob/main/docs/PRIVACY-POLICY.md`
- Support: `https://github.com/Katschko-IT/Wachbuch-Client/blob/main/docs/SUPPORT.md`
- Marketing/Projekt: `https://github.com/Katschko-IT/Wachbuch-Client`

Eine eigene Domain kann diese URLs später ersetzen; die Store-Angaben und die In-App-Erklärung müssen dann synchron aktualisiert werden.

## 6. Apple Developer / App Store Connect – manuell

Vor dem ersten Upload:

- [ ] Apple Developer Program aktiv.
- [ ] Explicit App ID `de.wachbuch.wachbuchMobile` angelegt.
- [ ] App in App Store Connect mit derselben Bundle-ID angelegt.
- [ ] Distribution-Zertifikat und App-Store-Provisioning-Profile erzeugt.
- [ ] App Store Connect API Key mit minimal notwendigen Rechten erzeugt.
- [ ] GitHub Environment `testflight` mit Required Reviewer konfigurieren.
- [ ] Secrets eintragen; Schlüssel niemals committen.
- [ ] **EU-DSA-Trader-Status** in App Store Connect bewusst festlegen. Apple verlangt die Erklärung auch dann, wenn kein EU-Vertrieb geplant ist.
- [ ] Bei Trader-Status die von Apple geforderten Kontakt-/Nachweisdaten verifizieren und vor Veröffentlichung prüfen, welche Anschrift, Telefonnummer und E-Mail auf der EU-Produktseite öffentlich erscheinen.

Vor Review:

- [ ] Datenschutz-URL eingetragen.
- [ ] App-Privacy-Fragen anhand `STORE-METADATA.md` und des finalen Builds beantwortet.
- [ ] Neue Apple-Altersfreigabe-Fragen vollständig beantwortet.
- [ ] Kategorie, Beschreibung, Keywords, Support-URL und Copyright eingetragen.
- [ ] Echte Screenshots aus dem 1.0-Build mit ausschließlich Demo-Daten hochgeladen.
- [ ] Dedizierter Review-Server + wiederverwendbarer Testzugang hinterlegt; alternativ eingebauten Demo-Modus nur nach Apples Zustimmung als Ersatz verwenden.
- [ ] Export-Compliance-Angabe mit `ITSAppUsesNonExemptEncryption=false` abgeglichen.
- [ ] Upgrade von +11 auf +12 mit bestehendem Keychain-Token auf echtem iPhone geprüft.
- [ ] TestFlight-Build auf echtem iPhone und mindestens einem iPad-Layout geprüft.
- [ ] Build in App Store Connect ohne Upload-Warnungen/Fehler verarbeitet.

Apple verlangt seit 28. April 2026 Xcode 26 oder neuer mit iOS-26-SDK oder neuer. Der CI-Gate bildet diese Mindestanforderung ab.

## 7. Google Play Console – manuell

Vor dem ersten Upload:

- [ ] Passenden Kontotyp **Personal** oder **Organization** bewusst wählen; Organisationskonten benötigen unter anderem die hierfür geforderten Organisations-/D-U-N-S-Angaben.
- [ ] Entwicklerprofil, Identität und Kontaktangaben vollständig verifiziert; Angaben müssen mit Zahlungsprofil/Nachweisen übereinstimmen.
- [ ] Paketname `de.wachbuch.mobile` im verifizierten Entwicklerkonto registriert und App damit angelegt.
- [ ] Play App Signing aktiviert.
- [ ] GitHub Environment `google-play` mit Required Reviewer konfigurieren.
- [ ] Upload-Key-Secrets eintragen.
- [ ] Signiertes 1.0-AAB zunächst im internen Test-Track hochladen.

Vor Review/Produktion:

- [ ] App access: Demo-Anweisung und bei Bedarf dedizierte Review-Zugangsdaten eingetragen.
- [ ] Datenschutz-URL eingetragen.
- [ ] öffentliche Support-E-Mail/Support-Kontaktdaten in Play Console korrekt eingetragen.
- [ ] Data-Safety-Formular vollständig und konsistent mit der Datenschutzerklärung ausgefüllt.
- [ ] Content Rating / Zielgruppe ausgefüllt.
- [ ] Store Listing mit echten 1.0-Screenshots und finalen Texten ausgefüllt.
- [ ] Pre-Launch-Report geprüft; keine kritischen Crashes/ANRs/Policy-Probleme.
- [ ] Production-AAB targetet API **36+**. Der Release-Workflow bricht andernfalls ab.
- [ ] 9.x→10.3.1-Secure-Storage-Upgrade einschließlich Prozessabbruch/Recovery auf echtem Android-Gerät geprüft.
- [ ] Internen oder geschlossenen Test auf echten Android-Geräten abgeschlossen.

Ab 31. August 2026 müssen neue Apps und Updates für Mobilgeräte Android 16 / API 36 oder höher targeten. Zusätzlich gelten die aktuellen Android-/Play-Entwicklerverifikationsanforderungen; deshalb sind Paketregistrierung und verifiziertes Entwicklerprofil Teil der 1.0-Freigabe.

## 8. Datenschutz-/Berechtigungsabgleich 1.0

### Android Manifest

Erwartete produktive Berechtigungen:

- `INTERNET`
- `ACCESS_NETWORK_STATE` (über Plugin/Netzwerkstatus)
- `CAMERA`
- `ACCESS_COARSE_LOCATION`
- Android-interne dynamische Receiver-Berechtigung

Nicht zulässig ohne neuen Review:

- Hintergrundstandort
- Kontakte
- Mikrofon
- SMS/Anruflisten
- breite Datei-/Medienspeicherberechtigungen

### iOS Info.plist

Erwartete Usage Descriptions:

- Kamera: QR + ausdrücklich ausgewähltes Mängelfoto
- Fotomediathek: ausdrücklich ausgewähltes Mängelfoto
- Standort When In Use: lokale Sonnenaufgang/-untergang-Berechnung

`ITSAppUsesNonExemptEncryption=false` bleibt gesetzt, solange die App nur reguläre Betriebssystem-/HTTPS-Verschlüsselung im beschriebenen Umfang nutzt und keine eigene exportkontrollpflichtige Kryptofunktion hinzukommt.

## 9. Datenschutz-/Privacy-Manifest-Gate

Apple verlangt korrekte Privacy-Manifeste für verwendete Required-Reason-APIs und betroffene Drittanbieter-SDKs. Der Build validiert alle `PrivacyInfo.xcprivacy`, die im finalen App-Bundle enthalten sind. Bei jedem Plugin-Upgrade muss zusätzlich geprüft werden, ob Apple neue Required-Reason-/SDK-Anforderungen eingeführt hat.

Ein erfolgreicher lokaler/CI-Build ersetzt **nicht** die App-Store-Connect-Verarbeitung: Erst ein dort vollständig verarbeiteter Build ohne Privacy-/SDK-Warnung gilt als Store-Gate bestanden.

## 10. Review-Testfälle vor Veröffentlichung

Auf iOS und Android mindestens prüfen:

1. frische Installation → Server-Setup
2. Datenschutzlink vor Login öffnen
3. Demo-Modus ohne Server
4. HTTPS-Server manuell verbinden
5. QR-Verbindung, Kamera verweigert → manuelle Eingabe weiterhin möglich
6. Login/App-Token und MFA-Hinweis
7. Übergabe lesen/filtern/quittieren
8. Übergabe → Mangel
9. Mangel anlegen/Status/Foto
10. Geräte-/Fahrzeugstatus
11. Inventar Checkout/Checkin
12. Checkliste abschließen + Wiederholungsfälligkeit
13. Auswertung
14. Offline-Lesecache
15. Logout → Token/Cache entfernt
16. Serverwechsel → alter Token/Cache entfernt
17. Deep Link gleicher Server → bestehende Sitzung bleibt
18. Upgrade +11 → +12 mit bestehendem Token und Offline-Cache
19. Android: unterbrochene erste Secure-Storage-Migration → Recovery
20. große Schrift 200 %, Hoch-/Querformat, Tablet/iPad
21. Berechtigungen einzeln verweigern

## 11. Freigabekriterium

**1.0 darf erst öffentlich eingereicht werden**, wenn:

- GitHub-CI auf dem finalen Release-Head vollständig grün ist,
- der Secure-Storage-Migrationspfad 9.x → 10.3.1 auf echten Geräten bestanden ist,
- die signierten Store-Artefakte aus `main` erzeugt wurden,
- TestFlight beziehungsweise interner Play-Test auf echten Geräten bestanden ist,
- Datenschutz/Store-Metadaten dem tatsächlichen Build entsprechen,
- Apple-DSA-/Google-Entwicklerverifikation für die gewählte Vertriebsform erledigt ist,
- Review-Zugang funktioniert,
- keine echten Patienten-/Einsatz-/Organisationsdaten in Screenshots oder Reviewer-Demo enthalten sind.
