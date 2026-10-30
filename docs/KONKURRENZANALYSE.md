# Konkurrenzanalyse Wachwerk (Stand 30.10.2026)

Grundlage: öffentliche Herstellerseiten, abgerufen am 30.10.2026. Die Produkte wurden nicht selbst getestet. „?“ heißt: steht nicht auf der öffentlichen Seite. Für Wachwerk gilt Version 0.26.0. Der Vergleich ersetzt den alten RETTpro-Vergleich (`docs/MARKTVERGLEICH-RETTPRO.md`, entfernt mit 0.25.0). Eine zweite, kritische Prüfung hat Preise, Matrix und Rechtsanker nachgeprüft und korrigiert. Daraus folgen [ROADMAP.md](ROADMAP.md), [FUNKTIONSVORSCHLAEGE.md](FUNKTIONSVORSCHLAEGE.md) und [UX-PLAN.md](UX-PLAN.md).

## 1. Marktkarte

| Kategorie | Produkte | Nähe zu Wachwerk |
|---|---|---|
| Komplettsuiten für die Wachenorganisation | RETTpro, **RDSuite**, VISION (E/M/C), RescueSync | sehr hoch |
| QM- und Dokumentenplattform | qualido | hoch |
| Verwaltung für Hilfsorganisationen | HiOrg-Server, drkserver | mittel |
| Materialwirtschaft | MediConnect NEO, LAGER//APP | hoch (Lager) |
| Wissen und SOP | HELPP (CH), SOP-EASY | gering |
| Personal und Dienstplan | TailoRD, DSM-Ware | außerhalb der Grenze |
| Einsatznah (konkurriert nur beim Display) | rescuetrack Infodisplay, DIVERA 24/7 | gering |
| Geräteportale der Hersteller | corpuls.manager, Stryker LIFENET, ZOLL DeviceDashboard | Ergänzung |
| Angrenzende Muster | SafetyCulture/Mitti, Lumiform, MP-FEUER, Drägerware.ZMS, Staffbase, Connecteam, Shiftconnector, PSTrax, First Arriving | Vorbilder für Bedienabläufe |

Bei der Recherche wurde kein anderes quelloffenes Produkt für die Wachenorganisation gefunden. Selbst betreiben lassen sich nur qualido und laut einer Broschüre von 2021 die E/M/C-Produkte.

## 2. Steckbriefe der Hauptwettbewerber

**RETTpro (SEMAsystems, seit 2011, laut Firmenchronik über 150 Kunden und rund 15.000 Nutzer, Stand 2022).**
- Module: Wachbuch, Desinfektion „nach Rahmen-Hygieneplan“, Fahrtenbuch, Schlüssel, Fahrzeugmängel, CIRS, MPGpro (MP-Buch, Einweisungen, STK/MTK), LAGERpro (Mindestmengen, Barcode).
- Außerdem: Fortbildung, Führerscheinkontrolle per NFC, Personalakte mit Impfstatus, Verbandbuch, Dienstplan, Arbeitszeit, Temperaturkontrolle.
- Integrationen: WEINMANN Connect (ein fehlgeschlagener Funktionscheck füllt eine Mangelmeldung vor), Mercedes-Telematik, RFID-Beladecheck für 3.725 € einmalig plus 204,50 €/Jahr.
- Betrieb: „Unsere Software arbeitet online“, ohne genannten Serverstandort.
- Preis: Paket RETTpro ab 190 €/Monat plus 0,40 € je Nutzer (netto); LAGERpro (ab 109 €) und MPGpro (ab 99 €) gibt es auch einzeln.
- Stärke: größter Funktionsumfang. Schwäche: nur Cloud; viele Gesundheits- und Personaldaten in einem System.
- Quellen: https://www.rettpro.de/ · https://www.rettpro.de/rettungsdienst-software-funktionen/ · https://www.rettpro.de/rettungsdienst-software-preise-pakete/ · https://www.rettpro.de/weinmann-connect/ · https://www.rettpro.de/rfid-geraetecheck/ · https://www.rettpro.de/rettungsdienst-software/

