# Secure-Storage-Migration – Store Build 1.0.0+12

Stand: 10. August 2026

## Ziel

Wachbuch migriert `flutter_secure_storage` kontrolliert von 9.2.4 auf **10.3.1**, bevor ein späterer Wechsel auf 11.x erfolgt. Der Schritt betrifft App-Token, Token-Ablaufzeit und den server-/tokengebundenen Offline-Lesecache.

## Warum nicht direkt 11.x?

`flutter_secure_storage` 10.x führt die neue Android-Kryptobasis und Migrationswerkzeuge ein. Die 11er-Linie entfernt alte/deprecated Pfade; deshalb muss eine vorhandene 9.x-Installation zuerst über einen getesteten 10.x-Build migriert werden.

Für Build 1.0.0+12 gilt zentral:

```dart
AndroidOptions(
  migrateOnAlgorithmChange: true,
  migrateWithBackup: true,
)
```

Damit wird die Algorithmusmigration ausdrücklich aktiviert und mit crash-resistenten Backup-Markern abgesichert.

## Android-Zielzustand

Mit `flutter_secure_storage` 10.3.1 verwendet die Standardkonfiguration:

- RSA-OAEP mit SHA-256 für Key-Wrapping,
- AES-GCM für Storage-Verschlüsselung,
- Android Keystore für Schlüsselmaterial,
- `migrateOnAlgorithmChange=true`,
- `migrateWithBackup=true` in Wachbuch.

Wachbuch hat Android-App-Backups im Produktionsmanifest deaktiviert. Diese Einstellung bleibt verpflichtend.

In 10.x gilt zusätzlich der Android-Default `resetOnError=true`: Tritt ein Entschlüsselungsfehler auf, den auch die Migration nicht auflösen kann, wird der Secure Storage zurückgesetzt, damit die App nicht mit inkonsistentem Kryptomaterial weiterläuft. Das betroffene Gerät verliert dann seine Sitzung und der Nutzer muss sich neu anmelden. `migrateWithBackup` sichert genau diesen Migrationspfad mit Backup-Markern ab; ein Reset ist daher durch das Upgrade selbst nicht zu erwarten und wird in der Testmatrix über Schritt 11 abgedeckt.

## iOS/iPadOS

Die bisherige Keychain-Konfiguration wird in diesem Migrationsschritt bewusst nicht auf Secure Enclave oder neue Accessibility-Attribute umgestellt. Dadurch werden Kryptobibliotheks-Upgrade und Keychain-Policy nicht gleichzeitig verändert. Ein späterer Secure-Enclave-Schritt benötigt eine eigene Migration und reale Geräteabnahme.

## Pflicht-Testmatrix vor Store-Rollout

### Android Upgrade

1. 1.0.0+11/9.x installieren.
2. Produktivähnlichen Testserver verbinden.
3. App-Token speichern und mehrere Offline-Reads erzeugen.
4. App beenden; **nicht** abmelden.
5. 1.0.0+12 darüber installieren.
6. Prüfen: bestehende Sitzung bleibt nutzbar.
7. Netzwerk deaktivieren; Offline-Lesecache prüfen.
8. Netzwerk aktivieren; API-Aufruf prüfen.
9. Logout prüfen: Token + Cache entfernt.
10. Serverwechsel prüfen: alter Cache nicht mehr verfügbar.
11. App/Prozess während des ersten Storage-Zugriffs gezielt beenden; danach Neustart und Recovery prüfen.

### iOS Upgrade

1. Vorversion installieren und anmelden.
2. Token/Offline-Cache erzeugen.
3. 1.0.0+12 als Upgrade installieren.
4. Sitzung und Offline-Cache prüfen.
5. Logout/Serverwechsel prüfen.
6. Gerätesperre/Neustart und erneuten Zugriff prüfen.

## Rollout

Empfohlene Reihenfolge:

1. CI/OSV vollständig grün.
2. internes Android-Gerät Upgrade-Test.
3. TestFlight Upgrade-Test auf echtem iPhone.
4. kleiner geschlossener Pilot.
5. erst danach breiter Store-Rollout.

## Rollback

Nach erfolgreicher Migration darf nicht ungeprüft auf einen 9.x-Build zurückgegangen werden. Ein Rollback muss auf Testgeräten mit bereits migriertem Storage verifiziert werden. Bei einem App-Fehler ist ein 10.3.1-basierter Hotfix einem Downgrade auf 9.x vorzuziehen.

## v11-Freigabe

Ein Wechsel auf `flutter_secure_storage` 11.x ist ein eigener Change und darf erst erfolgen, wenn:

- der 10.3.1-Migrationsbuild auf realen Geräten erfolgreich war,
- vorhandene Tokens/Caches nach Upgrade erhalten bleiben,
- Logout/Serverwechsel weiterhin vollständig bereinigen,
- OS-/SDK-Anforderungen geprüft sind,
- Dependency Security/OSV grün ist,
- Store-Builds erneut vollständig validiert sind.
