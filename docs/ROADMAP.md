# Roadmap

Stand: 30. Oktober 2026 · aktuelle Version 0.26.0. Diese Datei ersetzt den Stand vom 3. August 2026. Sie führt `PRODUKT-FAHRPLAN.md`, `FUNKTIONSMATRIX-20261019.md`, `WAVE-3-READINESS.md` und `ROADMAP-OFFENE-BAUSTELLEN.md` zusammen; diese werden archiviert. Sicherheits- und Betriebsmaßnahmen stehen weiter in `REMEDIATION-ROADMAP-2026-08.md`; ihr Status ändert sich nur mit Beleg (AGENTS.md §§ 2, 5, 7). Der Wettbewerbsvergleich steht in [`KONKURRENZANALYSE.md`](KONKURRENZANALYSE.md); Funktionsvorschläge mit Bewertung: [`FUNKTIONSVORSCHLAEGE.md`](FUNKTIONSVORSCHLAEGE.md); UX-Plan: [`UX-PLAN.md`](UX-PLAN.md).

## Vision

Wachwerk ist die quelloffene, selbst betriebene Wachenorganisation für Rettungswachen. Es arbeitet auch ohne Internet und hilft bei MPG-, Hygiene- und Arbeitsschutznachweisen. Es speichert keine Patienten-, Einsatz-, Alarmierungs-, Gesundheits- oder Leistungsdaten.

## Grundsätze

1. **Produktgrenze vor Funktionsumfang** (AGENTS.md § 1). Jeder PR enthält eine Grenzprüfung, auch für Messziele und Auswertungen.
2. **Pilot vor Breite.** Was der Pilot braucht, kommt vor neuen Modulen. Während der 12 Pilotwochen gilt ein Feature-Freeze: nur Fehlerbehebung und Wünsche aus dem Pilot.
3. **Nachweise, die eine Begehung bestehen:** append-only, mit Person, Zeit und Ergebnis. Nachweise werden nie per CASCADE gelöscht. Objekte werden außer Betrieb genommen statt gelöscht.
4. **Inselbetrieb:** Die Kernabläufe funktionieren ohne Internet. Externe Dienste (Signal, E-Mail, Push-Relay, Healthcheck-Ping, Updates) sind abschaltbar und stehen in VVT und DSFA.
5. **Kein fünftes Prüfkonzept:** Tagesaufgaben, Checklisten, Fahrzeugübernahme und Funktionskontrolle laufen schrittweise in einem Prüflauf zusammen. Läufe mit Nachweischarakter laufen nie über das Terminal-Dienstkonto.
6. **Messen ohne Leistungsdaten:** keine Dauer je Person, keine Aktivitätsquote je Person. Bedienziele werden nur in moderierten Tests oder per anonymer Umfrage gemessen.
7. **Keine neue Upload-Art und keine schwere Abhängigkeit ohne ADR.** Druckansicht (`@media print`) statt PDF-Bibliothek, CSV statt XLSX.
8. **Kleine, abnehmbare Schnitte:** ein menschlicher Maintainer mit KI-Unterstützung. Geplant werden etwa 3–4 abnahmefähige Personenwochen (PW) je Monat, mit 25 % Puffer für Pilotbetreuung und Sicherheitsupdates. Den Takt bestimmen Abnahme und externe Freigaben, nicht die Programmierzeit.
9. **Wachwerk liefert keine medizinischen oder fachlichen Mustertexte** und keine fertigen Rechtstexte. Vorlagen werden per Import und Export zwischen Wachen geteilt.

## Erreicht bis 0.26.0

