# Marktvergleich: Wachwerk und RETTpro

Stand 24.10.2026. Grundlage für RETTpro sind ausschließlich die öffentlichen Seiten von
rettpro.de (deutsch und englisch, abgerufen am 24.10.2026; Quellen am Ende). Was dort
nicht steht, ist als „nicht genannt“ markiert – es kann im Produkt trotzdem existieren.
Für Wachwerk gilt der Stand dieses Repositorys (Branch der Gesamtreview 2026-10-24,
siehe [`REVIEW-2026-10-24.md`](REVIEW-2026-10-24.md)).

## 1. Steckbrief

| | RETTpro (EN: „Emergency Digital PRO“) | Wachwerk |
| --- | --- | --- |
| Anbieter | SEMAsystems GmbH, Schönberg (Bayern); Software seit 2012 | Open-Source-Projekt (AGPL-3.0), selbst betrieben |
| Verbreitung | laut Firmenchronik 2022: über 150 Organisationen, rund 15.000 aktive Nutzer (DRK, JUH, ASB, Feuerwehren, Bundeswehr) | Vorproduktion, keine Produktionsfreigabe |
| Betrieb | Cloud: „Our software operates online“; Serverstandort der Anwendung nicht genannt | eigener Server, Mini-PC, Raspberry Pi oder Mac; Installation mit einem Befehl (Docker), läuft im Wachennetz ohne Internet |
| Preis (Liste, zzgl. MwSt.) | RETTpro ab 190 €/Monat, LAGERpro ab 109 €, MPGpro ab 99 €, jeweils zzgl. 0,40 € je Nutzer; SSO 1.500 € einmalig + 25 €/Monat; RFID-Beispiel 3.725 € + 204,50 €/Jahr | Software kostenlos; einmalig Hardware (grob 300–450 € für Pi, SSD, Touch-Monitor) und eigene Betreuung |
| Endgeräte | jedes internetfähige Gerät per Browser; native App nicht genannt | Browser/PWA, quelloffene App für iOS und Android, Touch-Wachenterminal, Wachen-Display |
| Updates | durch den Anbieter (Cloud) | `wachbuch update` oder nächtlich automatisch mit Backup und Rollback; Images wöchentlich mit Sicherheitsupdates neu gebaut |
| Support | Telefon, E-Mail, Ticketsystem in der Software, Webinare, Demo | GitHub, eigene Betreuung |

## 2. Funktionsvergleich

Legende: ● vorhanden · ◐ teilweise · – nicht vorhanden / nicht genannt

