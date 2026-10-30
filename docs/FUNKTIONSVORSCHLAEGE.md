# Funktionsvorschläge (Stand 30.10.2026)

Abgeleitet aus [KONKURRENZANALYSE.md](KONKURRENZANALYSE.md), der Recherche zu Bedarf und Vorschriften, dem UI/UX-Audit und dem Ist-Stand. Bewertet nach RICE: Reichweite (1–10), Wirkung (1–5), Sicherheit der Annahme (%), Aufwand in Personenwochen (PW) für einen Maintainer mit KI-Unterstützung. Die verbindliche Reihenfolge steht in [ROADMAP.md](ROADMAP.md); dort sind die Korrekturen der kritischen Prüfung (unten) schon eingearbeitet.

| Vorschlag | R | W | S | PW | RICE | Einordnung |
|---|:-:|:-:|:-:|:-:|:-:|---|
| Fahrzeugübernahme ohne Vorauswahl: Ja/Nein je Punkt, „Nein“ öffnet den Mangel | 10 | 4 | 90 | 1 | 36.0 | Jetzt (0.26.1/0.27) |
| Betriebsüberwachung für Pi- und LAN-Installationen | 9 | 4 | 85 | 1 | 30.6 | Jetzt (0.26.1/0.27) |
| Desinfektion nach Plan: Freigabe „nach Antrocknen“ oder „nach Einwirkzeit“ | 9 | 4 | 80 | 1.5 | 19.2 | Jetzt (0.26.1/0.27) |
| Einweisungen lückenlos und Gerätecheck nur für eingewiesene Personen | 8 | 4 | 90 | 1.5 | 19.2 | Jetzt (0.26.1/0.27) |
| Stammdaten-Import per CSV/Excel mit Trockenlauf | 9 | 4 | 80 | 1.5 | 19.2 | Jetzt (0.26.1/0.27) |
| Mitbestimmungs-Paket und sparsamere Lesebestätigung | 9 | 3 | 70 | 1 | 18.9 | Jetzt (0.26.1/0.27) |
| Produktgrenze im Fuhrpark bereinigen: Status 3/4, Transportgrund und Erregernamen entfernen | 10 | 3 | 90 | 1.5 | 18.0 | Jetzt (0.26.1/0.27) |
| App: Review-Korrekturen zusammenführen und Offline-Vertrag einhalten | 7 | 3 | 90 | 2 | 9.4 | Jetzt (0.26.1/0.27) |
| Lesepflicht mit Frist, Zielgruppe und Erinnerung nur an Offene | 9 | 3 | 80 | 1 | 21.6 | Als Nächstes (0.28–1.1) |
| Führerscheinkontrolle für die Halterpflicht, ohne Scan | 8 | 3 | 75 | 1 | 18.0 | Als Nächstes (0.28–1.1) |
| Fristen-Erinnerungen und Wochenübersicht der Fälligkeiten | 10 | 4 | 85 | 2 | 17.0 | Als Nächstes (0.28–1.1) |
| Medizinproduktebuch vollständig nach MPBetreibV 2025 mit Sicherheitsmitteilungen (FSCA) | 8 | 4 | 85 | 2 | 13.6 | Als Nächstes (0.28–1.1) |
| QR-Objektkarten für alle Objekte mit A4-Sammeldruck | 8 | 4 | 80 | 2 | 12.8 | Als Nächstes (0.28–1.1) |
| Prüfpflichtige Arbeitsmittel: DGUV V3, Feuerlöscher, Leitern, PSA, Tragestuhl | 8 | 3 | 80 | 1.5 | 12.8 | Als Nächstes (0.28–1.1) |
| Übergabe mit Struktur, offenen Punkten für die Folgeschicht und Rückbestätigung | 9 | 3 | 70 | 1.5 | 12.6 | Als Nächstes (0.28–1.1) |
| Prüfbericht als PDF für Begehung und Behörde | 8 | 3 | 75 | 1.5 | 12.0 | Als Nächstes (0.28–1.1) |
| Unterweisungen mit Selbstbestätigung, Jahresfrist und Teilnehmerliste zum Unterschreiben | 9 | 4 | 70 | 2.5 | 10.1 | Als Nächstes (0.28–1.1) |
| BtM-Flankierung ohne BtM-Buch: Plombennummer, Prüffristen, Sperre im Lager | 7 | 2 | 70 | 1 | 9.8 | Als Nächstes (0.28–1.1) |
| Checklisten mit Ergebnis je Prüfpunkt, Wiederholregeln und „Entfällt (Grund)“ | 9 | 5 | 80 | 4 | 9.0 | Als Nächstes (0.28–1.1) |
| Soll-Beladung je Fahrzeug, Koffer und Fach mit Nachfüllliste | 8 | 4 | 75 | 3 | 8.0 | Als Nächstes (0.28–1.1) |
| Persönliche Bestätigung von Prüfnachweisen: am Terminal starten, auf dem eigenen Handy abschließen | 7 | 3 | 60 | 2 | 6.3 | Als Nächstes (0.28–1.1) |
| Temperaturprotokoll für Medikamentenkühlschrank und Lager, optional mit lokalem Sensor | 6 | 4 | 60 | 3 | 4.8 | Als Nächstes (0.28–1.1) |
| API und App für die Fachmodule: Übernahme, Desinfektion, Gerätekarte per QR, Quittierungen, Tagesaufgaben | 8 | 3 | 70 | 4 | 4.2 | Als Nächstes (0.28–1.1) |
| Fortbildungskonto mit Landesprofil | 8 | 3 | 60 | 2.5 | 5.8 | Später |
| Beinahe-Unfall im Arbeitsschutz an der Wache (Variante zu CIRS, die die Grenze einhält) | 6 | 2 | 50 | 2 | 3.0 | Später |
| Offline-Schreiben in der App für Fahrzeugübernahme und Prüfläufe | 6 | 4 | 50 | 5 | 2.4 | Später |
| Träger-Ansicht über mehrere Wachen | 4 | 4 | 50 | 6 | 1.3 | Später |
| Klinisches CIRS mit Einsatzbezug | 7 | 3 | 30 | 4 | 1.6 | Bewusst nicht (Produktgrenze) |
| Personal-Gesundheits- und Leistungsdaten: Verbandbuch, Impfstatus, G26, Quiz-Ergebnisse, Ranglisten | 6 | 2 | 20 | 3 | 0.8 | Bewusst nicht (Produktgrenze) |
| BtM-Bestandsbuch mit Abgängen | 7 | 3 | 20 | 6 | 0.7 | Bewusst nicht (Produktgrenze) |
| Einsatznahe Funktionen: Fahrtenbuch mit Einsatzfahrten, Alarm-Display, Verfügbarkeit, Dienstplan, Arbeitszeit | 6 | 2 | 20 | 4 | 0.6 | Bewusst nicht (Produktgrenze) |

## Jetzt (0.26.1/0.27)

### Produktgrenze im Fuhrpark bereinigen: Status 3/4, Transportgrund und Erregernamen entfernen

