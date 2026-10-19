# Release 0.18.0 – Pilotstand mit Hilfe, Wiki und Diagnose

Stand: 19. Oktober 2026. Zweck: lokaler Pilotbetrieb und Praxistest.
Keine Produktionsfreigabe, keine Zertifizierung, keine Compliance-Bestätigung.

## Neu gegenüber 0.17.0

- **Hilfe & System:** lokale, offline mitgelieferte Produkthilfe mit Suche in
  Deutsch und Englisch sowie eine rollenbeschränkte Systemseite mit Version,
  Datenbankstatus und Cache-Hinweisen.
- **Wachen-Wiki:** wachengebundene Hinweise mit unveränderlichen Revisionen,
  Konfliktschutz beim gleichzeitigen Bearbeiten und rollenbasierter Bearbeitung.
- **Diagnose und Supportexport:** bereinigte Fehlerereignisse mit
  Korrelations-ID, stabilem Routennamen, Kategorie und Status – ohne
  URLs, Abfrageparameter, Exception-Texte, Header oder Zugangsdaten.
  Export ausschließlich für Administratoren, mit fester Feldauswahl.
- **Zweisprachigkeit ausgebaut:** Templates, Fachmodule, JavaScript- und
  sichtbare Python-Texte über deutsch/englische Kataloge; Umschaltung ohne
  Änderung der Adressen.
- **Englische Projektseite** neben der deutschen Fassung, beide ohne
  JavaScript, ohne externe Dienste.

## Sicherheitsrelevante Nacharbeiten

- Serverfehler beim gleichzeitigen Anlegen gleichnamiger Wiki-Hinweise werden
  kontrolliert als Konflikt beantwortet; keine Teil-Schreibvorgänge.
- Archivieren und Wiederherstellen verlangen eine gültige Revisionsangabe.
- Diagnose-Übersicht und Supportexport verwenden dieselbe Aufbewahrungsgrenze.
- Sprachdaten für das JavaScript werden über Djangos sichere JSON-Ausgabe
  erzeugt statt über handgebautes JSON.

## Ausdrücklich nicht enthalten

- Schreibfähiger Offlinebetrieb ohne Serververbindung (Outbox/Synchronisierung).
- Vollständige Übersetzung von Datenbank-Altbeständen und Modell-Labels.
- Reale Geräte-, TLS-, Passkey- und WebPush-Abnahme in einer Wache.
- Produktiver Postgres-/Backup-Betriebsnachweis für dieses Release.

## Veröffentlichung

Vor Veröffentlichung müssen vollständige Tests, Katalog-, Migrations- und
Ruff-Prüfung, Webseitenprüfung sowie ein unabhängiges Review auf demselben
eingefrorenen Stand grün sein. Anschließend werden Commit, Push, CI und
Pages-Deployment geprüft.

Diese Veröffentlichung ist kein Produktionsdeployment eines Wachenbetriebs.