| Bereich | RETTpro | Wachwerk | Anmerkung |
| --- | :-: | :-: | --- |
| Wachbuch / Übergaben | ● | ● | Wachwerk: Priorität, Revisionen, Quittierung je Person, Anhänge |
| Dashboard / Information | ● | ● | Wachwerk: Übersicht zeigt zuerst den Handlungsbedarf aller Module |
| Mängelmeldung | ● | ● | Wachwerk: offener Mangel sperrt Fahrzeug/Gerät, Freigabe nur durch Leitung |
| Fahrzeuge, Fristen (HU/UVV/Wartung) | ● | ● | Wachwerk zusätzlich Status 1–6 und Schichtübernahme |
| Desinfektion | ● | ● | Wachwerk: Einwirkzeit-Sperre, Besatzung wird benachrichtigt |
| Medizinprodukte (STK/MTK, Einweisungen) | ● | ● | beide; Wachwerk mit QR-Kontrolle am Gerät |
| Lager / Material, Mindestbestand, Bestellvorschlag | ● | ● | Wachwerk: Chargen, Verfall (FEFO), Rückruf |
| Barcode-Scan | ● | ● | |
| Checklisten | ● | ● | Wachwerk mit Prüfintervallen |
| Kalender (ICS), Aufgaben | ● | ● | Wachwerk: Tages-/Wochenaufgaben, Feiertage, ICS-Abo |
| Dokumente mit Lesebestätigung | ● | ● | Wachwerk: Dienstanweisungen mit Revisionen |
| Telefonbuch | ● | ● | |
| Interne Kommunikation | ◐ | ● | RETTpro: E-Mail-Client; Wachwerk: Chat, Gruppen, verschlüsselte Post |
| Schlüsselverwaltung | ● | ◐ | Wachwerk: als Inventar mit Ausgabe/Rückgabe, ohne Immobilienbezug |
| Ressourcen reservieren | ● | – | |
| Temperaturkontrolle | ● | ◐ | Wachwerk: per Checkliste, kein Logger |
| Digitalfunkgeräte | ● | ◐ | Wachwerk: als Gerät erfassbar, ohne Funk-Spezifika |
| QM-Modul (Fehlermeldungen, Zuständigkeiten) | ● | ◐ | Wachwerk: Mängel mit Zuständigkeit und Auswertung |
| **Dienstplan, Tausch, Urlaub** | ● | – | bewusst nicht im Produkt (Produktgrenze), Anbindung denkbar |
| **Mitarbeiterakte, Impfstatus** | ● | – | Gesundheitsdaten – bewusst nicht im Produkt |
| **Fortbildungen** | ● | – | |
| **Führerscheinkontrolle** (auch NFC) | ● | – | |
| **CIRS** (anonym) | ● | – | |
| **Verbandbuch** | ● | – | Gesundheitsdaten – Produktgrenze prüfen |
| Umfragen, E-Learning | ● | – | |
| Arbeitszeiterfassung | ● | – | |
| Kleidungsverwaltung | ● | – | |
| Fahrtenbuch | ● | – | |
| Einsatz-/Spitzenabdeckung | ● | – | Einsatzdaten – Produktgrenze |
| Schnittstellen (SSO, RFID, WEINMANN, Mercedes-Benz, meetB) | ● | ◐ | Wachwerk: offene, versionierte API; keine Hersteller-Anbindungen |
| Mehrere Standorte eines Trägers | ● | ◐ | Wachwerk: eine Wache je Installation |
| **Betrieb ohne Internet** | nicht genannt | ● | durch Tests mit blockierten externen Aufrufen belegt |
| **Selbst gehostet, Daten beim Träger** | – | ● | |
| **Installation mit einem Befehl, Auto-Update mit Rollback** | – (Cloud) | ● | |
| **Native App (iOS/Android)** | nicht genannt | ● | quelloffen, mit Push und verschlüsseltem Lesecache |
| **Zwei-Faktor, Passkeys, QR-Login** | nicht genannt | ● | RETTpro nennt nur SSO (Zusatzmodul) |
| **Touch-Wachenterminal mit Wachen-Code** | nicht genannt | ● | Sperrbildschirm, Bildschirmtastatur, WLAN-QR |
| **Wachen-Display (Monitor)** | nicht genannt | ● | Fahrzeugstatus, Wetter, Termine, Verkehr |
| **Tag- und Nachtansicht** | nicht genannt | ● | Nachtdienst-Modus, auf Lesbarkeit ausgelegte Schrift |
| Audit-Log, Löschfristen | nicht genannt | ● | |
| Wetter, Müllkalender, Geburtstage, Kaffeekasse | – | ● | Komfort für den Wachalltag |

## 3. Wie weit Wachwerk ist – in Zahlen

Gezählt aus der Tabelle oben (● = 1, ◐ = ½):

| Blick | Ergebnis |
| --- | --- |
| RETTpro-Funktionen insgesamt (● oder ◐ bei RETTpro) | 31 Bereiche |
| davon in Wachwerk vorhanden | 13 vollständig, 6 teilweise → **16 von 31 (52 %)** |
| davon ohne die bewusst ausgeschlossenen Bereiche (Dienstplan, Mitarbeiterakte, Verbandbuch, Einsatzabdeckung, Arbeitszeit) | **16 von 26 (62 %)** |
| **Kernbetrieb einer Wache** (Wachbuch, Dashboard, Mängel, Fahrzeuge, Desinfektion, Medizinprodukte, Lager, Barcode, Checklisten, Kalender, Dokumente, Telefonbuch) | **12 von 12 (100 %)** |
| Bereiche, die nur Wachwerk bietet bzw. RETTpro nicht nennt | 10 |

Lesart: Im Wachalltag ist Wachwerk gleichauf und in Betrieb, Sicherheit und Bedienung
an der Wache voraus. Die Lücke liegt in der Personal- und Verwaltungsseite (Dienstplan,
Fortbildung, Führerscheine, CIRS, QM) und bei Integrationen – teils bewusst, weil diese
Bereiche Gesundheits- oder Einsatzdaten berühren, die die Produktgrenze ausschließt.

## 4. Was RETTpro besser macht

1. **Personal und Verwaltung**: Dienstplan, Mitarbeiterakte, Fortbildungen,
   Führerscheinkontrolle, Arbeitszeit – die Arbeit der Wachleitung und Verwaltung.
2. **Qualitätsmanagement**: CIRS, QM-Meldungen, Verbandbuch, Umfragen und E-Learning.
3. **Reife und Vertrauen**: seit 2012 am Markt, lange Referenzliste, Ansprechpartner,
   Datenübernahme beim Wechsel aus einem Altsystem.
4. **Integrationen**: SSO zu Dienstplanprogrammen, RFID-Gerätecheck mit Handscanner,
   Hersteller-, Fahrzeug- und Lieferantenanbindung.
5. **Mehrere Standorte** eines Trägers in einem System, ohne eigene IT.

## 5. Wo Wachwerk besser ist