- **Problem:** Fahrzeugstatus 3 (Anfahrt) und 4 (Einsatzort) werden mit Zeitstempel auditiert und ergeben so eine Zeitreihe der Einsatzphasen. Das Feld „Bemerkungen / Transportgrund“ und die Desinfektionsarten MRSA, Noro und C. diff erlauben Rückschlüsse auf den Infektionsstatus von Patienten.
- **Lösung:** Nur noch fünf Verfügbarkeitszustände: Einsatzbereit, Eingeschränkt, Desinfektion (gesperrt), Werkstatt, Außer Dienst. Eine Datenmigration setzt Status 3/4 auf Einsatzbereit; Audit-Einträge dazu werden nicht mehr neu erzeugt. Statt Erregernamen gibt es Desinfektionsstufen aus dem Plan (Routine, begrenzt viruzid PLUS, sporozid, Volldesinfektion). Das Bemerkungsfeld heißt „Bemerkung (keine Patienten- oder Einsatzangaben)“. API, Display, Sperrbildschirm und Client werden mit angepasst. Ein Test prüft die erlaubten Werte.
- **Für wen:** alle Wachen, Datenschutzbeauftragte, Betriebsrat
- **Belege:** AGENTS.md § 1; core/fleet_models.py Z. 36–43, 202–217; UX-Audit P0-1; FMS-Richtlinie https://www.gesetze-bayern.de/Content/Document/BayVwV156097/true; Art. 9 DSGVO
- **Produktgrenze:** Beseitigt einen bestehenden Verstoß gegen die Grenze; Voraussetzung für jeden Pilot.

### Desinfektion nach Plan: Freigabe „nach Antrocknen“ oder „nach Einwirkzeit“

- **Problem:** Jede Routine-Wischdesinfektion sperrt das Fahrzeug standardmäßig 15 Minuten. Das widerspricht KRINKO 2022 und LARD/NLGA Niedersachsen 2022 („Abwarten … soll unterbleiben“), kostet Verfügbarkeit und verleitet dazu, die Sperre zu umgehen.
- **Lösung:** Jedes Desinfektionsmittel und jede Stufe bekommt eine Freigaberegel. Routine wird ohne Sperre „nach Antrocknen“ freigegeben. Bei Volldesinfektion oder Mitteln, deren Wirkung nur im Suspensionstest belegt ist, sperrt die Einwirkzeit wie bisher, mit Benachrichtigung der Besatzung und ohne automatische Freigabe. Die Regel setzt die Wache im Plan, nicht Wachwerk.
- **Für wen:** Besatzungen, Hygienebeauftragte, Desinfektor:innen
- **Belege:** https://edoc.rki.de/handle/176904/11570; https://www.umwelt-online.de/recht/anlasi/sicher/nds/rettschutz22.htm; core/fleet_models.py lock_timer_applied default=True

### Fahrzeugübernahme ohne Vorauswahl: Ja/Nein je Punkt, „Nein“ öffnet den Mangel

- **Problem:** „BtM-Plombe unversehrt“, „Selbsttests in Ordnung“ und „sauber“ sind vorab angehakt (default=True). Ein Tipp erzeugt so einen Prüfnachweis ohne Prüfung. Der km-Stand ist mit dem alten Wert vorbelegt.
- **Lösung:** Ja/Nein-Paare ohne Vorauswahl, Pflicht vor dem Absenden. „Nein“ verlangt eine Kurzbeschreibung und legt einen Fahrzeugmangel mit Foto an. Das km-Feld bleibt leer, mit dem Hinweis „zuletzt …“ und einer Prüfung „≥ letzter Stand“. Füllstände als Schnellwahl (¼/½/¾/voll). Zwischenstand bleibt erhalten, wenn ein Einsatz dazwischenkommt.
- **Für wen:** Besatzungen, Schichtleitung
- **Belege:** core/fleet_models.py Z. 252–254; UX-Audit P0-2; GOV.UK Checkboxes https://design-system.service.gov.uk/components/checkboxes/; PSTrax Pflichtpunkte https://pstrax.com/ems/vehicle-inspections/

### Einweisungen lückenlos und Gerätecheck nur für eingewiesene Personen

- **Problem:** Einweisungsnachweise werden per update_or_create überschrieben oder gelöscht (core/mpg_views.py Z. 422/447). Durch CASCADE gehen MP-Buch-Einträge verloren, wenn ein Konto oder Gerät gelöscht wird. Der 1-Tap-„Check“ fragt nicht nach und prüft keine Einweisung.
- **Lösung:** DeviceTrainingRecord wird append-only (Ersteinweisung, Wiederholung, nach Software-Update, beauftragte Person durch den Hersteller). Der UniqueConstraint wird durch eine Sicht auf die „gültige Einweisung“ ersetzt. PROTECT statt CASCADE; ausgeschiedene Personen werden pseudonymisiert. „Funktion geprüft“ geht nur für eingewiesene Personen, mit Rückfrage und 5 Minuten Storno als neuer Datensatz. Die Fahrzeugübernahme warnt, wenn jemand aus der Besatzung für ein Gerät an Bord nicht eingewiesen ist.
- **Für wen:** MPG-Beauftragte, alle Anwender
- **Belege:** MPBetreibV 2025 §§ 4, 11, 13 https://www.gesetze-im-internet.de/mpbetreibv_2025/__13.html; UX-Audit P0-3; Recherche needs-regulation 1.3
- **Produktgrenze:** Die Einweisungsmatrix bleibt sachbezogen. Keine Auswertung je Person über die Frage „eingewiesen ja/nein“ hinaus.

### Stammdaten-Import per CSV/Excel mit Trockenlauf

- **Problem:** Eine Pilotwache müsste hunderte Artikel, Lagerorte, Medizingeräte und Fahrzeuge von Hand anlegen. Das ist der größte Aufwand beim Umstieg. Einen Import-Befehl gibt es nicht.
- **Lösung:** Import für Artikel (PZN/GTIN), Lagerorte, Medizingeräte (Seriennummer, UDI, letzte STK/MTK), Fahrzeuge und Teamkonten. Ablauf: Vorlage herunterladen, hochladen, Vorschau mit Fehlern je Zeile, Trockenlauf, dann Import in einer Transaktion mit Audit. Die Datei wird nach dem Import gelöscht und ist kein allgemeiner Upload. Dazu ein Management-Befehl für Admins.
- **Für wen:** Wachenleitung, IT der Pilotwache
- **Belege:** RDSuite CSV/Excel https://www.rdsuite.de/faq/; HiOrg Import/Export https://info.hiorg-server.de/funktionen-und-preise/; MediConnect Stammdatenservice

### Betriebsüberwachung für Pi- und LAN-Installationen

- **Problem:** wachwerk-health und die Alarmierung gibt es nur auf dem Hetzner-Weg. Gerade die typische Wache mit Pi oder LAN bemerkt einen Dienstausfall, fehlende Backups oder eine fehlgeschlagene Restore-Probe nicht.
- **Lösung:** wachwerk-health in allen Betriebsarten. Alarm an den Admin-Posteingang, per E-Mail und Signal, sowie lokal als Banner auf Übersicht und Display („Backup seit 26 h fehlt“). Ein optionaler Ping an healthchecks.io bleibt abschaltbar, damit der Inselbetrieb ohne Internet möglich bleibt. RPO und RTO werden in DSGVO-TOM festgelegt.
- **Für wen:** Admins, Betreiber
- **Belege:** internal-state Abschnitt 3 (Monitoring nur Hetzner); REMEDIATION R-016/R-017