**RDSuite (rescuecontrol, seit 2011, über 200 Organisationen) – bisher nicht betrachtet, mindestens so direkt wie RETTpro.**
- Wachbuch: offene Punkte gehen automatisch an die Folgeschicht; Fahrzeugcheck mit Ampel-Auswertung; Desinfektion „mit Erreger und Hygieneplan“; Einträge unveränderbar.
- Lager: Chargen, Beladungslisten je Fahrzeug, Inventur per Scanner, Prüfung bei Chargenrückruf.
- Geräte: §§ 13/14 MPBetreibV, Einweisungen, Störungs- und Vorkommnismeldungen.
- Weitere Module: Führerscheinkontrolle, kostenloses CIRS, BtM-Buch mit SHA-256-Hashkette und Vier-Augen-Prinzip, isiGUARD (LoRaWAN-Temperatursensoren mit Alarm), RFID-Inventur.
- Betrieb: Cloud in Deutschland „ohne eigenen Server“, Import per CSV/Excel. Preis nur auf Anfrage.
- Quellen: https://www.rdsuite.de/ · https://www.rdsuite.de/wachbuch/ · https://www.rdsuite.de/lager/ · https://www.rdsuite.de/geraete/ · https://www.rdsuite.de/fahrzeuge/ · https://www.rdsuite.de/btm/ · https://www.rdsuite.de/isiguard/ · https://www.rdsuite.de/faq/

**VISION / CareMan Office (E/M/C, opta data).**
- Portal mit Mitteilungen, Dienstanweisungen, Schichtberichten, Gerätebuch, Material mit Chargen und QR, Mandantenfähigkeit. Der Schwerpunkt liegt auf Disposition und Abrechnung.
- Gehostet im Rechenzentrum. Die Quelle ist eine Broschüre von 2021: https://www.rettungsdienstkongress.de/wp-content/uploads/2021/11/EMC_CareMan_Office_Broschuere_2021_web_21092021-1.pdf

**RescueSync (PAW Software).**
- Fuhrpark, Inhaltslisten mit Soll und Fehlmengen am Fahrzeug, Lager mit MHD, MPG (UDI, STK/MTK), OIDC-SSO.
- Preis nach Zahl der Fahrzeuge: 29–399 €/Monat für alle Funktionen und beliebig viele Nutzer.
- Wachbuch und Desinfektion nennt die Seite nicht. https://rescuesync.de/

**qualido.**
- Checklisten per QR, Prüfungen und Einweisungen nach MPBetreibV, CIRS und interne Meldestelle (HinSchG), Dokumentenlenkung mit Kenntnisnahme, Audits, Matrix-Messenger.
- Betrieb „im eigenen Rechenzentrum oder auf unseren Servern“. Kein Lager, kein Wachbuch.
- https://www.qualido.com/rettungsdienst/ · https://www.qualido.com/

**HiOrg-Server.**
- Material mit Sollmengen je Lagerort, Reservierung, Qualifikationen, Führerschein-Überprüfung, Lesebestätigung, SSO; „HiOrg-Workflows“ mit Checklisten per QR sind in der Beta.
- Preis: 14,90 €/Monat inkl. MwSt. für 50 aktive Mitglieder in 10 Gruppen, je weitere 50 Nutzer 12 €; kostenlose Stufe bis 50 Nutzer und 5 Gruppen. Kein MP-Buch, keine Desinfektion.
- https://info.hiorg-server.de/funktionen-und-preise/ · https://info.hiorg-server.de/

**Materialwirtschaft.**
- MediConnect NEO: Bestellvorschlag; Lieferscheine kommen bidirektional aus dem Fleischhacker-Shop; dafür an einen Lieferanten gebunden. https://www.fleischhacker.biz/fileadmin/user_upload/Werbung/Prospekte/MediConnect_NEO_2022.pdf
- LAGER//APP (Beta): Zählen parallel mit Regal-Sperre; die Leitung gibt Korrekturen frei; unbekannte Codes werden nie automatisch zugeordnet. https://lagerapp.org/

**Weitere Produkte.**
- HELPP: offline und in vier Sprachen. https://www.helpp-app.ch/
- rescuetrack Infodisplay: Themen-Brett mit Zeitsteuerung. https://www.rescuetrack.com/de-de/products/infodisplay/
- DIVERA 24/7: DAILY 3.600 €/Jahr. https://www.divera247.com/preise/gesundheitswesen
- Geräteportale: https://corpuls.world/wAssets/docs/broschueren/231128-corpuls-aed-de-es-web.pdf · https://www.stryker.com/gb/en/emergency-care/products/lifenet-system/index-eu-eemea.html · https://www.zoll.com/en-us/products/software-and-data/hospital-software/device-dashboard

