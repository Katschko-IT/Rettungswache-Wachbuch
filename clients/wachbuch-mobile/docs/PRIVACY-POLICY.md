# Datenschutzerklärung / Privacy Policy – Wachbuch

**Stand / Last updated:** 10. August 2026  
**App:** Wachbuch für iOS und Android  
**Quellcode:** https://github.com/Katschko-IT/Wachbuch-Client

Wachbuch ist ein Open-Source-Client für selbst gehostete Wachbuch-Server. Die App ist weder eine offizielle Behörden-App noch ein Patienten-, Einsatzleit-, Alarmierungs- oder ePCR-System.

## 1. Verantwortungsmodell

Die mobile App stellt **keinen zentralen Wachbuch-Cloud-Dienst** bereit. Nutzer verbinden die App mit einem von ihnen beziehungsweise ihrer Organisation betriebenen Wachbuch-Server. Der Betreiber dieses Servers ist für die dort gespeicherten Organisations- und Benutzerdaten, Aufbewahrungsfristen, Zugriffsrechte sowie Betroffenenrechte verantwortlich.

Der App-Entwickler erhält durch die normale Nutzung der App keinen automatischen Zugriff auf die Inhalte eines fremden selbst gehosteten Servers.

## 2. Welche Daten die App lokal verarbeitet

Die App kann lokal verarbeiten oder speichern:

- die Adresse des ausgewählten Wachbuch-Servers,
- einen vom Server ausgestellten App-Token,
- einen server- und tokengebundenen verschlüsselten Offline-Lesecache,
- lokale App-Einstellungen,
- optional einen ungefähren Gerätestandort ausschließlich zur lokalen Berechnung von Sonnenaufgang und Sonnenuntergang für das Tag-/Nacht-Design.

App-Tokens und der Offline-Cache werden über die sicheren Speichermechanismen des Betriebssystems geschützt. Android-Backups und Geräteübertragungen der App-Daten sind im Produktionsmanifest deaktiviert.

## 3. Datenübertragung an den selbst gehosteten Server

Für die App-Funktion werden Daten über HTTPS an den vom Nutzer eingerichteten Wachbuch-Server übertragen. Dazu können insbesondere gehören:

- Benutzername und Passwort beim Token-Austausch; das Passwort wird von der App nicht dauerhaft gespeichert,
- App-Token bei authentifizierten API-Anfragen,
- Übergaben, Checklisten, Mängel, Geräte-/Fahrzeugstatus, Inventar-/Poolvorgänge und zugehörige Organisationsdaten,
- ausdrücklich vom Nutzer ausgewählte oder aufgenommene Mängelfotos.

Welche Daten der Server anschließend speichert, wie lange sie gespeichert werden und wer darauf zugreifen darf, legt der jeweilige Serverbetreiber fest.

## 4. Kamera und Fotos

Die Kamera wird für zwei getrennte Funktionen verwendet:

1. **QR-Servereinrichtung:** Kamerabilder werden zur QR-Erkennung verarbeitet und von der App nicht als Foto gespeichert oder an den Entwickler übertragen.
2. **Mängeldokumentation:** Nur wenn der Nutzer ausdrücklich ein Foto aufnimmt oder aus der Fotomediathek auswählt, wird dieses Bild an den eingerichteten Wachbuch-Server übertragen.

Die App weist darauf hin, keine Patienten-, Einsatz- oder vergleichbaren sensiblen Fachdaten zu fotografieren.

## 5. Standort

Wenn die Standortberechtigung erteilt wird, verwendet Wachbuch nur einen ungefähren Standort, um Sonnenaufgang und Sonnenuntergang für das lokale Erscheinungsbild zu berechnen. Dieser Standort wird nach aktuellem App-Konzept **nicht an den Wachbuch-Server, den App-Entwickler oder Werbedienste übertragen**. Wird die Berechtigung verweigert, verwendet die App das Systemdesign als Fallback.

### Benachrichtigungen

Mit erteilter Benachrichtigungsberechtigung erinnert die App die Besatzung, wenn die Einwirkzeit einer Fahrzeugdesinfektion abläuft. Die Erinnerung wird **lokal auf dem Gerät** geplant; Grundlage sind nur Funkrufname, Sperrzeit und ein kurzer Hinweistext vom eigenen Wachbuch-Server. Es werden keine Daten an den App-Entwickler oder an Werbedienste übertragen. Ohne Berechtigung erscheint der Hinweis nur in der App bzw. im Web.