- **Wachalltag:** Übergaben mit Revisionen und Quittierung, Tagesaufgaben und Wochenbogen, Checklisten, Mängel mit Foto und Frist, Ausstattung und Pool, Kalender mit Feiertagen und Müll-ICS, Pinnwand, Neuigkeiten mit Lesebestätigung, Wiki, Kaffeekasse mit GiroCode, Geburtstage.
- **Fachmodule:** Fuhrpark (Übernahme, Desinfektion, Einwirkzeit-Sperre, Fristen); Medizinprodukte nach MPBetreibV 2025 (Bestandsverzeichnis, MP-Buch-Grundstock, STK/MTK, Funktionskontrolle mit Sperre, Einweisungen, QR); Lager (Chargen, FEFO, Kühlware, Rückrufsperre); Dienstanweisungen mit Version, SHA-256 und Lesequittung.
- **An der Wache:** Wachen-Display, Touch-Terminal mit Sperrbildschirm und Wachen-Code.
- **Sicherheit:** TOTP, Passkeys, QR-Login, MFA-Pflicht, append-only Audit, CSP ohne `unsafe-inline`, Rate-Limit (R-011), Log-Redaktion.
- **Betrieb:** `install.sh` (local/lan/domain), Auto-Update mit Rollback, tägliche Dumps mit Restore-Probe, Housekeeping, Hetzner-Härtung mit `wachwerk-health` und GPG-Offsite (nur Hetzner-Weg), Images für amd64/arm64, öffentliche Demo.
- **App** (Flutter, 1.0.0+12): Wachalltag-Kern, E2EE-Chat, verschlüsselter Lesecache, Kopplung am Terminal.
- **Weiter offen** (anders als bisher teils angegeben): R-010 Backup-Rolle [~], R-016 Monitoring [ ], R-017 Offsite und Restore-Nachweis [ ] (für Pi/LAN fehlt Offsite ganz), R-015 Pentest [ ], R-018 Barrierefreiheit [ ], R-019 Last [ ].

## Sofort – 0.26.1 „Schaden begrenzen“ (Zielfenster Mitte November 2026, ca. 1,5 PW, ohne Schemaumbau)

| Baustein | Aufwand |
|---|---|
| Erregernamen nicht mehr in `vehicle.status_note`; Display und Fahrzeugseite zeigen nur „Desinfektion bis HH:MM“ | S |
| Feld „Bemerkungen / Transportgrund“ heißt „Bemerkung (keine Patienten- oder Einsatzangaben)“, mit Hinweis | S |
| Formulare für Fahrzeugübernahme und Funktionskontrolle ohne Vorauswahl (Ja/Nein als Pflicht, km-Feld leer mit „zuletzt …“) | S–M |
| Status 3/4 und die Unterscheidung 1/2 in den Formularen nicht mehr anbieten | S |
| Lesebestätigung speichert keine neue IP und keinen User-Agent mehr | S |
| `defects_by_owner` aus der API-Statistik entfernen | S |

## Jetzt – 0.27 „Pilotfähig“ (Zielfenster Ende Februar 2027, ca. 11 PW)

**Ziel:** Alle Voraussetzungen, damit eine echte Wache den Pilot mit unterschriebener Vereinbarung starten kann.

| Reihenfolge | Baustein | Aufwand |
|---|---|---|
| 1 | Django-Tests gegen PostgreSQL in der CI; Pflicht für alle folgenden Migrationen | 1 PW |
| 2 | Produktgrenze Fuhrpark vollständig: fünf Zustände unter „Fahrzeugzustand“ (Einsatzbereit, Eingeschränkt, Desinfektion, Werkstatt, Außer Dienst); Desinfektionsstufen aus dem Plan, sichtbar nur für Hygiene und die durchführende Person; einmalige Bereinigung der Altdaten mit Löschprotokoll (Ausnahme von append-only per Betreiberentscheid) | 2 PW |
| 3 | Nachweise geschützt: PROTECT und „außer Betrieb nehmen“ für Fahrzeug, Gerät, Mittel und Dienstanweisung; Einweisungen append-only mit Sicht „gültige Einweisung“; fehlende Einweisung warnt die Person selbst und die MPG-Beauftragten, eine harte Sperre ist je Wache einschaltbar; Funktionskontrolle mit Rückfrage und Storno als neuer Datensatz | 1,5 PW |
| 4 | Desinfektion nach Plan, klein: Stufe → Mittel → Freigaberegel („nach Antrocknen“ oder „nach Einwirkzeit“). Bestehende Wachen behalten ihr Verhalten, bis die Hygienebeauftragten die Regel bestätigt haben; neue Wachen fragt der Assistent | 1 PW |
| 5 | Betrieb Pi und LAN: `wachwerk-health` mit lokalem Banner und Alarm über Posteingang, E-Mail oder Signal; verschlüsselte Offsite-Kopie (USB-Rotation oder NAS); Restore-Probe mit echten Daten; RPO/RTO in DSGVO-TOM; USV in die Hardware-Empfehlung (R-016/R-017 für diesen Weg) | 1,5 PW |
| 6 | Datenschutz- und Mitbestimmungsunterlagen: Datenkatalog je aktivem Modul (Felder, Rollen, Zugriffe, Auswertungen, Fristen); verbindliche Löschfristen für die Daten des Pilots; Datenflüsse an Dritte; Varianten BetrVG, LPVG und MAVO/MVG-EKD, KDG/DSG-EKD; kirchliche Aufsicht im Assistenten | 1 PW |
| 7 | Stammdaten-Import als CSV (Artikel, Lagerorte, Medizingeräte, Fahrzeuge) mit Vorlage, Vorschau, Trockenlauf und Transaktion; Konten nur als Einladungen, nie mit Admin-Rolle; Altbestand gekennzeichnet; Datei wird nach dem Import gelöscht | 1,5 PW |
| 8 | Papier-Rückfallebene: Druckansicht leerer Formulare aus der Konfiguration, Fristenliste der Woche, Telefonbuch | 0,5 PW |
| 9 | UX für den Pilot: Glossar zuerst; Fokus nicht verdecken; Rücksprung mit Anker nach „Erledigt“; Sperrbildschirm 800×480; „Gelesen – quittieren“ oben | 1 PW |