**Angrenzende Muster, die Wachwerk übernehmen sollte:**
- SafetyCulture/Mitti: Ergebnis je Prüfpunkt wird zur Maßnahme, Asset-QR, „Won't do“ mit Grund. https://help.safetyculture.com/en-US/000082/ · https://help.mitti.com/000158 · https://help.safetyculture.com/002882
- Lumiform: automatische Maßnahmen. https://lumiformapp.com/de/produkt/massnahmen
- Staffbase: Erinnerung nur an Nicht-Leser. https://support.staffbase.com/hc/en-us/articles/360017402559-Resending-Notifications-for-a-Post
- Drägerware.ZMS: Beladelisten. https://draeger-cloud.com/produkte/draegerware-zms
- MP-FEUER: Prüf-App, die offline arbeitet. https://www.mpbos.de/produkte/erweiterungen/webservice-apps/webservice-apps-ger/
- I-PASS: strukturiertes Übergabeschema. Die Studie betrifft Patientenübergaben im Krankenhaus und taugt für die Wache nur als Anregung zur Gestaltung, nicht als erwartete Wirkung. https://www.nejm.org/doi/full/10.1056/NEJMsa1405556
- PSTrax: Pflichtpunkte vor dem Absenden. https://pstrax.com/ems/vehicle-inspections/
- First Arriving: Display je Raum. https://firstarriving.com/

## 3. Funktionsmatrix (Kurzfassung)

Legende: ● vorhanden · ◐ teilweise · – fehlt · ? nicht genannt. WW = Wachwerk 0.26.0, RP = RETTpro, RDS = RDSuite, RS = RescueSync, QL = qualido, HO = HiOrg.

| Funktion | WW | RP | RDS | RS | QL | HO |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Wachbuch und Übergabe mit Quittierung | ● | ● | ● | ? | ? | – |
| Offene Punkte gehen an die Folgeschicht | ◐ | ? | ● | ? | ? | – |
| Lesebestätigung mit Version | ● | ● | ◐ | ◐ | ● | ● |
| Ergebnis je Prüfpunkt, „nicht in Ordnung“ wird Mangel | – | ? | ◐ | ? | ● | ◐ Beta |
| Desinfektionsnachweis mit Einwirkzeit-Sperre | ● | ◐ | ◐ | ? | ? | – |
| MP-Buch, STK/MTK, Einweisungen | ● | ● | ● | ◐ | ● | – |
| Funktionskontrolle sperrt das Gerät bis zur Freigabe | ● | ◐ | ◐ | ? | ? | – |
| Vorkommnisse und FSCA je Gerät | – | ◐ | ● | ? | ◐ | – |
| Chargen, FEFO, Rückrufsperre | ● | ? | ● | ◐ | – | – |
| Kühlware mit verkürzter Haltbarkeit | ● | ? | ? | ? | – | – |
| Soll-Beladung je Fahrzeug oder Koffer | ◐ | ● | ● | ● | – | ● |
| Temperatursensorik | – | ● | ● | ? | – | – |
| QR-Objektkarten für alle Objekte | ◐ | ● | ● | ● | ● | ◐ |
| Führerscheinkontrolle | – | ● | ● | – | – | ● |
| Unterweisung und Fortbildung | – | ● | ● | – | ● | ● |
| CIRS | – | ● | ● | – | ● | – |
| Stammdaten-Import (CSV/Excel) | – | ? | ● | ? | ? | ● |
| SSO (OIDC) | – | ● | ? | ● | ? | ◐ OAuth 2 |
| Mehrere Wachen eines Trägers | ◐ | ● | ● | ● | ● | ● |
| Quelloffen | ● AGPL | – | – | – | – | – |
| Betrieb ohne Internet, Server in der Wache | ● | – | – | ? | ◐ | – |
| Wachen-Display und Touch-Terminal | ● | ? | ? | ? | – | – |
| Zwei-Faktor und Passkeys | ● | ? | ? | ? | ? | ? |
| Öffentliche Demo ohne Anmeldung | ● | – | – | – | – | ◐ Gratis-Stufe |
| Listenpreis | 0 € | ab 190 €/Monat netto | auf Anfrage | 29–399 €/Monat | auf Anfrage | 0 € bzw. 14,90 €/Monat brutto |