### Mitbestimmungs-Paket und sparsamere Lesebestätigung

- **Problem:** Ohne Betriebs- bzw. Dienstvereinbarung startet kein Pilot. Audit, Lesequoten und Zeitstempel sind nach § 87 Abs. 1 Nr. 6 BetrVG objektiv geeignet, Verhalten zu überwachen. SOPReceipt speichert IP und User-Agent.
- **Lösung:** Aus den aktiven Modulen entsteht automatisch eine Anlage zur Betriebsvereinbarung: Zweck, Datenfelder, Rollen, Fristen, Auswertungsverbot zur Leistungskontrolle, Einsichtsrechte. IP und User-Agent bei Lesebestätigungen entfallen oder werden nach 30 Tagen gelöscht. defects_by_owner wird nur noch nach Funktion statt nach Person ausgewertet, oder abschaltbar gemacht.
- **Für wen:** Betriebsrat/Personalrat, Datenschutzbeauftragte, Wachenleitung
- **Belege:** BetrVG § 87 https://www.gesetze-im-internet.de/betrvg/__87.html; BAG 1 ABR 7/15; EuGH C-34/21; core/orga_views.py Z. 153
- **Produktgrenze:** Verringert den Bezug zu Leistungsdaten.

### App: Review-Korrekturen zusammenführen und Offline-Vertrag einhalten

- **Problem:** Die Korrekturen C1–C11 aus der Review vom 24.10. liegen nur auf origin/fertigstellung-2026-10-24. Die App auf main cacht unter anderem Kaffeekasse und Mängel ohne Ablauf und ohne Rollenausschluss. Beim Abmelden werden die Chat-Schlüssel nicht gesperrt.
- **Lösung:** Zweig nach main zusammenführen: Cache nach CLIENT-OFFLINE-CONTRACT (24 h; nur me, Checklisten, Übergaben; kein Cache für admin, cashier und auditor), CryptoSession beim Abmelden sperren, 401/403 zentral behandeln, Design Klar 2. Dann ein Release mit Server-Paarung 0.27.x und korrigierter README.
- **Für wen:** alle App-Nutzer
- **Belege:** internal-state 1.3; docs/CLIENT-OFFLINE-CONTRACT.md § 2

## Als Nächstes (0.28–1.1)

### Checklisten mit Ergebnis je Prüfpunkt, Wiederholregeln und „Entfällt (Grund)“

- **Problem:** ChecklistItem ist nur Text, und eine ganze Liste bekommt einen einzigen Abschlussvermerk. Es gibt kein Ergebnis, keinen Messwert und keine Verknüpfung „nicht in Ordnung → Mangel“. Intervalle gibt es nur täglich, wöchentlich oder monatlich, und Checklisten sind an kein Objekt gebunden.
- **Lösung:** ChecklistRun und ChecklistItemResult (append-only): in Ordnung, nicht in Ordnung, entfällt; optional Messwert mit Grenzwerten und Pflichtpunkte. „Nicht in Ordnung“ legt beim Abschluss einen Mangel mit vorbelegtem Objekt und Rückverweis an. Das Foto läuft über den bestehenden DefectAttachment-Weg, ohne neue Upload-Art. Wiederholregeln nach RFC 5545 (Quartal, „jeden 1. Montag“), Bindung an Fahrzeug, Gerät oder Raum, „Entfällt heute – Grund“ und Zwischenstand. Fahrzeugübernahme und Tagesaufgabe „Fahrzeugcheck“ nutzen denselben Lauf, damit kein fünftes Prüfkonzept entsteht.
- **Für wen:** Besatzungen, Schichtleitung, QM
- **Belege:** SafetyCulture https://help.safetyculture.com/en-US/000082/, https://help.mitti.com/000158; Lumiform https://lumiformapp.com/de/produkt/massnahmen; RDSuite Ampel https://www.rdsuite.de/wachbuch/; BetrSichV § 14 Abs. 7
- **Produktgrenze:** Freitext mit Hinweis „keine Patienten- oder Einsatzangaben“, Länge begrenzt.

### QR-Objektkarten für alle Objekte mit A4-Sammeldruck

- **Problem:** QR-Codes gibt es nur einzeln für Medizingeräte und Fahrzeuge. Für Schlüssel, Pool-Geräte, Lagerfächer, Räume und Checklisten fehlen sie. Der Nachweis der letzten Prüfung ist am Objekt nicht zugänglich.
- **Lösung:** Eine einheitliche URL je Objekt, ohne Token, auf derselben Origin. Sie öffnet die Objektkarte: Status, letzte Prüfung (Datum, Ergebnis, Person), nächste Frist, offene Mängel, Knöpfe „Mangel melden“ und „Prüfung starten“. Ohne Anmeldung führt sie zum Login bzw. QR-Login. Etikettenbogen als A4-PDF mit Klartext. Der Fahrzeug-QR führt direkt zur Übernahme. In der App öffnet ein App-Link die Karte.
- **Für wen:** alle, besonders Halle und Lager
- **Belege:** BetrSichV § 14 Abs. 7 https://www.gesetze-im-internet.de/betrsichv_2015/__14.html; MPBetreibV § 13 Abs. 3; SafetyCulture Asset-QR https://help.safetyculture.com/002882; HiOrg-Workflows

### Fristen-Erinnerungen und Wochenübersicht der Fälligkeiten

- **Problem:** Erinnerungen gibt es nur für „Fahrzeug frei“ und die Kaffeekasse. STK, MTK, HU, UVV, Chargenverfall, Mangelfristen, ungelesene Dienstanweisungen und fällige Prüfungen erscheinen nur in der Übersicht.
- **Lösung:** Neue Benachrichtigungsarten über Posteingang, WebPush, E-Mail und Signal. Fristen bei 30, 7 und 0 Tagen, je Funktion oder Rolle abonnierbar. Montags eine Übersicht „Diese Woche fällig“ an die Leitung. Alles funktioniert lokal; E-Mail und Signal sind optional. Die Fälligkeit wird nach Regel berechnet: STK mit Ablauf des Monats, MTK mit Ablauf des Jahres.
- **Für wen:** Wachenleitung, MPG-Beauftragte, Fuhrpark
- **Belege:** core/notification_models.py Z. 22–24; MPBetreibV §§ 12, 15; PRODUKT-FAHRPLAN Phase 4; RETTpro STK/MTK-Erinnerung

### Medizinproduktebuch vollständig nach MPBetreibV 2025 mit Sicherheitsmitteilungen (FSCA)

