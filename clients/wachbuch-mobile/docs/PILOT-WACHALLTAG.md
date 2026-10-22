# Pilot Wachalltag 0.6.x

## Ziel

Den realen Wachalltag-Vertrag für 2–4 Wochen in einer Partnerwache nutzen und dabei Schichtübergabe, Mängel, Gerätestatus, Schlüssel/Pools, Quittierungen, Checklisten, Fotos und Auswertung unter echten Betriebsbedingungen prüfen – ohne ELS/Alarmierung, ePCR oder Patientendaten.

## Technische Mindestbasis

- Server `0.16.x` auf isolierter Test-/Pilotinstanz
- Client `0.6.x` aus einem CI-grünen Commit
- HTTPS, Backup und dokumentierter Restore-Test
- App-Token statt dauerhaftem Passwort im Client
- MFA für Konten entsprechend Serverrichtlinie
- getrennte Rollen für Mitglied, Schichtleitung und Admin
- keine echten Patienten-/Einsatzdaten in Pilot-Fixtures oder Screenshots

## Ablauf

1. **Vorab-Abnahme:** `E2E-WACHALLTAG.md` vollständig gegen die Pilotinstanz durchspielen.
2. **Kickoff:** Produktgrenze, Rollen, Foto-Regeln und Meldeweg erklären.
3. **Woche 1:** Übergaben, Mängel, Quittierungen und Gerätestatus im Schichtalltag einsetzen.
4. **Woche 2:** Schlüssel/Pools, wiederkehrende Checks, Fotos und Auswertung dazunehmen.
5. **Fehlerreview:** Blocker, Dateninkonsistenzen, Offline-Verhalten und Rechtefehler priorisieren.
6. **Abschluss:** Rollout-/Store-Entscheidung treffen; offene Punkte als GitHub-Issues dokumentieren.

## Pilot-Sicherheitsregeln

- Mängelfotos zeigen ausschließlich Zustand von Gerät/Fahrzeug/Wache.
- Keine Patienten, Einsatzprotokolle, Monitorbilder mit Patientendaten oder Kennzeichen fremder Betroffener erfassen.
- Reports dienen der Stationsorganisation und nicht der individuellen Leistungsüberwachung.
- Korrekte Stationsisolation mit mindestens zwei Testwachen verifizieren.
- Nach Logout/Serverwechsel prüfen, dass keine Offline-Daten einer anderen Sitzung angezeigt werden.
- Korrelation-ID bei Serverfehlern im Supportfall sichern, nicht sensible Nutzdaten in Freitextlogs kopieren.

## Erfolgskriterien

- mindestens eine vollständige Schichtwoche ohne Datenverlust
- kein Blocker ohne dokumentierten Workaround
- keine stationsübergreifende Datenanzeige
- keine doppelten Mängel/Fotos durch automatische Request-Wiederholung
- Backup/Restore erfolgreich getestet
- Android- und iOS-Pilotbuilds reproduzierbar
- E2E-Pflichtpfad vollständig bestanden

## Nicht Teil des Piloten

Alarmierung, Einsatzleitsystem, Patientendokumentation/ePCR, Abrechnung, Personalakte, vollständige Dienstplanung und individuelle Leistungskennzahlen.
