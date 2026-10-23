# Marktvergleich: Wachbuch und RETTpro

Stand 22.10.2026. Grundlage für RETTpro sind ausschließlich die öffentlichen Seiten von
rettpro.de (Startseite, Funktionen, Software, Zusatz-Module, Preise, Kunden, Unternehmen,
Impressum, Datenschutz). Was dort nicht steht, ist als „nicht genannt“ markiert – es kann
im Produkt trotzdem existieren. Für das Wachbuch gilt der Stand dieses Repositorys.

## 1. Steckbrief

| | RETTpro | Wachbuch |
| --- | --- | --- |
| Anbieter | SEMAsystems GmbH, Schönberg (Bayern); seit 2012 am Markt | Open-Source-Projekt (AGPL-3.0), selbst betrieben |
| Verbreitung | laut Website über 150 Organisationen, rund 15.000 Nutzer (DRK, JUH, ASB, MHD, Berufsfeuerwehren, Bundeswehr) | Pilotphase, keine Produktionsfreigabe |
| Betrieb | Cloud („Unsere Software arbeitet online“), Serverstandort nicht genannt | eigener Server oder Raspberry Pi auf der Wache, funktioniert ohne Internet |
| Preis | Gesamtpaket ab 190 €/Monat zzgl. 0,40 € je Nutzer und MwSt.; LAGERpro ab 109 €, MPGpro ab 99 € | Software kostenlos; einmalig Hardware (Pi 4, SSD, RTC, 14″-Touch-Monitor: grob 300–450 €) und eigene Betreuung |
| Endgeräte | Browser auf allen Geräten; eine native App ist nicht eindeutig genannt | Browser, Flutter-App für iOS/Android mit Offline-Lesecache, Touch-Terminal, Wachen-Display |
| Support | Telefon, E-Mail, Ticketsystem in der Software, Webinare | GitHub, eigene Betreuung |

## 2. Funktionsvergleich

Legende: ● vorhanden · ◐ teilweise · – nicht vorhanden / nicht genannt

| Bereich | RETTpro | Wachbuch | Anmerkung |
| --- | :-: | :-: | --- |
| Wachbuch / Übergaben | ● | ● | Wachbuch: dringende Übergaben, Lesebestätigung, Anhänge, Revisionen |
| Mängelmeldung | ● | ● | Wachbuch: Mangel sperrt Fahrzeug/Gerät, Freigabe nur durch Leitung |
| Fahrzeuge, Fristen (HU/UVV/Wartung) | ● | ● | Wachbuch zusätzlich BOS-Status und 3-Minuten-Schichtübernahme |
| Desinfektion nach Hygieneplan | ● | ● | Wachbuch: Einwirkzeit-Sperre, Besatzung wird benachrichtigt, keine Auto-Freigabe |
| Medizinprodukte (STK/MTK, Medizinproduktebuch, Einweisungen) | ● | ● | beide; Wachbuch mit QR-Kontrolle am Gerät |
| Lager / Material, Mindestbestand, Bestellvorschlag | ● | ● | Wachbuch: Chargen, Haltbarkeit (FEFO), Rückruf |
| Barcode-Scan | ● | ● | |
| Checklisten | ● | ● | Wachbuch mit Prüfintervallen |
| Kalender, Aufgaben | ● | ● | Wachbuch: Tages-/Wochen-/Monatsaufgaben, ICS-Abo |
| Dokumente mit Lesebestätigung | ● | ● | Wachbuch: Dienstanweisungen (SOP) mit Revisionen und Quittierung |
| Telefonbuch | ● | ● | |
| Interne Kommunikation | ◐ (E-Mail-Client) | ● | Wachbuch: Wachenchat, Gruppen, Ende-zu-Ende-verschlüsselte Post |
| Information/Dashboard | ● | ● | Wachbuch: Übersicht, Pinnwand, Neuigkeiten, Wiki |
| **Dienstplan, Diensttausch, Urlaub** | ● | – | größte Lücke |
| **Mitarbeiterakte** (Fortbildungsstunden, Nachweise, Impfstatus) | ● | – | |
| **Fortbildungen** (Anmeldung, Nachweis-Upload) | ● | – | |
| **Führerscheinkontrolle** (auch NFC-Siegel) | ● | – | |
| **CIRS** (anonym) | ● | – | |
| **QM-Modul** (Fehlermeldungen, Verbesserungsvorschläge, Zuständigkeiten) | ● | ◐ | Wachbuch hat nur Mängel und Auswertung |
| **Verbandbuch** | ● | – | |
| Umfragen, E-Learning (Multiple Choice) | ● | – | |
| Arbeitszeiterfassung (ARBEITSZEITpro) | ● | – | |
| Kleidungsverwaltung | ● | – | |
| Digitalfunkgeräte | ● | ◐ | Wachbuch: als „Geräte“ erfassbar, ohne Funk-Spezifika |
| Schlüsselverwaltung, Fahrtenbuch | ● | – | |
| Ressourcen reservieren | ● | – | |
| Temperaturkontrolle (Kühlschrank, optional Logger) | ● | ◐ | Wachbuch: nur per Checkliste |
| Einsatz-/Spitzenabdeckungs-Erfassung | ● | – | |
| Schnittstellen (SSO, RFID, WEINMANN Connect, Mercedes-Benz, Bestellung bei meetB) | ● | – | |
| **Touch-Terminal auf der Wache mit Wachen-Code** | – | ● | eigenes WLAN, Bildschirmtastatur, Sperrbildschirm-Dashboard |
| **Wachen-Display (Monitor)** | – | ● | Fahrzeugstatus, Wetter, Termine, Müll, Verkehr |
| **Offline-Betrieb ohne Internet** | – | ● | |
| **Native App mit Push und Offline-Cache** | nicht genannt | ● | |
| Zwei-Faktor, Passkeys, QR-Login | nicht genannt | ● | |
| Revisionssicheres Audit-Log, Löschfristen | nicht genannt | ● | |
| Mehrere Standorte / Träger-Ebene | ● | ◐ | Wachbuch: eine Wache je Installation |
| Wetter, Müllkalender, Geburtstage, Kaffeekasse | – | ● | Komfort für den Wachalltag |