- **Problem:** Es fehlen: Inbetriebnahme und Funktionsprüfung am Betriebsort, beauftragte Person, Funktionsstörungen und Bedienungsfehler, Vorkommnismeldungen, Herstelleranschrift, Wartungsart „Software-Update“ und Aufbewahrung fünf Jahre nach Außerbetriebnahme.
- **Lösung:** Neue append-only Eintragsarten: Inbetriebnahme, Funktionsstörung/Bedienungsfehler, Vorkommnismeldung nur mit Metadaten (Datum, BfArM-Aktenzeichen, Link), Software-Update (löst eine Wiederholungseinweisung aus). Sicherheitsmitteilungen je Gerätetyp und Seriennummer mit Status betroffen / Maßnahme / erledigt und Sperre bis zur Erledigung. Herstelleranschrift, Zuordnung, Datenklasse „MP-Buch“ im Löschkonzept.
- **Für wen:** MPG-Beauftragte, Wachenleitung
- **Belege:** MPBetreibV 2025 § 13 Abs. 2/3, § 14 https://www.gesetze-im-internet.de/mpbetreibv_2025/__13.html; MPAMIV § 3 https://www.gesetze-im-internet.de/mpamiv/__3.html; RDSuite Vorkommnisse https://www.rdsuite.de/geraete/
- **Produktgrenze:** Vorkommnis ausdrücklich ohne Patientenangaben; die eigentliche Meldung bleibt beim BfArM.

### Prüfbericht als PDF für Begehung und Behörde

- **Problem:** Bei einer Begehung durch Gesundheitsamt, Gewerbeaufsicht oder Träger müssen MP-Buch, Bestandsverzeichnis, Desinfektionsnachweise und Fristen vorgelegt werden. Heute gibt es dafür nur CSV und Einzelseiten.
- **Lösung:** Ein Knopf „Prüfbericht“ je Bereich und Zeitraum: PDF mit Stand, Seitenzahlen, SHA-256-Prüfsumme, Bestandsverzeichnis (§ 14), MP-Buch (§ 13), Desinfektionsnachweise je Fahrzeug, Fristenliste Fuhrpark und Lesequote der Dienstanweisungen als Summe. Das PDF wird lokal erzeugt.
- **Für wen:** Wachenleitung, Hygiene, MPG-Beauftragte
- **Belege:** RDSuite PDF-Export https://www.rdsuite.de/wachbuch/; LAGER//APP https://lagerapp.org/; IfSG § 23 Abs. 6
- **Produktgrenze:** Lesequoten nur als Summe; eine Namensliste nur gemäß Dienstvereinbarung.

### Lesepflicht mit Frist, Zielgruppe und Erinnerung nur an Offene

- **Problem:** Neuigkeiten verlangen immer eine Quittierung, ohne Frist, Zielgruppe oder Nachfassen. Die Leitung muss Offene von Hand ansprechen.
- **Lösung:** Schalter „Quittierung erforderlich“, Frist „bis Datum“, Zielgruppe nach Rolle oder Funktion, geplante Veröffentlichung. Nach X Tagen geht eine Erinnerung nur an Offene über die vorhandenen Kanäle; der zweite Kanal ist optional. „Für dich“ zeigt Fälliges. Die Leitung sieht die Quote, Namen nur gemäß Dienstvereinbarung.
- **Für wen:** Wachenleitung, alle Mitglieder
- **Belege:** Staffbase https://support.staffbase.com/hc/en-us/articles/360017402559-Resending-Notifications-for-a-Post; SafetyCulture Heads Up https://help.safetyculture.com/003101; Connecteam https://connecteam.com/employee-communication-app/updates/
- **Produktgrenze:** § 87 BetrVG: Namenslisten nur mit Vereinbarung.

### Übergabe mit Struktur, offenen Punkten für die Folgeschicht und Rückbestätigung

- **Problem:** Nicht erledigte Punkte gehen beim Schichtwechsel nicht gebündelt über. Die Quittierung kennt kein „verstanden / Rückfrage“. Freitext lädt zu Einsatzangaben ein.
- **Lösung:** Übergabe mit den Feldern Lage (ein Satz), offene Punkte als abhakbare Liste, „Wenn … dann …“ und Textbausteine je Wache. Offene Punkte, Tagesaufgaben und Mängel erscheinen bei Schichtbeginn als „Von der Vorschicht offen“. Beim Quittieren wählt man „verstanden“ oder „Rückfrage“ mit Kurztext. Hinweis „keine Patienten- oder Einsatzdaten“.
- **Für wen:** Besatzungen, Schichtleitung
- **Belege:** RDSuite Folgeschicht https://www.rdsuite.de/wachbuch/; I-PASS NEJM 2014 https://www.nejm.org/doi/full/10.1056/NEJMsa1405556; Shiftconnector Textbausteine https://www.produktion.de/technik/digitales-schichtbuch-textbausteine-erleichtern-uebergabe/1723314
- **Produktgrenze:** Kein Feld wie „Patient summary“ aus I-PASS; Textbausteine liefert Wachwerk nicht mit.

### Persönliche Bestätigung von Prüfnachweisen: am Terminal starten, auf dem eigenen Handy abschließen

- **Problem:** Am Terminal laufen Checklisten und Mängel über das Dienstkonto. BetrSichV § 14 Abs. 7 verlangt aber den Namen der prüfenden Person. Das Dienstkonto darf laut AGENTS.md nicht erweitert werden.
- **Lösung:** Prüfläufe, die als Prüfnachweis markiert sind, zeigen am Terminal einen QR-Code mit der Lauf-URL, ohne Token. Die Person schließt auf dem eigenen Konto ab und bestätigt erneut per Passkey, TOTP oder Passwort. Gespeichert werden Name, Zeit und eine SHA-256-Prüfsumme. Optional Vier-Augen-Prinzip beim Freigeben gesperrter Geräte.
- **Für wen:** Prüfende, Schichtleitung
- **Belege:** BetrSichV § 14 Abs. 7 https://www.gesetze-im-internet.de/betrsichv_2015/__14.html; MP-FEUER Signatur; PSTrax dual authentication https://pstrax.com/features/
- **Produktgrenze:** Kein Unterschrift-Pad mit Biometrie; ob die Bestätigung als elektronische Signatur genügt, muss juristisch geklärt werden.

### Soll-Beladung je Fahrzeug, Koffer und Fach mit Nachfüllliste

- **Problem:** Mindest- und Sollbestand gelten nur für die ganze Wache (MedicalItem). Eine Beladeliste je RTW oder Rucksack und den Abgleich Soll gegen Ist gibt es nicht. Genau das ist die tägliche Arbeit der stellvertretenden Wachenleitung.
- **Lösung:** Soll und Minimum je StorageLocation, optional je Fach oder Modul. Die Übernahme bekommt den Schritt „Beladung prüfen“, der nur Abweichungen zeigt. Aus den Fehlmengen entsteht mit einem Klick ein Auffüllauftrag aus dem Zentrallager nach FEFO, und der Bestellvorschlag wird genauer. Später als Ausbau: ein geführter Lagercheck mit Freigabe.
- **Für wen:** Besatzungen, Materialverantwortliche
- **Belege:** RDSuite Beladungslisten https://www.rdsuite.de/lager/; RescueSync https://rescuesync.de/; Drägerware.ZMS https://draeger-cloud.com/produkte/draegerware-zms; HiOrg Sollmengen
- **Produktgrenze:** Nur Bestand, kein Bezug „verbraucht bei Einsatz X“.

### Prüfpflichtige Arbeitsmittel: DGUV V3, Feuerlöscher, Leitern, PSA, Tragestuhl