**App (eigener Takt, Zielfenster Dezember 2026, ca. 1,5 PW):** Zweig `fertigstellung-2026-10-24` zusammenführen (Offline-Vertrag mit 24 h, kein Cache für admin, cashier und auditor, Schlüssel beim Abmelden sperren, 401/403 zentral, Klar 2) und als App 1.1 veröffentlichen. Das behebt Datenschutzfehler bei schon verteilten Apps und hängt nicht vom Server-Release ab.

**Messbare Ziele 0.27:**
- Ein Test prüft die Auswahlwerte von Fahrzeug und Desinfektion. Kein Feld, kein Status und keine Anzeige hat noch Einsatz- oder Erregerbezug; Altdaten sind nachweislich bereinigt.
- Kein Nachweis lässt sich durch Löschen eines Objekts entfernen (Negativtests für alle Nachweis-Tabellen).
- 300 Artikel und 40 Medizingeräte sind in unter 30 Minuten importiert.
- Ein simulierter Dienstausfall auf dem Pi wird in unter 15 Minuten gemeldet; ein Restore aus der Offsite-Kopie ist belegt.
- Alle Migrationen laufen in der CI grün gegen PostgreSQL.

### Startkriterien für den Pilot (Gate, frühestens März 2027)

- Vereinbarung mit Betriebsrat, Personalrat oder MAV unterschrieben; DSFA-Vorprüfung und VVT liegen vor.
- Löschfristen für die Daten des Pilots verbindlich; Datenflüsse an Dritte dokumentiert oder abgeschaltet.
- Betrieb nur im LAN/Pi ohne Erreichbarkeit aus dem Internet, bis R-015 abgeschlossen ist.
- Pilot-Umfang festgelegt: E2EE-Chat aus, solange R-001/R-020 nicht abgenommen sind.
- Restore mit echten Daten erfolgreich; Papier-Rückfallebene ausgedruckt.
- Ansprechperson, Supportzeiten und Ausstiegsweg (Export) schriftlich vereinbart.

## Als Nächstes – 0.28 „Prüfen“ (Zielfenster Mai 2027, während des Pilots, ca. 10 PW)

**Ziel:** Prüfungen haben ein Ergebnis je Punkt, Mängel entstehen ohne doppelte Erfassung, und niemand verpasst eine Frist.

- Kleines Funktionsmodell: MPG-Beauftragte/r, Hygiene bzw. Desinfektor:in, Material, Fuhrpark, Sicherheit; als Zuordnung zur Mitgliedschaft. (1 PW)
- Checklisten mit Ergebnis je Punkt (in Ordnung, nicht in Ordnung, entfällt mit Grund), Pflichtpunkten, Messwert mit Grenzwerten (damit ist das Temperaturprotokoll von Hand abgedeckt) und Zwischenstand. „Nicht in Ordnung“ legt einen Mangel mit Rückverweis an, das Foto läuft über den vorhandenen Weg. Feste Wiederholmuster statt RFC 5545. Läufe mit Nachweischarakter sind am Terminal gesperrt. (3,5 PW)
- „Mangel in drei Tipps“: Foto aufnehmen, Kategorie und Priorität als Chips, Bezug als Auswahl, Hinweis „bereits gemeldet“. (1 PW)
- Fristen-Erinnerungen bei 30, 7 und 0 Tagen (STK zum Monatsende, MTK zum Jahresende, HU, UVV, Charge, Mangel, Dienstanweisung, Prüfung), abonnierbar je Funktion; montags eine Wochenübersicht; lokal ohne Internet, E-Mail und Signal optional. (2 PW)
- Lesepflicht mit Frist, Zielgruppe und Erinnerung nur an Offene; die Leitung sieht die Quote, Namen nur nach Vereinbarung. (1 PW)
- Nachträge von Papier: Ereigniszeit und Erfassungszeit, sichtbar gekennzeichnet. (0,5 PW)
- Wand-Display als festes 16:9-Raster nur im Kiosk über den Display-Link, ohne Emojis; Screenshot-Test 1920×1080 und 1280×720. (1 PW)