1. **Läuft in der Wache, auch ohne Internet**: eigener Server oder Pi im Wachennetz;
   fällt das Internet aus, arbeitet die Wache weiter.
2. **Daten bleiben beim Träger**: selbst gehostet, quelloffen, keine Nutzerlizenzen,
   kein Auftragsverarbeiter, keine Analyse- oder Marketing-Dienste im Produkt.
3. **Kosten**: keine laufenden Lizenzkosten (Rechenbeispiel unten).
4. **Sicherheit, nachprüfbar**: Zwei-Faktor und Passkeys (MFA-Pflicht durchsetzbar),
   QR-Login, Audit-Log, verschlüsselte Post, Löschfristen; Quellcode und
   Review-Berichte sind öffentlich.
5. **Sicherheitslogik im Fachablauf**: Mängel und Einwirkzeiten sperren Fahrzeuge und
   Geräte; Freigabe nur bewusst durch Menschen.
6. **Bedienung**: Übersicht mit Handlungsbedarf zuerst, Nachtdienst-Modus,
   Touch-Terminal mit Wachen-Code, Wachen-Display, native App.
7. **Betrieb ohne IT-Abteilung**: Installation mit einem Befehl, nächtliche Updates
   mit Backup und automatischem Rollback, wöchentlich neu gebaute Images.

### Rechenbeispiel Kosten (Listenpreise, ohne MwSt.)

Wache mit 30 Nutzern, RETTpro mit LAGERpro und MPGpro, drei Jahre:

| | RETTpro | Wachwerk |
| --- | --: | --: |
| Monatlich | 190 + 109 + 99 € + 3 × 30 × 0,40 € = **434 €** | 0 € |
| Drei Jahre | **15.624 €** (ohne SSO/RFID) | einmalig ~300–450 € Hardware + eigene Betreuung |

Die eigene Betreuung (Updates prüfen, Backups sichern, Ansprechpartner vor Ort) ist bei
Wachwerk der eigentliche Kostenfaktor und muss ehrlich eingeplant werden.

## 6. Nächste Schritte (nach Nutzen und Aufwand)

| Priorität | Vorhaben | Aufwand | Warum |
| --- | --- | --- | --- |
| 1 | **Produktionsfreigabe**: externe Abnahmen (R-015 bis R-019), Release 0.25.0, Pilotwache | mittel | ohne Freigabe kein Echtbetrieb |
| 2 | **CIRS + QM-Meldungen**: anonyme Meldung ohne Benutzerbezug, Kategorien, Zuständige, Status | klein | baut auf Mängeln auf; großer Nutzen für QM |
| 3 | **Fortbildungsnachweise und Führerscheinkontrolle**: Stunden, Nachweis, Kontrolltermine mit Erinnerung | mittel | häufige Prüffragen der Wachleitung |
| 4 | **Temperaturkontrolle** Medikamentenkühlschrank: Vorlage, Grenzwerte, Hinweis in der Übersicht | klein | Arzneimittellagerung |
| 5 | **Mehrere Wachen eines Trägers**: Träger-Ansicht, wachenübergreifende Auswertung | groß | Voraussetzung für Kreisverbände |
| 6 | **SSO (OpenID Connect)** | mittel | Erwartung größerer Träger; bei RETTpro kostenpflichtiges Zusatzmodul |
| 7 | **Dienstplan-Anbindung** (Import ICS/CSV, „wer ist heute im Dienst“) statt eigenem Planer | mittel | Benachrichtigungen an die diensthabende Besatzung |
| 8 | **Ressourcen reservieren** und **Fahrtenbuch** | klein | einfache Ergänzungen zu Fuhrpark und Inventar |

Bewusst nicht empfohlen: Mitarbeiterakte mit Impfstatus, Verbandbuch und
Einsatzabdeckung (Gesundheits- und Einsatzdaten, Produktgrenze), eigene
Arbeitszeiterfassung und Kleidungsverwaltung (eigene Fachgebiete mit Tarif- und
Mitbestimmungsfragen – besser über Schnittstellen).

## 7. Quellen (abgerufen am 24.10.2026)

- https://www.rettpro.de/en/
- https://www.rettpro.de/en/rettpro/emergency-medical-services-software-features/
- https://www.rettpro.de/en/emergency-medical-services-software/
- https://www.rettpro.de/en/emergency-medical-services-software-additional-modules/
- https://www.rettpro.de/en/ambulance-service-software-prices-packages/
- https://www.rettpro.de/en/emergency-services-software-customers/
- https://www.rettpro.de/en/emergency-medical-services-software-company-semasystems/
- https://www.rettpro.de/en/elementor-4066/ (SSO)
- https://www.rettpro.de/en/rfid-device-check/ (RFID)
- https://www.rettpro.de/en/data-protection/
- deutsche Fassungen der Funktions-, Software-, Modul-, Preis- und Kundenseiten