- **Problem:** Prüffristen gibt es nur an Medizingeräten und Fahrzeugen. StationAsset und InventoryItem haben keine Frist.
- **Lösung:** Eine Prüffrist mit Intervall, prüfender Stelle, Ergebnis, Plakettennummer und Protokoll-PDF an StationAsset und InventoryItem. Ampel in der Übersicht, QR-Objektkarte, Erinnerungen. Intervalle setzt die Wache selbst, Wachwerk gibt keine Werte vor (Doppelung mit STK nach DIN EN 62353 klären).
- **Für wen:** Wachenleitung, Sicherheitsbeauftragte
- **Belege:** DGUV V3 § 5 https://vorschriften.bgn-branchenwissen.de/daten/dguv/3/5.htm; ASR A2.2; PRODUKT-FAHRPLAN Phase 4

### Unterweisungen mit Selbstbestätigung, Jahresfrist und Teilnehmerliste zum Unterschreiben

- **Problem:** ArbSchG § 12, DGUV V1, BioStoffV und GefStoffV § 14 verlangen jährliche, dokumentierte Unterweisungen. Eine Lesebestätigung (SOPReceipt) ist keine Unterweisung.
- **Lösung:** Unterweisung mit Thema, verknüpfter Dienst- oder Betriebsanweisung (Version), Anlass (jährlich, neues Gerät, neues Mittel, Beinaheunfall), Datum, unterweisender Person mit Weisungsbefugnis und Teilnehmenden. Die Teilnehmenden bestätigen auf dem eigenen Konto. Zusätzlich eine PDF-Teilnehmerliste zum Unterschreiben, solange offen ist, ob die elektronische Bestätigung genügt. Fälligkeit nach 12 Monaten, die Person sieht ihren eigenen Stand, die Leitung nur fällig/ok.
- **Für wen:** Wachenleitung, alle Mitglieder
- **Belege:** ArbSchG § 12 https://www.gesetze-im-internet.de/arbschg/__12.html; DGUV Regel 100-001 https://publikationen.dguv.de/widgets/pdf/download/article/2942; GefStoffV § 14 https://www.gesetze-im-internet.de/gefstoffv_2010/__14.html
- **Produktgrenze:** Keine Quiz-Ergebnisse und keine Bestehensquoten je Person; Mitbestimmung nach § 87 Abs. 1 Nr. 6 und 7 BetrVG.

### Führerscheinkontrolle für die Halterpflicht, ohne Scan

- **Problem:** Der Halter haftet, wenn jemand ohne gültige Fahrerlaubnis fährt (§ 21 StVG), und C1 gilt höchstens fünf Jahre (§ 23 FeV). Wachwerk unterstützt die Kontrolle nicht.
- **Lösung:** Je Person werden Klassen, Ablaufdatum C1/C1E, „kontrolliert am / durch“ und die nächste Kontrolle gespeichert. Intervall je Wache, Erinnerung an Person und Leitung, Warnung bei der Fahrzeugübernahme, wenn die Kontrolle abgelaufen ist. Optional ein QR-Siegel.
- **Für wen:** Wachenleitung, Fahrer:innen
- **Belege:** StVG § 21 https://www.gesetze-im-internet.de/stvg/__21.html; FeV § 23 https://www.gesetze-im-internet.de/fev_2010/__23.html; RDSuite https://www.rdsuite.de/; RETTpro NFC-Siegel
- **Produktgrenze:** Keine Kopie oder Fotos des Führerscheins, keine Punkte, keine Sperrgründe, keine Gesundheitsangaben.

### Temperaturprotokoll für Medikamentenkühlschrank und Lager, optional mit lokalem Sensor

- **Problem:** Medikamente müssen in festen Temperaturbereichen gelagert werden. Wachwerk bildet Temperatur nur über eine Checkliste ab. Wettbewerber alarmieren über ihre Cloud.
- **Lösung:** Stufe 1: Messpunkte mit Grenzwerten (2–8 °C, 15–25 °C), manuelles Min/Max-Protokoll append-only, Ampel. Stufe 2: Sensor-Eingang lokal per HTTP oder MQTT von einem Gateway im Wachennetz. Bei Überschreitung oder Sensorausfall gibt es Alarm auf Übersicht, Display, Push und Signal und einen Mangel. Betroffene Chargen werden zur Prüfung markiert. Export als PDF/CSV. Alles funktioniert ohne Internet.
- **Für wen:** Materialverantwortliche, Wachenleitung
- **Belege:** RDSuite isiGUARD https://www.rdsuite.de/isiguard/; RETTpro Logger https://www.rettpro.de/; Studie PMC12211764 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12211764/

### BtM-Flankierung ohne BtM-Buch: Plombennummer, Prüffristen, Sperre im Lager

- **Problem:** Wachen wollen BtM-Abläufe unterstützt haben. Ein BtM-Buch mit Abgängen liegt aber außerhalb der Produktgrenze.
- **Lösung:** Siegelnummer bei der Fahrzeugübernahme. Fristen ohne Mengen für die Monatsprüfung durch den beauftragten Arzt und die halbjährliche Begehung durch die Apotheke. Tresor- und Schlüsselübergabe über die Ausstattung. Artikel mit dem Merkmal „BtM“ sind im Lager für Verbrauch, Umlagerung und Verfall gesperrt. Hinweis im Notizfeld der Bewegungen; Verweis auf das amtliche BtM-Buch.
- **Für wen:** Wachenleitung, ÄLRD, Apotheke
- **Belege:** BtMVV §§ 6, 13 https://www.gesetze-im-internet.de/btmvv_1998/__13.html; core/fleet_models.py btm_seal_intact
- **Produktgrenze:** Keine Mengen, keine Abgänge, kein Einsatzbezug. Vor der Umsetzung mit ÄLRD und Apotheke abstimmen.

### API und App für die Fachmodule: Übernahme, Desinfektion, Gerätekarte per QR, Quittierungen, Tagesaufgaben

- **Problem:** Für Fuhrpark, MPG, Lager, Dienstanweisungen, Neuigkeiten, Tagesaufgaben und Wiki gibt es keine API und keine App-Oberfläche. Die QR-Codes zeigen auf Webseiten. In /me/ fehlen Modulflags.
- **Lösung:** Versionierte Endpunkte mit Vertragstests und OpenAPI für Fahrzeugübernahme, Desinfektion, Objektkarte, Funktionskontrolle, SOP- und Neuigkeiten-Quittierung und Tagesaufgaben. Vollständige Modulflags in /me/. In der App ein QR-Scanner, der Objektkarten öffnet. Die OpenAPI-Datei deckt danach alle 55+ Routen ab.
- **Für wen:** App-Nutzer
- **Belege:** internal-state 1.2, 2.3 Nr. 3; core/api/views.py Z. 515–527

## Später

### Fortbildungskonto mit Landesprofil