Anmerkungen zu Wachwerk:
- **Soll-Beladung:** Der Sollbestand gilt heute nur für die ganze Wache (`MedicalItem.target_stock`), nicht je Lagerort.
- **QR-Codes:** gibt es nur für Medizingeräte und Fahrzeuge, jeweils einzeln.

## 4. Wo Wachwerk vorn liegt

1. **Quelloffen (AGPL-3.0) und selbst betrieben.** Kein Lizenzgeber hat Zugriff auf die Daten; ein Auftragsverarbeitungsvertrag mit einem Softwareanbieter entfällt. Externe Fernwartung, IT-Dienstleister und die optionalen Dienste (Signal, E-Mail, Push-Relay, Healthcheck-Ping, Updates von ghcr.io) gehören trotzdem in VVT und DSFA.
2. **Inselbetrieb.** Server, Pi und Terminal arbeiten ohne Internet weiter; Tests mit blockierten externen Aufrufen belegen das. Der Wettbewerb ist online-pflichtig (RETTpro „arbeitet online“, RDSuite „ohne eigenen Server“).
3. **Produktgrenze als Datenschutzvorteil.** Kein Verbandbuch, kein Impfstatus, keine Einsätze. Das erleichtert Datenschutz-Folgenabschätzung und Mitbestimmung, sobald die eigenen Grenzverstöße im Fuhrpark (Lücke 7) behoben sind.
4. **Sicherheitslogik im Fachablauf:**
   - Die Einwirkzeit-Sperre benachrichtigt die Besatzung.
   - Eine nicht bestandene Funktionskontrolle sperrt das Gerät; die Freigabe kommt erst, wenn alle Mängel erledigt sind.
   - FEFO und Rückrufsperre.
   - Kühlware mit verkürzter Haltbarkeit (bei keinem Wettbewerber öffentlich beschrieben).
5. **Bedienung an der Wache.** Touch-Terminal mit Sperrbildschirm und Wachen-Code, Wachen-Display ohne Cloud, Übersicht „N Punkte brauchen Aufmerksamkeit“.
6. **Nachprüfbare Sicherheit.** TOTP, Passkeys, QR-Login, append-only Audit, öffentliche Review-Berichte.
7. **Einstieg.** 0 € Lizenz, Installation mit einem Befehl, nächtliche Updates mit Rollback, als einziges Produkt eine öffentliche Demo ohne Anmeldung.

## 5. Lücken (priorisiert)

1. **Prüfen:** kein Ergebnis je Prüfpunkt; „nicht in Ordnung“ erzeugt keinen Mangel; keine QR-Objektkarten für alle Objekte; keine Erinnerungen an Fristen (nur „Fahrzeug frei“ und Kaffeekasse).
2. **Nachweise:**
   - Einweisungen werden überschrieben (`core/mpg_views.py` Z. 422/447).
   - Im MP-Buch fehlen Pflichtangaben (§ 13 Abs. 2 Nr. 2, 3, 6 MPBetreibV 2025).
   - Es gibt keinen Prüfbericht als PDF.
   - Am Terminal fehlt der Name der prüfenden Person.
3. **Arbeitsschutz und Personal:** keine Unterweisungen, keine Führerscheinkontrolle, keine Fristen für sonstige Arbeitsmittel (DGUV V3, Feuerlöscher).
4. **Material:** keine Soll-Beladung je Lagerort, kein geführter Lagercheck, kein Temperaturprotokoll.
5. **Umstieg und Skalierung:** kein Stammdaten-Import, kein SSO, keine Träger-Ansicht.
6. **Vertrauen:** keine Referenzwache, kein Support-Vertrag, kein Fortführungsplan bei nur einem Maintainer; Pentest und Barrierefreiheitsprüfung stehen aus; eine verschlüsselte Offsite-Kopie gibt es nur für den Hetzner-Weg, nicht für Pi und LAN.
7. **Eigene Verstöße gegen die Produktgrenze:**
   - Fahrzeugstatus 3/4 (Anfahrt, Einsatzort) werden mit Zeitstempel auditiert.
   - Das Feld „Bemerkungen / Transportgrund“ und die Desinfektionsarten mit Erregernamen (MRSA, Noro, C. diff) lassen Rückschlüsse auf Patienten zu (`core/fleet_models.py` Z. 39–40, 202–217).