**Messbare Ziele 0.28:**
- In der Pilotwache haben mindestens 90 % der Checklisten-Läufe ein Ergebnis je Punkt (Summe für die Wache).
- Für 100 % der fälligen STK, MTK, HU und UVV geht 30 Tage vorher eine Erinnerung raus; keine Frist läuft ohne vorherige Erinnerung ab.
- Moderierter Bedientest mit 5 Personen: „Mangel mit Foto“ in höchstens 3 Taps.
- axe-core (Playwright) in der CI: 0 Funde der Schwere critical oder serious, hell und dunkel.

## Als Nächstes – 0.29 „Nachweisen und Material“ (Zielfenster August 2027, ca. 11 PW)

**Ziel:** Das MP-Buch ist vollständig, Begehungen sind vorbereitet, Fahrzeuge sind sichtbar vollständig beladen.

- MP-Buch nach § 13 MPBetreibV 2025 vollständig: Inbetriebnahme und Funktionsprüfung am Betriebsort, beauftragte Person, Funktionsstörungen und Bedienungsfehler, Vorkommnis nur als Metadaten, Sicherheitsmitteilung (FSCA) je Typ und Seriennummer mit Sperre bis zur Erledigung, Software-Update als Anlass zur Wiederholungseinweisung, Fristart IT-Sicherheitsüberprüfung, Herstelleranschrift; Gerätestandort und Fahrzeugzuordnung strukturiert mit Verlauf (§ 14 Abs. 2 Nr. 4). (2,5 PW)
- Prüfbericht als Druckansicht (MP-Buch, Bestandsverzeichnis, Desinfektionsnachweise, Fristen, Lesequote als Summe) mit Stand, Seitenzahlen und SHA-256-Prüfsumme über den Export; keine PDF-Bibliothek. (1 PW)
- Fahrzeugübernahme auf den gemeinsamen Prüflauf, Fahrzeugseite aufgeteilt (Status und Fristen; eine Primäraktion „Übernahme starten“, die anderen Aktionen sekundär); die Tagesaufgabe „Fahrzeugcheck“ hakt sich selbst ab. Grundlage im Text: DGUV V70 § 36, MPBetreibV § 4 Abs. 6. (2 PW)
- Soll-Beladung je Lagerort (Fahrzeug, Koffer, Fach), Schritt „Beladung prüfen“ in der Übernahme, der nur Abweichungen zeigt; Nachfüllliste nach FEFO. Nur Bestand, kein Verbrauch je Einsatz. (3 PW)
- Übergabe mit offenen Punkten für die Folgeschicht („Von der Vorschicht offen“) und Rückbestätigung „verstanden / Rückfrage“; Mängel aus der Übernahme gehen an die Ablösung. (1,5 PW)
- Hinweis zur Grenze in Freitexten: lokale Musterprüfung, warnt nur, speichert keine Treffer. (1 PW)

**Messbare Ziele 0.29:**
- Fehlmengen sind nach der Übernahme für 100 % der Fahrzeuge sichtbar.
- Prüfbericht für ein Jahr in unter 1 Minute erstellt; bei einer Probebegehung mit der Pilotwache vollständig.
- Moderierter Bedientest: Fahrzeugübernahme mit höchstens 1 Navigations-Tap; Dauer nur im Test gemessen, nicht im Betrieb.

## 1.0 „Produktionsfreigabe“ (Zielfenster Q4 2027, nicht vor 12 Wochen Pilot und Feature-Freeze)