- **Problem:** NRW verlangt 30 h, Hessen 38 h, das Saarland 30 Unterrichtseinheiten, die Praxisanleitung 24 h im Jahr. Nachweise liegen verstreut.
- **Lösung:** „Mein Fortbildungskonto“ mit Teilnahme, Stunden, Art (Präsenz oder Fernunterricht) und Nachweis-PDF. Ein Landesprofil enthält Soll, Pflichtanteile, Höchstanteil Fernunterricht und Stichtag. Ampel für die Person, Sammelübersicht fällig/ok für die Leitung. Qualifikationen mit Ablauf (Praxisanleitung, Desinfektor).
- **Für wen:** Mitarbeitende, Wachenleitung, Praxisanleitung
- **Belege:** NRW https://recht.nrw.de/mblnrw/2021-s926; NotSan-APrV § 3 https://www.gesetze-im-internet.de/notsan-aprv/__3.html; RETTpro, RDSuite, qualido
- **Produktgrenze:** Nur Teilnahme und Stunden; keine Ergebnisse von Leistungsnachweisen, kein G26, keine Tauglichkeit. Erst mit Dienstvereinbarung.

### Offline-Schreiben in der App für Fahrzeugübernahme und Prüfläufe

- **Problem:** In Fahrzeughalle und Garage ist der Empfang schlecht. Die App kann nur lesen.
- **Lösung:** Eine Ausgangswarteschlange mit Idempotenzschlüssel, höchstens 24 h, an Person und Wache gebunden, nur für Übernahme und Checklisten-Läufe. Abgleich, sobald das Wachen-WLAN erreichbar ist. Freigaben, Sperren, Quittierungen und Administration nie offline. Lokale verschlüsselte Datenbank statt Secure Storage.
- **Für wen:** Besatzungen
- **Belege:** SafetyCulture Offline https://help.safetyculture.com/en-US/002907/; MP-FEUER GER-App; docs/CLIENT-OFFLINE-CONTRACT.md §§ 6–8, 11

### Träger-Ansicht über mehrere Wachen

- **Problem:** Träger mit mehreren Wachen brauchen einen Überblick und wachenübergreifende Umlagerung. Heute gilt eine Mitgliedschaft und eine Rolle je Person (get_membership().first()).
- **Lösung:** Mehrere Mitgliedschaften mit Wachenumschalter, Funktionen statt Rollen (MPG-Beauftragte, Desinfektor). Eine Träger-Rolle sieht je Wache nur Kennzahlen (Fristen, Mängel, Mindestbestände). Gemeinsame Dienstanweisungen und Umlagerung zwischen Wachen. Dazu optional SSO über OpenID Connect.
- **Für wen:** Träger, Springer, Bereichsleitung
- **Belege:** VISION, RescueSync https://rescuesync.de/, RDSuite https://www.rdsuite.de/faq/; core/access.py Z. 22–29; docs/ROLLENMODELL-RETTUNGSWACHE.md § 5
- **Produktgrenze:** Träger sieht nur Kennzahlen, keine Daten je Person.

### Beinahe-Unfall im Arbeitsschutz an der Wache (Variante zu CIRS, die die Grenze einhält)

- **Problem:** Beinaheunfälle sind laut DGUV ein Anlass für Unterweisungen, etwa Glätte in der Halle oder eine defekte Rampe. Bisher gibt es keinen Meldeweg.
- **Lösung:** Strukturierte Meldung nur zu Gebäude, Fahrzeug und Arbeitsmittel: Kategorie, Ort per Objekt-QR, optional anonym, eigene Löschfrist, Status. Ergebnis ist eine Maßnahme oder ein Anlass für eine Unterweisung. Keine Felder für Patient, Einsatznummer oder Einsatzzeit; Freitext begrenzt und mit Warnhinweis.
- **Für wen:** alle Mitglieder, Sicherheitsbeauftragte
- **Belege:** DGUV Regel 100-001; DIVERA-Formulare „Beinaheunfälle“ https://www.divera247.com/funktionen/organisation/formulare
- **Produktgrenze:** Nur Arbeitsschutz an der Wache; vorher Datenschutz- und Mitbestimmungsprüfung.

## Bewusst nicht (Produktgrenze)

### Klinisches CIRS mit Einsatzbezug

- **Problem:** Wettbewerber (RETTpro, RDSuite, qualido) bieten CIRS an. Ein CIRS-Fall beschreibt aber fast immer einen Einsatz oder einen Patienten.
- **Lösung:** Nicht bauen. Die Variante ohne Grenzverletzung ist die Arbeitsschutz-Meldung oben. Für klinisches CIRS verweist Wachwerk auf vorhandene Systeme (z. B. CIRS des Trägers).
- **Für wen:** –
- **Belege:** https://www.rettpro.de/rettungsdienst-software-funktionen/; https://www.rdsuite.de/; AGENTS.md § 1
- **Produktgrenze:** Einsatz- und mittelbar Patientendaten im Freitext lassen sich nicht zuverlässig ausschließen.

### BtM-Bestandsbuch mit Abgängen

- **Problem:** RDSuite bietet ein digitales BtM-Buch mit Hashkette an.
- **Lösung:** Nicht bauen. Stattdessen die BtM-Flankierung (Plombe, Fristen, Sperre im Lager).
- **Für wen:** –
- **Belege:** BtMVV §§ 13, 14 https://www.gesetze-im-internet.de/btmvv_1998/__14.html; https://www.rdsuite.de/btm/
- **Produktgrenze:** Jeder Abgang verknüpft Einsatz, Patient und verabreichende Person; damit sind alle drei Ausschlüsse berührt. Außerdem entstünde eine zweite, nicht amtliche Bestandszahl.

### Personal-Gesundheits- und Leistungsdaten: Verbandbuch, Impfstatus, G26, Quiz-Ergebnisse, Ranglisten

- **Problem:** Wettbewerber führen Verbandbuch, Impfstatus und Personalakte. Inspektions-Apps bieten Ranglisten und Punkte je Person.
- **Lösung:** Nicht bauen. G26/Tauglichkeit aus PRODUKT-FAHRPLAN Phase 5 streichen. Stattdessen nur Team-Werte für die ganze Wache, z. B. „Dienstanweisungen zu 92 % quittiert“.
- **Für wen:** –
- **Belege:** DGUV V1 § 24; IfSG § 20; ArbMedVV § 3; BetrVG § 87 Abs. 1 Nr. 6; SC Training Ranglisten https://training.safetyculture.com/blog/lms-leaderboard/
- **Produktgrenze:** Gesundheitsdaten (Art. 9 DSGVO) und Leistungsdaten von Beschäftigten.

### Einsatznahe Funktionen: Fahrtenbuch mit Einsatzfahrten, Alarm-Display, Verfügbarkeit, Dienstplan, Arbeitszeit

- **Problem:** RETTpro, DIVERA und rescuetrack bieten diese Funktionen. Wachen mit Alarmmonitor erwarten sie teilweise.
- **Lösung:** Nicht bauen. Varianten innerhalb der Grenze: ein Wartungsbuch nur für Sonderfahrten (Werkstatt, Tanken, Überführung), ohne Adressen und Einsatzzeiten; ein ICS-Import „wer ist heute im Dienst“ höchstens später; ein Display ohne Alarmmodus.
- **Für wen:** –
- **Belege:** https://www.divera247.com/funktionen/alarmmonitor; https://www.rescuetrack.com/de-de/products/infodisplay/; README (kein Einsatzleitsystem)
- **Produktgrenze:** Einsatz- und Alarmierungsdaten sowie Leistungskontrolle.

## Korrekturen der kritischen Prüfung

