# Test- und Go-live-Checkliste

Ein erfolgreicher Docker-Start ist keine fachliche, datenschutzrechtliche oder
betriebliche Freigabe.

## Technik

- [ ] CI und Anwendungstests sind grün
- [ ] Container-Healthchecks sind grün
- [ ] Anwendung ist nur über den vorgesehenen TLS-Einstieg erreichbar
- [ ] Anmeldung erfolgt nur über lokale Konten hinter dem vorgesehenen Proxy
- [ ] Rollenmatrix wurde mit mehreren Testkonten geprüft
- [ ] Backup wurde in einer isolierten Datenbank wiederhergestellt
- [ ] Abhängigkeiten und Container-Images wurden gescannt
- [ ] Monitoring, Alarmierung, Patch- und Incident-Prozess sind aktiv

## Fachlichkeit

- [ ] Zweck, erlaubte Datenfelder und verantwortliche Stelle sind beschlossen
- [ ] Patienten-, Einsatz- und Gesundheitsdaten sind organisatorisch untersagt
- [ ] Rollen, Kalenderzweck und optionale Kassenregeln sind abgenommen
- [ ] Hinweise zu externen Quellen sind fachlich geprüft
- [ ] Aufbewahrungs- und Löschfristen sind je Datenart festgelegt
- [ ] Papier-Rückfallebene ausgedruckt und an der Wache hinterlegt (Deckblatt,
  Formulare je Fahrzeug und Gerätestandort, Telefonbuch); die Fristenliste wird
  wöchentlich neu gedruckt (`/papier/`, siehe `docs/OFFLINE-BETRIEB.md` § 7)

## Datenschutz und Mitbestimmung

- [ ] anwendbares Datenschutz- und Mitbestimmungsrecht ist bestimmt (bei kirchlichen Trägern KDG bzw. DSG-EKD, `COMPLIANCE.md`)
- [ ] Datenschutz, Informationssicherheit und Interessenvertretung sind beteiligt
- [ ] Vereinbarung mit der Interessenvertretung ist unterschrieben (Bausteine: `MITBESTIMMUNG-VORLAGE.md`)
- [ ] Datenkatalog der Wache ist erzeugt und als Anlage beigefügt (`data_catalog --station auto`, Referenz `DATENKATALOG.md`)
- [ ] Datenflüsse an Dritte sind dokumentiert oder abgeschaltet (`DATENFLUESSE.md`)
- [ ] Löschfristen für die Daten des Pilots sind freigegeben (`LOESCHKONZEPT.md`, Vorschlag für den Pilot)
- [ ] VVT, DSFA-Vorpruefung und Betroffeneninformation sind freigegeben
- [ ] Cookie-/TDDDG-Hinweis unter `/datenschutz/` ist an die Stelle angepasst
- [ ] AI-Act-Prüfung dokumentiert (Produkt ohne KI-System / kein Scoring)
- [ ] Auskunft, Berichtigung, Löschung und Incident-Meldung sind geregelt
- [ ] Audit-Zweck und Auswertungsverbot sind dokumentiert
- [ ] Altdaten-Bereinigung ausgeführt (`cleanup_legacy_data --apply`); Audit-Eintrag „Altdaten einmalig bereinigt“ je Wache vorhanden

## Produktion

- [ ] externer Sicherheitstest oder angemessene ASVS-Pruefung ist abgeschlossen
- [ ] Betreiberangaben, Datenschutzinformation und Supportweg sind vorhanden
- [ ] Versions- und Updateprozess inkl. Rollback ist geübt
- [ ] verschlüsseltes Offsite-Backup und erfolgreicher Restore-Test existieren
- [ ] formale Go-live-Freigabe ist dokumentiert