- Externer Pentest bzw. ASVS-L2-Prüfung (R-015) vor jeder Erreichbarkeit aus dem Internet.
- Barrierefreiheit nach WCAG 2.2 AA intern (R-018), mit Screenreader, 400 % Zoom und Handschuhen am Terminal. Externe BITV-Abnahme und Barrierefreiheitserklärung für öffentliche Träger.
- Lasttest (R-019), Incident-Übung, Monitoring für alle Betriebsarten (R-016), Offsite-Restore belegt (R-017).
- Lieferkette (R-012): volle Ruff-Regeln, CodeQL, Secret-Scan, SBOM und Provenance.
- Abnahme auf echter Pi-Hardware (800×480 und Touch Display 2), mit USV.
- Löschkonzept endgültig je Datenart, Audit-Purge geregelt.
- Ausstieg und Fortführung: vollständiger Export aller Nachweise, Supportfenster je Version, Sicherheitskontakt, möglichst ein Co-Maintainer.
- `GO-LIVE-CHECKLIST.md` vollständig mit Belegen; Dokumentation aufgeräumt.

**Messbare Ziele 1.0:**
- Pilot über mindestens 12 Wochen ohne Datenverlust; Restore-Probe wöchentlich grün.
- SUS mindestens 70 in einer anonymen Umfrage der Pilotwache (keine Messung von Aktivität je Person).
- Keine offenen Pentest-Funde der Stufen kritisch oder hoch.
- Eine Referenzwache stimmt der Nennung zu.

## 1.1 „Arbeitsschutz“ (2028, nur mit Vereinbarung, Reihenfolge nach Pilotbedarf)

- Unterweisungen: Thema, Dienstanweisung mit Version, Anlass, unterweisende Person, Bestätigung im eigenen Konto, Jahresfrist; die Leitung sieht je Person „fällig/ok“, keine Ergebnisse; Teilnehmerliste zum Unterschreiben als Druckansicht. (2,5 PW)
- Führerscheinkontrolle ohne Scan (Klassen, Ablauf C1/C1E, „kontrolliert am / durch“); Hinweise nur an die Person und die Leitung. Bei Bedarf des Pilots vorziehbar. (1 PW)
- Prüfpflichtige Arbeitsmittel (DGUV V3, Feuerlöscher, Leitern, PSA, Tragestuhl) mit Intervall, prüfender Stelle, Ergebnis und Plakettennummer; Protokoll als Referenznummer, PDF-Upload nur nach ADR. (1,5 PW)
- QR-Objektkarten für alle Objekte mit Etikettenbogen als Druckansicht. (1,5 PW)
- BtM-Flankierung: „Plombe unversehrt“ und aktuelle Siegelnummer ohne Verlauf, Fristen für die Monats- und Halbjahresprüfung, BtM-Artikel im Lager gesperrt; nur nach Abstimmung mit ÄLRD und Apotheke. (1 PW)
- Reinigungs- und Desinfektionsplan, aus dem Aufgaben entstehen; Gefahrstoffverzeichnis (GefStoffV § 6 Abs. 12).
- App: QR-Scanner und App-Links öffnen Objektkarte und Übernahme (Web-Oberfläche in der App); native Fachmodule erst bei Bedarf.

## Später (nach Bedarf aus Pilot und Referenzwachen)

- Fortbildungskonto mit Landesprofil, nur Teilnahme und Stunden.
- Offline-Schreiben in der App für Übernahme und Prüfläufe, nach Entscheidung der acht Fragen in `CLIENT-OFFLINE-CONTRACT.md` § 11.
- Träger-Ansicht mit mehreren Mitgliedschaften und SSO über OpenID Connect; nur mit eigenem Security-Review der Stationsbindung.
- Temperatur-Sensor über ein lokales Gateway; nur Aufzeichnung neben einem Datenlogger mit eigenem Alarm.
- Geführter Lagercheck mit Regal-Sperre und Freigabe.
- Meldung von Beinaheunfällen im Arbeitsschutz an der Wache, nach Datenschutz- und Mitbestimmungsprüfung.
- Vorlagen-Austausch als JSON, XLSX-Import (nach ADR), Wartungsbuch nur für Sonderfahrten, Import aus Herstellerportalen (nur Bereitschaftsdaten), Mehrsprachigkeit.

## Bewusst nicht (Produktgrenze)