## 6. Bewusst nicht übernehmen

| Funktion | Wo | Grund |
|---|---|---|
| Verbandbuch, Impfstatus, G26/Tauglichkeit | RETTpro, RDSuite | Gesundheitsdaten (Art. 9 DSGVO) |
| BtM-Buch mit Abgängen | RDSuite | Jeder Abgang verknüpft Patient, Einsatz und Person (BtMVV §§ 13, 14) |
| Einsätze, Fahrtenbuch mit Einsatzfahrten, Alarm-Display | RETTpro, DIVERA, rescuetrack | Einsatz- und Alarmdaten |
| Arbeitszeit, Dienstplan | RETTpro, TailoRD, RDSuite | Leistungskontrolle (§ 87 Abs. 1 Nr. 6 BetrVG), außerhalb der Grenze |
| Ranglisten, Quiz-Ergebnisse, Standortstempel | SC Training, Connecteam | Leistungs- und Verhaltensdaten |
| Biometrische Unterschrift, Meldungen ohne Konto | MP-FEUER, SafetyCulture | DSGVO Art. 9 bzw. Sicherheitsmodell |

## 7. Preise im Vergleich (Listenpreise)

| Produkt | Beispiel |
|---|---|
| RETTpro | Paket ab 190 €/Monat + 0,40 € je Nutzer netto, bei 30 Nutzern also ab 202 €/Monat; LAGERpro und MPGpro einzeln ab 109 € bzw. 99 € |
| RescueSync | bis 8 Fahrzeuge 99 €/Monat |
| HiOrg | kostenlos bis 50 Nutzer / 5 Gruppen, sonst ab 14,90 €/Monat brutto |
| DIVERA | 3.600 €/Jahr plus mindestens 2.000 € Einrichtung |
| Wachwerk | 0 € Lizenz, Hardware ca. 300–450 € |

Bei Wachwerk ist die eigene Betreuung der eigentliche Kostenfaktor. Ein ehrlicher Kostenvergleich rechnet sie mit.

## 8. Rechtliche Anker (Primärquellen)

- MPBetreibV 2025: https://www.gesetze-im-internet.de/mpbetreibv_2025/__11.html · https://www.gesetze-im-internet.de/mpbetreibv_2025/__13.html
- BetrSichV § 14 Abs. 7 (Prüfaufzeichnung mit Name für Prüfungen prüfpflichtiger Arbeitsmittel durch befähigte Personen, nicht für den täglichen Fahrzeug- oder Gerätecheck): https://www.gesetze-im-internet.de/betrsichv_2015/__14.html
- DGUV Vorschrift 70 § 36 (Prüfung vor Schichtbeginn, Mängel an die Ablösung melden): https://vorschriften.bgn-branchenwissen.de/daten/dguv/70/36.htm
- MPBetreibV 2025 § 4 Abs. 6 (Funktionsprüfung vor der Anwendung) und § 14 Abs. 2 Nr. 4 (Standort): https://www.gesetze-im-internet.de/mpbetreibv_2025/
- ArbSchG § 12: https://www.gesetze-im-internet.de/arbschg/__12.html
- DGUV Regel 100-001: https://publikationen.dguv.de/widgets/pdf/download/article/2942
- GefStoffV § 14: https://www.gesetze-im-internet.de/gefstoffv_2010/__14.html
- StVG § 21: https://www.gesetze-im-internet.de/stvg/__21.html
- FeV § 23: https://www.gesetze-im-internet.de/fev_2010/__23.html
- BtMVV § 13: https://www.gesetze-im-internet.de/btmvv_1998/__13.html
- KRINKO Flächen 2022: https://edoc.rki.de/handle/176904/11570
- LARD/NLGA Niedersachsen: https://www.umwelt-online.de/recht/anlasi/sicher/nds/rettschutz22.htm
- BetrVG § 87: https://www.gesetze-im-internet.de/betrvg/__87.html
- BGG § 12a (gilt für öffentliche Stellen, z. B. kommunale Träger; private Hilfsorganisationen sind bei einem internen Werkzeug nicht verpflichtet): https://www.gesetze-im-internet.de/bgg/__12a.html
- HinSchG § 12: https://www.gesetze-im-internet.de/hinschg/__12.html

Die Hinweise auf Vorschriften sind eine technische Vorprüfung, keine Rechtsberatung.