## 6. Werbung, Tracking und Analyse

Wachbuch enthält nach aktuellem Stand:

- keine Werbung,
- kein Werbe-SDK,
- kein Nutzer-Tracking,
- kein Profiling für Werbung,
- kein externes Analytics-/Crash-Tracking-SDK.

Die App kann technische Fehler des verbundenen Servers anzeigen, sendet aber nicht automatisch Telemetrie an den App-Entwickler.

## 7. Konten und Löschung

Die mobile App erstellt selbst keine zentralen Entwicklerkonten. Benutzerkonten werden auf dem jeweils eingerichteten Wachbuch-Server verwaltet. Anfragen auf Auskunft, Berichtigung oder Löschung serverseitiger Daten sind daher an den Betreiber des betreffenden Servers zu richten.

Beim Abmelden oder Wechsel des Servers entfernt die App das lokale App-Token sowie den zugehörigen Offline-Cache. Eine Deinstallation entfernt die App-Daten entsprechend den Mechanismen des Betriebssystems.

## 8. Transport- und Zugriffsschutz

Produktive Serververbindungen müssen HTTPS verwenden. Die App trennt Offline-Caches nach Server und Token und verwendet die sicheren Schlüssel-/Credential-Speicher von iOS und Android. Betreiber eines Wachbuch-Servers sind zusätzlich für TLS, Benutzerverwaltung, Backups, Updates und ihre eigene Datenschutzkonfiguration verantwortlich.

## 9. Drittanbieter-Komponenten

Die App basiert auf Flutter und nutzt Open-Source-Pakete für unter anderem HTTPS-Kommunikation, Secure Storage, QR-Erkennung, Kamera-/Fotoauswahl, Konnektivitätsstatus, lokale Benachrichtigungen und optionalen Standortzugriff. Die App integriert keine Werbe- oder Marketing-SDKs. Änderungen an Abhängigkeiten werden im Repository und in der automatisierten Dependency-Security-Prüfung nachvollzogen.

## 10. Kinder und öffentliche soziale Funktionen

Wachbuch richtet sich an Organisationen und deren autorisierte Nutzer und nicht speziell an Kinder. Es gibt keine öffentliche Social-Networking-, Chat-, Dating- oder frei zugängliche User-Generated-Content-Plattform. Inhalte eines Wachbuch-Servers sind organisationsbezogen und zugriffsgeschützt.

## 11. Änderungen

Wenn sich Datenverarbeitung, Berechtigungen oder integrierte Dienste wesentlich ändern, muss diese Erklärung zusammen mit den App-Store-/Play-Store-Datenschutzangaben aktualisiert werden.

## 12. Kontakt

Fragen zur mobilen Open-Source-App und zu dieser Erklärung können über das öffentliche Repository gestellt werden:

https://github.com/Katschko-IT/Wachbuch-Client/issues

Fragen zu Daten auf einem konkreten Wachbuch-Server sind an den Betreiber dieses Servers zu richten.

---

# English summary

Wachbuch is an open-source client for self-hosted Wachbuch servers. It does not provide a central developer-operated cloud service and is not an official government, patient-record, dispatch, alarm or ePCR application.

The app stores the selected server address locally and protects app tokens and token/server-scoped offline snapshots using operating-system secure storage. It sends authentication and operational station data only to the server explicitly configured by the user. A password used for token exchange is not persistently stored by the app.

Camera frames used for QR setup are processed for scanning and are not uploaded as photos. A defect photo is transmitted only when the user explicitly captures or selects one. Approximate location, when permitted, is used locally for sunrise/sunset theme calculation and is not transmitted under the current app design.

The app contains no advertising, advertising SDK, cross-app tracking or external analytics/crash-tracking SDK. Account and server-side data deletion are controlled by the operator of the selected self-hosted server. Signing out or changing servers removes the associated local token and offline cache.

Questions about the mobile app or this policy can be filed at:
https://github.com/Katschko-IT/Wachbuch-Client/issues