## 3. Was RETTpro besser macht

1. **Personal- und Organisationsseite**: Dienstplan, Mitarbeiterakte, Fortbildungen,
   Führerscheinkontrolle, Arbeitszeit. Damit deckt RETTpro die Arbeit der Wachleitung
   und Verwaltung ab, nicht nur den Wachalltag.
2. **Qualitätsmanagement**: CIRS, QM-Meldungen mit Zuständigkeiten, Verbandbuch,
   Umfragen. Das wird bei Audits (z. B. QM-Zertifizierung des Trägers) erwartet.
3. **Reife und Vertrauen**: 14 Jahre am Markt, große Referenzliste, Support mit
   Ansprechpartner, Datenübernahme aus Altsystemen.
4. **Integrationen**: SSO, RFID-Gerätecheck, Hersteller- und Fahrzeugdaten, Shop-Anbindung.
5. **Mehrere Standorte** eines Trägers in einem System.

## 4. Was das Wachbuch besser macht

1. **Läuft auf der Wache, auch ohne Internet**: Pi mit eigenem WLAN, Touch-Terminal,
   Wachen-Display. Fällt das Internet aus, arbeitet die Wache weiter.
2. **Daten bleiben beim Träger**: selbst gehostet, offener Quellcode, keine
   Nutzerlizenzen, kein Auftragsverarbeiter.
3. **Sicherheit**: Zwei-Faktor, Passkeys, QR-Login, Audit-Log, Ende-zu-Ende-verschlüsselte
   Post, Löschfristen.
4. **Sicherheitslogik im Fachablauf**: Mängel und Einwirkzeiten sperren Fahrzeuge und
   Geräte; Freigabe nur bewusst durch Menschen, Besatzung wird benachrichtigt.
5. **Bedienung an der Wache**: Sperrbildschirm mit Tagesüberblick, Wachen-Code,
   Bildschirmtastatur, WLAN- und App-QR, native App mit Push.

## 5. Optimierungsbedarf (Vorschlag, nach Nutzen und Aufwand)

| Priorität | Vorhaben | Aufwand | Warum |
| --- | --- | --- | --- |
| 1 | **Produktionsreife**: Freigabe-Checkliste, Update- und Backup-Routine am Pi (USB-Stick automatisch), Wiederherstellungstest, Betriebshandbuch | mittel | Ohne Freigabe kein Echtbetrieb |
| 2 | **CIRS + QM-Meldungen**: anonyme Meldung (ohne Benutzerbezug gespeichert), Kategorien, Zuständige, Bearbeitungsstatus | klein | Baut auf „Mängel“ auf; hoher Nutzen für QM |
| 3 | **Verbandbuch** mit stark eingeschränkter Einsicht | klein | Pflichtdokumentation, einfach umzusetzen |
| 4 | **Fortbildungsnachweise und Führerscheinkontrolle**: Stunden je Jahr, Nachweis-Upload, Kontrolltermine mit Erinnerung | mittel | Häufige Prüffragen der Wachleitung |
| 5 | **Temperaturkontrolle Medikamentenkühlschrank**: Checklisten-Vorlage, Grenzwerte, Alarm; später Sensor | klein | Arzneimittellagerung |
| 6 | **Dienstplan-Anbindung**: Import (ICS/CSV) statt eigenem Planer; „Wer ist heute im Dienst“ für Benachrichtigungen | mittel | Dienstplan selbst zu bauen ist groß; Anbindung reicht für den Wachalltag |
| 7 | **Mehrere Wachen eines Trägers**: Träger-Ansicht, wachenübergreifende Auswertungen | groß | Voraussetzung für Kreisverbände |
| 8 | **Nachbestellung aus dem Lager** als PDF/E-Mail an Lieferanten | klein | Bestellvorschlag existiert schon |
| 9 | **SSO (OpenID Connect)** für Träger mit zentraler Benutzerverwaltung | mittel | Erwartung größerer Organisationen |
| 10 | **Umfragen und kurze Lernkontrollen** zu Dienstanweisungen | mittel | Ergänzt die Quittierung |

Nicht empfohlen: Arbeitszeiterfassung und Kleidungsverwaltung – eigene Fachgebiete mit
Tarif- und Mitbestimmungsfragen, besser über Schnittstellen.

## 6. Quellen

- https://www.rettpro.de/
- https://www.rettpro.de/rettpro/rettungsdienst-software-funktionen/
- https://www.rettpro.de/rettungsdienst-software/
- https://www.rettpro.de/rettungsdienst-software-zusatz-module/
- https://www.rettpro.de/rettungsdienst-software-preise-pakete/
- https://www.rettpro.de/rettungsdienst-software-kunden/
- https://www.rettpro.de/rettungsdienst-software-unternehmen-semasystems/
- https://www.rettpro.de/impressum/