Korrekturen an den Feature-Vorschlägen. Belege habe ich im Code und in Primärquellen nachgeprüft; das Repository ist unverändert.

1. Produktgrenze Fuhrpark (jetzt): richtig, aber unvollständig.
   - Status 1/2 („auf Wache“ oder „auf Funk“) sind ebenfalls Anwesenheitsdaten und fallen auch weg.
   - Die Überschrift heißt „Fahrzeugzustand“ statt „Verfügbarkeit“, sonst widerspricht sie „Bewusst nicht“.
   - Erregernamen landen heute auch in `vehicle.status_note` (`core/fleet_models.py` Z. 228–232).
   - Die Altdaten (Audit, kind-Werte, Notizen) brauchen eine einmalige, protokollierte Bereinigung als Ausnahme von append-only.
   - Die Desinfektionsstufe sehen nur Hygiene und die durchführende Person.
   - Es gibt keine Fuhrpark-API und keinen Fuhrpark-Client. Der Hinweis „API und Client anpassen“ entfällt.
   - Sofortanteil als 0.26.1, Rest in 0.27. Aufwand 2 PW.

2. Desinfektion nach Plan (jetzt): fachlich richtig. KRINKO 2022 ist geprüft: „in the majority of cases … after air drying“, Abwarten nötig, wenn die Wirkung nur im Suspensionstest belegt ist (https://edoc.rki.de/handle/176904/11570).
   - Die Migration darf bestehende Wachen nicht still auf „ohne Sperre“ umstellen. Die Hygiene bestätigt die Regel.
   - Den NLGA-Text aus der Primärquelle (Nds. MBl. 2022 S. 1332) zitieren, nicht aus dem umwelt-online-Auszug.
   - Den Plan nur in kleiner Form umsetzen. Aufwand 1 PW.

3. Fahrzeugübernahme ohne Vorauswahl (jetzt): Dasselbe gilt für `DeviceRoutineCheck` (default=True, `core/mpg_models.py` Z. 274–277). Grundlage ist DGUV V70 § 36, nicht BetrSichV. Die Formularebene kommt in 0.26.1. „Zwischenstand bei Einsatz“ wandert in 0.28 (Prüflauf).

4. Einweisungen (jetzt): append-only und PROTECT gelten für alle Nachweise, auch Desinfektion, Übernahme, Funktionskontrolle, Wartung und SOPReceipt.
   - Fehlende Einweisungen warnen standardmäßig nur; die harte Sperre ist je Wache einschaltbar. Die Altbestände liegen auf Papier.
   - Die Warnung „Besatzung nicht eingewiesen“ entfällt. Sie braucht Besatzungsdaten und eine feste Gerätezuordnung, die es nicht gibt, und zeigt Lücken von Kolleg:innen. Es bleibt eine Warnung nur an die Person selbst.

5. Stammdaten-Import (jetzt): nur CSV. Konten nur als Einladungen, nie mit Admin-Rolle. STK/MTK als „Altbestand“ gekennzeichnet. XLSX nur nach ADR.

6. Betriebsüberwachung Pi/LAN (jetzt): ergänzt um eine verschlüsselte Offsite-Kopie (USB oder NAS), einen Restore mit echten Daten und eine USV. R-016 und R-017 sind offen und nicht erledigt. Aufwand 1,5 PW.

7. Mitbestimmungs-Paket (jetzt): Erzeugt wird ein Datenkatalog, kein fertiger Vertragstext. Dazu kommen Varianten für Personalrat und kirchliche Träger (MAVO/MVG-EKD, KDG/DSG-EKD, § 118 Abs. 2 BetrVG). Die Löschfristen für die Pilotdaten werden verbindlich.

8. App-Zweig zusammenführen: eigener Takt im App-Repo (Dezember 2026), unabhängig vom Server-Release.

9. Checklisten mit Ergebnis je Punkt (0.28): Aufwand realistisch 6–8 PW, deshalb aufgeteilt.
   - 0.28: Ergebnis, Pflichtpunkt, Messwert, Mangel.
   - 0.29: Fahrzeugübernahme auf denselben Lauf.
   - Feste Wiederholmuster statt RFC 5545.
   - Läufe mit Nachweischarakter sind am Terminal gesperrt (AGENTS.md § 4).
   - BetrSichV § 14 Abs. 7 nicht als Begründung für Tageschecks nennen.

10. QR-Objektkarten: Für Fahrzeuge und Geräte gibt es sie schon. Alle übrigen Objekte und der Etikettenbogen als Druckansicht kommen in 1.1. Auf der Karte gibt es nur eine Primäraktion (DESIGN-SYSTEM Regel 2).

11. Fristen-Erinnerungen (0.28): Sie hängen am Funktionsmodell, das deshalb vor 0.28 entschieden wird.

12. MP-Buch vollständig (0.29): ergänzt um die Fristart IT-Sicherheitsüberprüfung (§ 13 Abs. 2 Nr. 4, § 17 Abs. 3) und einen strukturierten Gerätestandort mit Verlauf (§ 14 Abs. 2 Nr. 4).

13. Prüfbericht als PDF: Druckansicht mit SHA-256 über den Export statt einer PDF-Bibliothek. Aufwand 1 PW.

14. Lesepflicht mit Frist (0.28): unverändert.

15. Übergabe mit Struktur (0.29): I-PASS nur als Anregung zitieren, ohne die Zahl −23 %. Mängel aus der Übernahme gehen an die Ablösung (DGUV V70 § 36 Abs. 2).

16. Persönliche Bestätigung am Terminal → Handy: Der rechtliche Treiber entfällt, BetrSichV § 14 Abs. 7 gilt nur für Prüfungen durch befähigte Personen. Ersetzt durch „Nachweis-Läufe nur auf persönlichen Konten“. Die Weitergabe vom Terminal ans Handy per QR kommt höchstens später.

17. Soll-Beladung (0.29): bleibt; hängt an der strukturierten Gerätezuordnung.

18. Prüfpflichtige Arbeitsmittel (1.1): Protokoll als Referenznummer, PDF-Upload nur nach ADR.

19. Unterweisungen (1.1): Die Leitung sieht je Person „fällig/ok“. Das ist für ArbSchG § 12 nötig und wird in der Vereinbarung geregelt. Die Teilnehmerliste ist eine Druckansicht.

20. Führerscheinkontrolle (1.1, vorziehbar): Warnungen nur an die Person und die Leitung, nicht an die Besatzung.

21. Temperaturprotokoll: Stufe 1 geht in den Checklisten-Messwert auf (0.28). Stufe 2 kommt später, nur als Aufzeichnung neben einem zertifizierten Datenlogger. „Warnung“ statt „Alarm“.

22. BtM-Flankierung (1.1): keine Siegelnummern-Historie je Übernahme.

23. API und App für die Fachmodule: zunächst App-Links und Web-Objektkarten in der App (1.1), native Module später.

24. Fortbildungskonto, Offline-Schreiben, Träger-Ansicht und Beinaheunfall bleiben unter „Später“. Die Träger-Ansicht braucht ein eigenes Security-Review der Stationsbindung.

25. „Nicht bauen“-Liste bleibt richtig. Ergänzen: Import „wer ist heute im Dienst“, Bearbeitungsdauer je Person, Aktivitätsquoten.

26. Messziele: Ziele wie „Median der Übernahme unter 3 Minuten“ oder „70 % des Teams wöchentlich aktiv“ nur in moderierten Tests bzw. per anonymer Umfrage messen, nie im Betrieb.

27. UX-Plan an das DESIGN-SYSTEM anpassen:
   - Touch-Ziele 48 px statt 44 px.
   - Eine Primäraktion je Ansicht (B2, B5).
   - Keine Schreibaktion in der Listenzeile (C4, A6); oder Regel 9 ausdrücklich ändern.
   - B1 `overflow:hidden` nur im Kiosk.
   - „Zuletzt genutzt“ nur im localStorage.
   - „Ampeln nicht nur über Farbe“ gilt schon heute (Regel 5).
   - A1–A4 und B5 nicht doppelt zur Feature-Arbeit zählen.

28. Konkurrenzanalyse korrigieren:
   - RETTpro: 30 Nutzer ab 202 €/Monat netto, Obergrenze offen; Kennzahlen „Stand 2022“.
   - HiOrg: 14,90 € inkl. MwSt. für 50 aktive Mitglieder, dazu eine Gratis-Stufe.
   - RDSuite: „nicht in Ordnung wird Mangel“ ist ◐.
   - HiOrg-SSO ist OAuth 2 (◐).
   - Den AVV-Vorteil einschränken; den Grenzvorteil erst nach 0.27 nennen.

### Ergänzungen, die in der Synthese fehlten

- Papier-Rückfallebene und Nachtrag: Fällt der Pi aus, braucht die Wache sofort Papier. Druckbare Leerformulare (Übernahme, Desinfektion, Funktionskontrolle, Checklisten) aus der aktuellen Konfiguration, eine Fristenliste der Woche als Ausdruck und ein Telefonbuch-Ausdruck. Später wird nachgetragen, mit Ereigniszeit und Erfassungszeit, sichtbar als „Nachtrag“ gekennzeichnet. Wenig Aufwand (Druck-CSS), hoher Nutzen für Vertrauen und Begehungen.
- Offsite-Backup und Restore-Nachweis für Pi und LAN (R-017 offen): verschlüsselte Kopie mit USB-Rotation oder auf ein NAS des Trägers, Alarm bei fehlender Kopie, Restore-Probe mit echten Daten vor dem Pilot (GO-LIVE-CHECKLIST), USV für den Pi in die Hardware-Empfehlung. Bisher gibt es Offsite nur für Hetzner.
- Nachweise vollständig schützen: PROTECT und „außer Betrieb nehmen / archivieren“ statt Löschen für Fahrzeug, Medizingerät, Desinfektionsmittel und Dienstanweisung. Vorauswahl auch bei `DeviceRoutineCheck` entfernen. Nachweise ausgeschiedener Personen pseudonymisieren, die Nachweise selbst bleiben.
- Einmalige Altdaten-Bereinigung nach der Korrektur der Grenze (Audit zu Status 3/4 und 1/2, Werte mrsa/noro/c_diff, „Transportgrund“, status_note-Texte) mit Löschprotokoll und ausdrücklicher Ausnahme von append-only.
- Kleines Funktionsmodell vor 0.28: MPG-Beauftragte/r, Hygienebeauftragte/r bzw. Desinfektor:in, Materialverantwortliche, Fuhrpark, Sicherheitsbeauftragte. Funktionen als Zuordnung zur Mitgliedschaft, ohne Umbau der Rollen. Voraussetzung für Fristen-Abos, beauftragte Person nach § 13 Abs. 2 Nr. 3 MPBetreibV und Freigaben.
- Gerätestandort strukturiert mit Verlauf (MPBetreibV 2025 § 14 Abs. 2 Nr. 4 „Standort und betriebliche Zuordnung“, https://www.gesetze-im-internet.de/mpbetreibv_2025/__14.html) und Fahrzeugtausch auf das Reservefahrzeug (Geräte und Beladung mit wenigen Schritten umziehen). Das ist eine tägliche Last auf der Wache und Grundlage für die Beladung und für „Geräte an Bord“. Heute ist `location` nur Freitext.
- Hinweis zur Grenze in allen Freitexten (Übergabe, Mangel, Bemerkungen): lokale Musterprüfung im Browser auf Einsatznummer, Uhrzeit mit Adresse, „Pat.“ und Geburtsdatum. Sie warnt nur, blockiert nicht und speichert keine Treffer. Die stärkste Absicherung gegen schleichende Patientendaten, bei kleinem Aufwand.
- Ausstieg und Fortführung: vollständiger Export aller Nachweise (CSV/JSON plus Druckansicht) für den Fall, dass eine Wache Wachwerk verlässt. Dazu ein Fortführungsplan (Co-Maintainer, Sicherheitskontakt, Supportfenster je Version, Reaktionszeit bei Sicherheitslücken). Ohne das unterschreibt kein Träger einen Pilot bei einem einzelnen Maintainer.
- Varianten für Datenschutz und Mitbestimmung je Trägerart: privat (BetrVG, DSGVO/BDSG), kommunal (Personalrat, LPVG, Dienstvereinbarung), kirchlich (MAVO bzw. MVG-EKD, KDG bzw. DSG-EKD mit kirchlicher Aufsicht; § 118 Abs. 2 BetrVG https://www.gesetze-im-internet.de/betrvg/__118.html).
- Pilot-Umfang und Feature-Freeze: welche Module im Pilot laufen (E2EE-Chat aus, solange R-001/R-020 nicht abgenommen sind), nur LAN/Pi ohne Erreichbarkeit aus dem Internet bis R-015, während der 12 Pilotwochen nur Fehlerbehebung und Wünsche aus dem Pilot.
- Datenflüsse an Dritte in DSFA und VVT (Signal über signal-cli, SMTP, Push-Relay mit FCM/APNs, healthchecks.io, Updates über ghcr.io) und ein Schalter „Inselbetrieb: alles Externe aus“, der den Zustand prüfbar anzeigt.
- MP-Buch: Fristart „IT-Sicherheitsüberprüfung“ (§ 13 Abs. 2 Nr. 4 und § 17 Abs. 3 MPBetreibV 2025, für Software als Medizinprodukt der Klassen IIb/III; https://www.gesetze-im-internet.de/mpbetreibv_2025/__17.html). Selten, aber ein Pflichtfeld.
- Mangel an Werkstatt oder Träger weitergeben: Ausdruck oder E-Mail eines Fahrzeug- oder Gerätemangels ohne Personennamen, mit Rückmeldestatus. Das ist der häufigste Medienbruch auf der Wache.
- Richtige Rechtsgrundlagen im Fachmodul Fuhrpark und MPG: DGUV Vorschrift 70 § 36 (Prüfung vor Schichtbeginn, Mängel an den Ablöser melden: https://vorschriften.bgn-branchenwissen.de/daten/dguv/70/36.htm) und MPBetreibV 2025 § 4 Abs. 6 statt BetrSichV § 14 Abs. 7 als Begründung für Übernahme und Funktionskontrolle.

Die Hinweise auf Vorschriften sind eine technische Vorprüfung, keine Rechtsberatung.