- Patientendaten, Einsatz- und Dispositionsdaten, Einsatzstatus (FMS 1–4), Alarmierung, Alarm-Display, Personalverfügbarkeit.
- BtM-Bestandsbuch mit Abgängen, klinisches CIRS mit Einsatzbezug.
- Verbandbuch, Impf- und Masernstatus, G26, Tauglichkeit, arbeitsmedizinische Vorsorge (der Eintrag „G26“ aus Phase 5 ist gestrichen).
- Arbeitszeit, Dienstplan, Dienstbörse, Import „wer ist heute im Dienst“; Ranglisten, Quiz-Ergebnisse, Leistungsauswertungen je Person, Bearbeitungsdauer je Person, Aktivitätsquoten, Standortstempel.
- Allgemeine Datei-Uploads, mitgelieferte medizinische Inhalte oder Rechtstexte, Zahlungsabwicklung, Banking-APIs.
- Primäre Sicherheitsüberwachung der Kühlkette, Hydrantenkarten, volles CalDAV.

## Offene Entscheidungen

| # | Frage | Bis wann |
|---|---|---|
| 1 | Ausnahme von append-only für die Bereinigung der Altdaten (Umfang, Protokoll, Backups) | 0.27 |
| 2 | Pilot-Umfang: E2EE-Chat an oder aus; später weiterführen oder auf Signal setzen (R-001, R-020) | 0.27 (Pilot), 0.29 (dauerhaft) |
| 3 | Freigaberegeln der Desinfektion als Standard für bestehende Installationen (Hygiene) | 0.27 |
| 4 | Aufbewahrungsfristen je Datenart | 0.27 verbindlich für den Pilot, 1.0 endgültig |
| 5 | Betrieb aus dem Internet vor dem Pentest | 0.27 (Vorschlag: nein) |
| 6 | Funktionsmodell (`ROLLENMODELL-RETTUNGSWACHE.md` § 5) | vor 0.28 |
| 7 | QR-Login für Nutzer mit MFA | 0.28 |
| 8 | Ausrichtung: nur Rettungsdienst oder mehrere BOS (`organization_profile`) | 0.28 |
| 9 | Neue Upload-Arten (PDF-Protokolle, XLSX) als ADR | vor 1.1 |
| 10 | Genügt die Bestätigung im eigenen Konto als Unterschrift (Unterweisung, BetrSichV-Prüfungen)? Juristisch klären; bis dahin Liste zum Unterschreiben | vor 1.1 |
| 11 | Wer betreibt das Push-Relay? | 1.0 |
| 12 | Offline-Umfang der App (8 Fragen, BYOD/MDM) | nach 1.0 |
| 13 | Lokale KI (RAG) gegenüber der Aussage „kein KI-System“ | nach 1.0 |

## Abhängigkeiten

- **Pilotwache:** Ansprechperson, Testgeräte, WLAN in der Fahrzeughalle, Startdatum, Probebegehung. Ohne Pilot gibt es keine Messung.
- **Mitbestimmung je Trägerart:** Betriebsrat (BetrVG § 87 Abs. 1 Nr. 1, 6, 7), Personalrat (LPVG/BPersVG, Dienstvereinbarung) oder Mitarbeitervertretung bei kirchlichen Trägern (MAVO bzw. MVG-EKD; § 118 Abs. 2 BetrVG). Mehrere Monate Vorlauf einplanen. Voraussetzung für den Pilot, für Unterweisungen, Führerscheinkontrolle und Fortbildung.
- **Datenschutz:** DSGVO/BDSG oder kirchliches Recht (KDG, DSG-EKD) mit der zuständigen Aufsicht; DSFA-Vorprüfung, VVT, Löschkonzept, RPO/RTO, Datenflüsse an Dritte.
- **Fachliche Freigaben:** Hygienebeauftragte für Stufen und Freigaberegeln; MPG-Beauftragte für MP-Buch und Einweisungssperre; ÄLRD und Apotheke für die BtM-Flankierung.
- **Externe Prüfungen:** Pentest (R-015), Barrierefreiheit (R-018), Last (R-019); Budget und Anbieter vor 0.29 festlegen.
- **Hardware:** Pi mit SSD und USV, zweites Backup-Medium, Touch-Display 800×480 und 720×1280, Wand-TV 1080p.
- **App-Verteilung:** Konto für Play Store, TestFlight oder F-Droid, Keystore, Data Safety.
- **Kapazität:** Bei ausfallendem Maintainer greift der Fortführungsplan. Ohne Co-Maintainer bleibt die Zahl der Pilotwachen bei einer.