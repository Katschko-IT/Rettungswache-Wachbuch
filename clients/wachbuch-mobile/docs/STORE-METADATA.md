# Store-Metadaten – Wachbuch 1.0

Stand: 10. August 2026

Diese Datei ist die redaktionelle Quelle für App Store Connect und Google Play Console. Vor Einreichung immer mit dem tatsächlich hochgeladenen Build und der Datenschutzerklärung abgleichen.

## Positionierung

**Name:** Wachbuch  
**Kategorie:** Produktivität / Business  
**Nicht positionieren als:** offizielle Behörden-App, Medizinprodukt, Notruf-, Alarmierungs-, Einsatzleit-, Patientenakten- oder ePCR-App.

Wachbuch ist ein generischer Open-Source-Client für selbst gehostete Organisationsserver. Feuerwehr, Rettungsdienst oder Polizei dürfen in Screenshots/Demo-Beispielen als mögliche Einsatzumgebungen erscheinen, jedoch ohne den Eindruck einer offiziellen staatlichen Herausgeberschaft.

## Apple App Store – Deutsch

### Name

`Wachbuch`

### Untertitel

`Wachalltag. Selbst gehostet.`

### Beschreibung

Wachbuch verbindet iPhone und iPad mit einem selbst gehosteten Wachbuch-Server.

Organisieren Sie den Stations- und Wachalltag mit Übergaben, Checklisten, Mängeln, Geräte- und Fahrzeugstatus, Pool-/Inventarvorgängen und einer kompakten Auswertung. Die App unterstützt außerdem Mängelfotos, QR-basierte Servereinrichtung und einen verschlüsselten Offline-Lesecache.

Ihre Organisation behält die Kontrolle über den Server und die dort gespeicherten Daten. Die App enthält keine Werbung und kein Werbe- oder Tracking-SDK.

Funktionen:
- Übergaben lesen, filtern und quittieren
- Mängel erfassen, priorisieren, terminieren und dokumentieren
- optionale Mängelfotos aus Kamera oder Fotomediathek
- Fahrzeug- und Gerätestatus
- Schlüssel- und Pool-Inventar mit Ausgabe/Rückgabe
- wiederkehrende Checklisten
- organisatorische Auswertung ohne individuelle Leistungsbewertung
- sichere App-Tokens und servergebundener Offline-Lesecache
- Deutsch und Englisch
- Demo-Modus ohne eigenen Server

Wachbuch ist Open Source (AGPL-3.0-or-later). Es ist keine offizielle Behörden-App und kein Notruf-, Alarmierungs-, Einsatzleit-, Patientenakten- oder ePCR-System.

### Keywords

`wachbuch,übergabe,checkliste,inventar,mängel,selfhosted,opensource,wache`

### Marketing-URL

Bevorzugt eine eigene öffentliche Wachbuch-Seite. Bis dahin kann das öffentliche Repository verwendet werden:
`https://github.com/Katschko-IT/Wachbuch-Client`

### Support-URL

`https://github.com/Katschko-IT/Wachbuch-Client/blob/main/docs/SUPPORT.md`

### Datenschutz-URL

`https://github.com/Katschko-IT/Wachbuch-Client/blob/main/docs/PRIVACY-POLICY.md`

## Apple App Store – English

### Name

`Wachbuch`

### Subtitle

`Self-hosted station operations`

### Description

Wachbuch connects iPhone and iPad to a self-hosted Wachbuch server.

Manage day-to-day station operations with handovers, checklists, defects, vehicle and equipment status, pooled inventory and lightweight operational reports. The app also supports defect photos, QR-based server setup and an encrypted offline read cache.

Your organisation controls its server and the data stored there. The app contains no advertising, advertising SDK or cross-app tracking.

Wachbuch is open source under AGPL-3.0-or-later. It is not an official government app and is not an emergency-calling, dispatch, alarm, patient-record or ePCR system.

### Keywords

`handover,checklist,inventory,defects,selfhosted,opensource,station`

## Google Play – Deutsch

### App-Name

`Wachbuch`

### Kurzbeschreibung

`Übergaben, Checklisten und Material für selbst gehostete Wachbuch-Server.`

### Vollständige Beschreibung

Wachbuch ist der mobile Open-Source-Client für selbst gehostete Wachbuch-Server.

Die App unterstützt den organisatorischen Stations- und Wachalltag: Übergaben, wiederkehrende Checklisten, Mängel, Fahrzeug-/Gerätestatus, Pool-Inventar und Auswertungen. Mängel können optional mit ausdrücklich ausgewählten Fotos dokumentiert werden. Ein QR-Code erleichtert die Servereinrichtung.

Produktive Verbindungen verwenden HTTPS. App-Tokens werden über den sicheren Speicher des Betriebssystems geschützt; Offline-Snapshots sind an Server und Token gebunden. Es gibt keine Werbung und kein Werbe- oder Tracking-SDK.

