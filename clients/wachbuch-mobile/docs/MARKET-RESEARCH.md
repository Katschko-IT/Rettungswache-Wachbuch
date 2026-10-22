# Markt- und UX-Recherche

Stand: 2. August 2026

## Ziel

Den selbstgehosteten Wachbuch-Client mit bestehenden digitalen Wachbüchern, Feuerwehr-/Rettungsdienstlösungen und Schichtübergabe-Apps vergleichen. Herstellerangaben wurden als Marktpositionierung ausgewertet; daraus abgeleitete Produktentscheidungen sind separat gekennzeichnet.

## Betrachtete Produkte

- [RDSuite Wachbuch](https://www.rdsuite.de/wachbuch/) – Aufgaben/Infoboard, Checklisten, Fahrzeugchecks, Anhänge und Auswertungen.
- [FWportal](https://www.fwportal.de/) – Feuerwehrverwaltung mit mobiler App, Alarmrückmeldungen und teilweise offline verfügbaren Inhalten.
- [MissionBuddies Einsatztagebuch](https://www.missionbuddies.de/einsatztagebuch/) – geräteübergreifendes Einsatztagebuch, Filter, Lagekarte, Timer und Spracheingabe.
- [Testify Schichtübergabe](https://www.testify.io/anwendungsfaelle/schichtuebergabe-protokoll/) – geführte Checklisten, Mangelmanagement, Signaturen und Benachrichtigungen.
- [Finito Digital Shift Book](https://www.schichtbuch.com/finito/) – Textbausteine, Aufgaben, Signaturen und Recherchefunktion.
- [Wachplan.info](https://wachplan.info/) – Wachdienst-, Anwesenheits- und Leistungserfassung.
- [EVALARM Digitales Wachbuch](https://www.evalarm.de/digitales-wachbuch) – Einträge, Anhänge, Suche, Filter und Audit-/Report-Funktionen.

## Offizielle Designquellen

- [Material Design 3: Search](https://m3.material.io/components/search/overview)
- [Material Design 3: Navigation rail](https://m3.material.io/components/navigation-rail)
- [Material Design 3: Components](https://m3.material.io/components)
- [Material Design 3: Accessibility](https://m3.material.io/foundations/designing/overview)

## Beobachtete Marktmuster

1. Historische Einträge werden über Suche und Filter auffindbar gemacht.
2. Status und Priorität sind visuell erfassbar, nicht nur als Fließtext dargestellt.
3. Ein Listeneintrag führt zu einer Detailansicht mit vollständigem Inhalt.
4. Aufgaben, Checklisten, Anhänge und Benachrichtigungen steigern den operativen Nutzen, benötigen aber abgestimmte Serverfunktionen.
5. Offline-Zugriff ist wertvoll, erfordert jedoch definierte Regeln für Aktualität, Serverwechsel, Logout und sensible lokale Daten.

## Entscheidung für 0.4.0

Rein clientseitig und ohne neuen Serververtrag umgesetzt:

- Volltextsuche über vorhandene Übergabefelder
- kombinierbare Status- und Prioritätsfilter
- lokalisierte, farbige Status-/Prioritätsdarstellung
- Ergebniszählung und klare Leerzustände
- Detailansicht über den bereits vorhandenen Endpoint `GET /api/v1/handovers/{id}/`
- kompakte Dashboard-Kennzahlen

## Bewusst verschoben

### Offline-Lesecache

Eigener Release mit verschlüsselter bzw. datensparsamer Persistenz, Zeitstempel „zuletzt aktualisiert“, Invalidierung bei Serverwechsel/Logout und Tests für veraltete Daten.

### Aufgaben und Checklisten

Erfordern API-, Rollen-, Status- und Audit-Entscheidungen im Server. Nicht als rein lokale Parallelwelt implementieren.

### Anhänge und Fotos

Erfordern Uploadvertrag, Größen-/Dateitypgrenzen, Berechtigungen, Datenschutz und serverseitige Bereinigung.

### Push-Benachrichtigungen

Erfordern Geräte-Registrierung, Zustellinfrastruktur, Abonnementlogik und Regeln gegen die Offenlegung sensibler Inhalte auf Sperrbildschirmen.

## Positionierung

Der wichtigste Unterschied zu vielen betrachteten Cloud-Angeboten ist der selbstgehostete Betrieb. Der Client sollte deshalb Datenhoheit, nachvollziehbare API-Verträge, minimale Berechtigungen und einen klaren Offline-/Cache-Umgang höher priorisieren als möglichst viele unverbundene Funktionen.