Wachbuch ist kein offizielles Behördenprodukt und kein Notruf-, Alarmierungs-, Einsatzleit-, Patientenakten- oder ePCR-System. Patienten- und Einsatzdaten gehören nicht in Wachbuch.

Quelloffen unter AGPL-3.0-or-later.

## Review-Zugang

### Google Play

Der eingebaute **Demo-Modus** ist ohne Login vom ersten Bildschirm aus erreichbar und deckt die produktiven Kernabläufe mit lokalen Musterdaten ab. In der Play Console unter **App access** folgende Review-Anweisung hinterlegen:

> Start the app and tap “Try demo mode”. Choose “Emergency medical services” (or another demo profile). The demo runs fully offline and exposes handovers, defects, assets/inventory, checklists and reports without credentials. For server-login review, use the dedicated review server credentials supplied separately in Play Console. No production-user credentials are required.

Wenn Google servergebundene Funktionen überprüfen soll, zusätzlich einen dauerhaft erreichbaren dedizierten Review-Server und wiederverwendbare Testzugangsdaten bereitstellen.

### Apple App Review

Apple verlangt für Login-Apps grundsätzlich einen funktionsfähigen Demo-Account. Ein eingebauter Demo-Modus kann nur als Ersatz verwendet werden, wenn Apple dies akzeptiert. Bevorzugte Review-Konfiguration:

- dedizierter HTTPS-Review-Server,
- dauerhaft gültiger Testbenutzer beziehungsweise App-Token,
- keine MFA-Abhängigkeit mit Einmalcode,
- keine realen Organisations- oder Personendaten,
- Review Notes mit Serveradresse und klaren Navigationsschritten.

Review-Notes-Vorlage:

> Wachbuch is a client for user-selected self-hosted servers. It is not an official government or medical application. A built-in offline demo is available from the first screen via “Try demo mode”. A dedicated review server and reusable credentials are provided in the Sign-In Information fields so App Review can also verify the real network flow. No patient or incident data is part of the product model.

## Datenschutzangaben – konservativer Entwurf

Die endgültigen Formulare in App Store Connect und Play Console müssen den jeweiligen Definitionen der Plattform folgen. Für 1.0 gilt nach aktuellem Code:

- **Kein Tracking / keine Werbung.**
- **Keine externen Analytics-/Crash-SDKs.**
- Benutzer verbindet die App mit einem selbst gewählten Server.
- Zugangsdaten werden für die Anmeldung an diesen Server übertragen; das Passwort wird von der App nicht dauerhaft gespeichert.
- App-Token wird lokal im sicheren Betriebssystemspeicher gespeichert.
- Übergaben, Mängel, Checklisten, Inventar-/Gerätestatus und ausdrücklich ausgewählte Mängelfotos werden für die App-Funktion an den ausgewählten Server übertragen.
- QR-Kameraframes werden lokal verarbeitet und nicht als Foto hochgeladen.
- Ungefährer Standort wird nur lokal für Sonnenaufgang/-untergang verwendet und nicht übertragen.

Für Google Play ist eine eher konservative Deklaration sinnvoll: serverseitig gespeicherte Benutzerkennungen und nutzergenerierte Organisationsinhalte als für **App functionality** verarbeitet angeben; keine Weitergabe zu Werbung/Tracking behaupten. Die Rolle des selbst gehosteten Serverbetreibers in der Datenschutzerklärung erläutern.

## Altersfreigabe / Zielgruppe

- Zielgruppe: berufliche/organisatorische Nutzer, nicht speziell Kinder.
- Keine Glücksspiel-, Dating-, sexualisierten oder öffentlichen Social-Networking-Funktionen.
- Organisationsinterne nutzergenerierte Texte/Fotos können vorkommen; dies bei den jeweils aktuellen Altersfreigabe-Fragen wahrheitsgemäß angeben.
- Kein frei öffentlicher UGC-Feed.

## Screenshots – benötigter Satz

Keine generierten/fiktiven Store-Screenshots verwenden, die Funktionen zeigen, die der Build nicht besitzt. Screenshots aus einem echten 1.0-Build mit Demo-Daten aufnehmen.

Empfohlene Motive:
1. Übersicht / Schnellzugriff
2. Übergaben mit Status/Priorität
3. Mängel inkl. Foto-Funktion
4. Geräte-/Fahrzeugstatus und Pool-Inventar
5. Checklisten / Fälligkeit
6. Auswertung
7. Servereinrichtung + QR/Demo als optionales letztes Motiv

In Screenshots ausschließlich Demo-Daten verwenden; keine echten Namen, Serveradressen, Tokens oder Einsatz-/Patientendaten.
