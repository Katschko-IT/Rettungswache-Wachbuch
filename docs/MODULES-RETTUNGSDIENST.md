# Rettungsdienst-Fachmodule & Automatisierungs-Architektur (v0.24.0)

Dieses Dokument beschreibt die Architektur, Datenmodelle, gesetzlichen Normen und Automatisierungsfunktionen der fünf Rettungsdienst-Fachmodule im Wachbuch sowie die Wachenzentrale („Mehr“-Menü).

---

## 1. Modul-Übersicht

```
+---------------------------------------------------------------------------------+
|                                 WACHENZENTRALE                                  |
+---------------------------------------------------------------------------------+
        |                        |                    |                |
        v                        v                    v                v
 🚑 FUHRPARK & HYGIENE     📦 LAGER & APOTHEKE     🩺 MPG & GERÄTE   🏢 ORGANISATION
  - Verfügbarkeit           - FEFO-Verfallsdatum    - MPBetreibV      - SOP-Lenkung
  - O2 / Tank / AdBlue      - Kühlkette (2–8 °C)    - STK/MTK Frist   - SHA-256 Hash
  - VAH-Desinfektion        - Mindestbestand-Task   - QR-Ingest       - Lesequittung
  - Auto-Sperrtimer         - 1-Scan Aufrüstung     - Einweisung      - Notruf-Kurzwahl
        |                        |                    |                |
        +------------------------+--------------------+----------------+
                                 |
                                 v
                        🖥️ WACHEN-DISPLAY
                         - Live-BOS Flotte
                         - Wetter & Ticker
                         - Fristenwarnungen
```

---

## 2. Die fünf Fachmodule im Detail

### 🚑 Fuhrpark & Hygiene (`/fuhrpark/`)
- **Fahrzeugzustand (fünf Zustände)**: Einsatzbereit, Eingeschränkt, Desinfektion, Werkstatt und Außer Dienst. „Eingeschränkt“ heißt: fahrbereit mit einer Einschränkung; der Grund wird als Mangel gemeldet (nach dem Setzen öffnet sich die Mangelmeldung), nicht als Freitext am Zustand. „Eingeschränkt“ zählt weder als „Einsatzbereit“ noch als „nicht einsatzbereit“, sondern hat eine eigene Kennzahl, einen eigenen Filter und eine eigene Karte in der Übersicht. Während der Einwirkzeit sind „Einsatzbereit“ und „Eingeschränkt“ gesperrt; „Desinfektion“ setzt nur das Desinfektionsprotokoll. Gespeichert werden seit 0.27 neutrale Werte (`ready`, `limited`, `disinfection`, `workshop`, `out_of_service`) – keine FMS-Codes; Migration 0069 hat die alten Codes umgestellt (1–4 → Einsatzbereit, 6 → Außer Dienst). Einsatzphasen (frühere Status 2/3/4) gibt es seit 0.26.1 nicht mehr (AGENTS.md § 1). Den Zustand eines vorhandenen Fahrzeugs ändert nur das Fahrzeug-Cockpit (mit Desinfektionssperre und Audit), nicht das Bearbeiten-Formular. Statusbemerkung, Display, Sperrbildschirm und App nennen während der Einwirkzeit nur „Desinfektion bis HH:MM Uhr“ – die Stufe steht ausschließlich im Protokoll.
- **Fahrzeug-Telemetrie**:
  - `fuel_level_percent`: Kraftstoffstand in Prozent (Warnung < 50%, Kritisch < 30%).
  - `adblue_level_percent`: AdBlue-Füllstand in Prozent (Warnung < 25%).
  - `o2_pressure_bar`: Flaschendruck in bar (Norm: 200 bar Bezugsskala; Warnung < 100 bar, Kritisch < 50 bar).
  - `current_mileage`: Kilometerstand in km.
- **Express-Schichtübernahme (3 Min.)**: Dokumentation von Füllständen, Sauberkeit, Gerätevollständigkeit und BtM-Siegelzustand – ohne Vorauswahl: Jeder Prüfpunkt wird aktiv mit Ja oder Nein beantwortet, der km-Stand startet leer („zuletzt … km“, nicht darunter und höchstens 2.000 km darüber; die erste Übernahme eines Fahrzeugs hat noch keine Grenze), Kraftstoff und AdBlue werden per Schnellwahl gewählt. Ein „Nein“ führt nach dem Speichern zur vorausgefüllten Mangelmeldung.
- **VAH-Desinfektionsmanagement**:
  - Dokumentation nach VAH-Vorgaben mit Einwirkzeit in Minuten.
  - **Stufen statt Erregerarten (seit 0.27)**: Jedes Protokoll nennt eine Stufe aus dem Desinfektionsplan der Wache (`DisinfectionLevel`: Stufe → Mittel → Freigaberegel „Nach Antrocknen“ oder „Nach Einwirkzeit“, mit Bestätigung). Standardstufen, benannt nach Umfang bzw. Wirkbereich: Routine-Wischdesinfektion, Schlussdesinfektion (begrenzt viruzid/bakterizid), Schlussdesinfektion (viruzid), Schlussdesinfektion (sporizid), Grunddesinfektion. Migration 0069 hat die früheren Arten verlustfrei zugeordnet (Routine, MRSA, Noro, C. diff, Grund – in dieser Reihenfolge). Stufennamen mit Erregernamen lehnt das Modell ab (kleine Sperrliste, keine vollständige Prüfung). Bis der Plan bestätigt ist (Paket C2), gilt das bisherige Verhalten: Mittel, Einwirkzeit und „Sperrtimer aktivieren“ stehen im Formular; die Freigaberegel der Stufe wirkt noch nicht. Die Stufe ist Pflicht und ohne Vorauswahl.
  - **Wer sieht die Stufe?** Stufe, Einwirkzeit und Bemerkung eines Protokolls sehen nur die durchführende Person, Schichtleitung und Admin (bis zum Funktionsmodell 0.28). Alle anderen sehen „Desinfektion“ mit Datum, Mittel und Person. Die Übersichtstabelle im Fuhrpark zeigt für alle nur Datum, Fahrzeug, Mittel und Person; Display, Sperrbildschirm, Terminal, CSV und App-API nennen nie eine Stufe.
  - **Keine automatische Freigabe**: Nach Ablauf der Einwirkzeit bleibt das Fahrzeug auf „Desinfektion“. Die Besatzung (Schichtübernahme der letzten 24 h plus die desinfizierende Person) wird benachrichtigt – im Posteingang, per Web-Push und in der App – und setzt den Status nach Prüfung selbst (`core/crew_notifications.py`, Dienst `notify-worker`, Audit `fleet.status_changed`). Details: `docs/PUSH-RELAY.md`.
- **Gesetzliche Fristen**:
  - Hauptuntersuchung gem. § 29 StVZO.
  - UVV-Prüfung gem. DGUV Vorschrift 70.
  - 10g-Tragentischprüfung gem. DIN EN 1789.
- **Außer Betrieb nehmen statt löschen** (seit 0.27, `core/evidence.py`):
  - Schichtleitung und Admin nehmen ein Fahrzeug auf der Fahrzeugseite außer Betrieb. Es
    verschwindet aus Übersicht, Display und Sperrbildschirm und nimmt keine Übernahme,
    Desinfektion, Statusänderung oder Mangelmeldung mehr an; Übernahmen und Desinfektionen
    bleiben sichtbar. „Wieder in Betrieb nehmen“ setzt es auf „Außer Dienst“, bis die
    Besatzung es einsatzbereit meldet. Liste: `/fuhrpark/ausser-betrieb/`; Audit
    `fleet.vehicle_retired` / `fleet.vehicle_reactivated`; CSV-Spalte „In Betrieb“.
  - Desinfektionsmittel werden im Django-Admin über „In Gebrauch“ aus dem Protokoll
    genommen, nicht gelöscht. Mindestens ein Mittel der Wache bleibt in Gebrauch.

### 📦 Lager & Material (`/lager/`)
- **FEFO-Prinzip (First-Expired-First-Out)**: Chargen mit dem kürzesten Verfallsdatum werden automatisch priorisiert vorgeschlagen.
- **Dynamische Kühlketten-Überwachung (2–8 °C)**:
  - Kühlpflichtige Notfallmedikamente (z. B. Rocuronium 10 mg/ml) besitzen ein herstellerseitiges MHD bei 2–8 °C.
  - Bei Entnahme auf das Fahrzeug wird das Out-of-Fridge Datum erfasst; das System berechnet dynamisch das verkürzte MHD bei Raumtemperatur (z. B. max. 84 Tage = 12 Wochen).
- **Automatischer Nachbestellschein (`/lager/nachbestellung/`)**:
  - Ermittelt alle Artikel unterhalb des Mindestbestands (`min_stock`) und kalkuliert den Bedarf bis zum Sollbestand (`target_stock`).
  - Export als Apotheken-Bestellschein (CSV mit PZN, Bezeichnung, Menge, Einheit).
  - 1-Klick-Übergabe als synchronisierte Tagesaufgabe in das Wachbuch.
- **1-Scan Express-Umlagerung**:
  - Direkte Buchung von Artikeln aus dem Zentrallager auf ein Zielfahrzeug per Scan der PZN, GTIN oder Lot-Nummer.
- **BfArM-Rückruf-Filter**:
  - Sofortige Quarantäne und Sperrung betroffener Chargen im gesamten Bestand.

### 🩺 MPG & Medizingeräte (`/mpg/`)
- **Medizinproduktebuch (§ 13 MPBetreibV)**:
  - Stammdaten mit UDI-DI (GTIN), Seriennummer, Inventarnummer, CE-Kennnummer und Hersteller.
  - Klassifizierung nach Risikoklassen (I, IIa, IIb, III gem. MDR) und Kennzeichnung aktiver Medizinprodukte (Anlage 1 & Anlage 2 MPBetreibV).
- **Prüffristen & Ampellogik**:
  - STK (Sicherheitstechnische Kontrolle gem. § 12 MPBetreibV) max. alle 24 Monate.
  - MTK (Messtechnische Kontrolle gem. § 15 MPBetreibV).
  - Ampel: Rot (<= 30 Tage / abgelaufen), Gelb (31–60 Tage), Grün (> 60 Tage).
- **Funktionskontrolle**:
  - Die prüfende Person beantwortet Energieversorgung, Sichtprüfung und Selbsttest einzeln mit
    Ja oder Nein. Nichts ist vorausgewählt; ohne Antwort auf jeden Punkt wird nichts gespeichert.
    Ein „Nein“ heißt nicht bestanden.
  - Die Schnellkontrolle „Alles in Ordnung – Funktion geprüft“ trägt alle drei Punkte als „Ja“
    ein und fragt vorher ausdrücklich nach.
  - Ein Selbsttest-Ausdruck oder gescannter Gerätecode kann als Notiz angehängt werden. Er wird
    **nicht** ausgewertet: Herstellerformate sind nicht dokumentiert, eine Heuristik würde
    Kontrollen falsch als bestanden eintragen.
- **Sperre und Freigabe** (`core/device_status.py`):
  - „Mangel melden“ und eine nicht bestandene Kontrolle sperren das Gerät und legen einen mit
    dem Gerät verknüpften Mangel an.
  - Eine bestandene Kontrolle hebt keine Sperre auf. Freigeben darf nur Schichtleitung oder
    Admin, erst wenn alle verknüpften Mängel erledigt sind; die Freigabe wird als
    Funktionskontrolle dokumentiert (Audit `mpg.device_released`).
  - Das Medizinproduktebuch ist führend. Ein gleichnamiges Gerät unter „Geräte & Fahrzeuge“
    zeigt denselben Status; dort kann ein gesperrtes Gerät nicht vorbei an offenen Mängeln
    freigegeben werden (Web und API, HTTP 409).
- **Digitale Einweisungsmatrix (§ 11 MPBetreibV)**:
  - Dokumentation von Geräte-Erst- und Wiederholungseinweisungen inklusive Gruppenschulungen.
- **Nachweise und Außerbetriebnahme** (seit 0.27, `core/evidence.py`):
  - Prüfungen (STK/MTK/DGUV) und Funktionskontrollen sind append-only; eine Korrektur ist ein
    neuer Eintrag. Kein Nachweis verschwindet, wenn ein Gerät gelöscht werden soll (PROTECT).
  - Schichtleitung und Admin nehmen ein Gerät dauerhaft außer Betrieb („Außer Betrieb
    nehmen“ auf der Geräteseite, mit Datum „Außerbetriebnahme“ und Audit `mpg.device_retired`).
    Es verschwindet aus Übersicht, Gerätepass und Display und nimmt keine Kontrolle, Prüfung,
    Einweisung, Mangelmeldung oder Freigabe mehr an. Das Bearbeiten-Formular bietet diesen
    Status nicht an.
  - „Wieder in Betrieb nehmen“ lässt das Gerät gesperrt, bis die Schichtleitung es mit einer
    dokumentierten Funktionskontrolle freigibt. Liste: `/mpg/ausser-betrieb/`; das
    Bestandsverzeichnis (CSV) hat die Spalte „Außerbetriebnahme“.
  - Ein gesperrtes oder außer Betrieb genommenes Gerät lässt sich unter „Geräte & Fahrzeuge“
    nicht freigeben (Web und API, HTTP 409); das geht nur im Medizinproduktebuch.

### 🏢 Organisation & Desk (`/orga/`)
- **QM-Dokumentenlenkung**:
  - Kategorien: Dienstanweisungen (`DAA`), Hygienepläne (`HYG`), Medizinische SOPs (`MED`), Geräteanweisungen (`TECH`), Qualitätsmanagement (`QM`), Arbeitssicherheit (`SAFETY`).
  - Formatierte Versionsnummern (`vX.Y`) mit Revisionshistorie.
  - **Integritätsnachweis**: SHA-256 Prüfsumme über den Dokumenteninhalt zur Manipulationssicherheit gem. GoBD und ISO 27001.
- **Persönliche Lesequittierung**:
  - Mitarbeiter quittieren wichtige Anweisungen mit Zeitstempel. Gespeichert werden Person,
    Version und Zeitpunkt; IP-Adresse und Browser nicht (seit 0.26.1). Ältere Einträge mit
    diesen Angaben bleiben unverändert, werden aber weder angezeigt noch exportiert.
  - Wachenleitung sieht in Echtzeit die Quittierungsquote je Dokument.
  - Wer wann quittiert hat (Liste und CSV-Nachweis), sehen seit 0.26.1 nur Schichtleitung und Admin; Mitglieder sehen ihren eigenen Stand.
- **Außer Kraft statt löschen** (seit 0.27):
  - Dienstanweisungen werden nicht gelöscht. Der Status „Außer Kraft“ nimmt sie aus der
    Pflichtlektüre; neue Quittierungen gibt es dann nicht. Versionen sind append-only,
    Versionen und Quittierungen bleiben als Nachweis erhalten. Jeder Statuswechsel steht im
    Audit (`orga.sop_status_changed`).
- **Notfall-Kurzwahlliste**:
  - Wichtige Ansprechpartner (ILS, Leitender Notarzt, Giftnotruf, Desinfektor, Werkstatt) mit 1-Tap Click-to-Call.

### 🖥️ Wachen-Display (`/display/`)
- **Optimiert für Wandmonitore und Smart-TVs**:
  - Vollbilddarstellung ohne Tastatur-/Mausinteraktion.
  - Live-Uhrzeit, Wachenname und aktuelles Wetter.
  - Heutige Wachentermine und offene Tagesaufgaben mit Fortschrittsbalken.
  - Fahrzeugzustand aller Fahrzeuge der Wache (einsatzbereit, eingeschränkt, Desinfektion, Werkstatt, außer Dienst) – ohne Einsatzphasen und ohne Stufe der Desinfektion.
  - MPG-Prüfungs- und Mängelwarnungen.
  - Verkehrslage und MoWaS-Warnungen (sofern konfiguriert).

---

## 3. Wachenzentrale („Mehr“-Menü)

Die Seite `/mehr/` („Alle Bereiche“) zeigt alle für die Rolle erreichbaren Module in vier Gruppen; deaktivierte Module erscheinen nicht. Auditoren sehen nur Konto- und Audit-Bereiche.

1. **🚑 Fachmodule**: Medizingeräte, Lager & Material, Fuhrpark, Organisation, Wachen-Display.
2. **📋 Wachbetrieb & Alltagsorganisation**: Mängel, Geräte & Pool, Tagesaufgaben, Auswertung, Checklisten, Prüfintervalle, Kalender, Pinnwand, Kaffeekasse, Geburtstage.
3. **📢 Kommunikation & Wissen**: Neuigkeiten, Wachen-Wiki, Meldungen & Verkehr, Wachenchat (Signal-Gruppe).
4. **⚙️ Wachenverwaltung & Sicherheit**: Mein Konto, App-Tokens / API, Display-Tokens, Team & Rollen, Einladungen, Darstellung & Leiste, Wacheneinstellungen, Audit-Log, Zwei-Faktor / Passkeys, Push-Mitteilungen, Technische Verwaltung.

**Features**:
- **Live-Schnellsuche**: Sofortige Filterung aller Karten bei Eingabe eines Suchbegriffs (z. B. "O2", "SOP", "Mangel", "Reifen").
- **Leisten-Synchronisation**: Module, die bereits in der oberen Kopfleiste angepinnt sind, tragen den Status-Badge `In Leiste`.
- **Individuelle Leisten-Anpassung**: Über `/einstellungen/darstellung/` kann der Master-Admin per Drag-and-Drop festlegen, welche Module direkt in der Leiste verankert sind.


---

## 4. Änderungen in 0.24.0 (Review 2026-10-22)

- Alle Modulseiten arbeiten unter der Content-Security-Policy: Verhalten über
  `data-*`-Attribute in `core/static/core/ui.js`, Gestaltung in `modules.css`.
- Kamera-Scanner leiten nur auf Adressen derselben Origin; die Kamera ist nur auf
  MPG-, Lager- und Fuhrpark-Übersicht erlaubt.
- Die Orga-Seite legt **keine** Muster-SOPs oder Notrufnummern mehr an. Der
  Fuhrpark legt höchstens ein neutrales Desinfektionsmittel an (im Django-Admin
  unter „Desinfektionsmittel“ pflegbar), dazu die fünf Standardstufen
  (unbestätigt, bisheriges Verhalten), und erfindet keine Kennzeichen.
- Die Übersicht (`/uebersicht/`) zeigt den Handlungsbedarf der aktiven
  Fachmodule (`core/module_overview.py`) und persönliche Hinweise („Für dich“).
- Fahrzeuge werden nach der Einwirkzeit **nicht** automatisch freigegeben; die
  Besatzung wird benachrichtigt und gibt selbst frei.
- Medizingeräte: Die QR-„Auswertung“ von Selbsttests trug Kontrollen als
  bestanden ein, sobald der Text z. B. „OK“ oder „CP3“ enthielt, und eine
  Ein-Klick-Kontrolle hob Sperren trotz offener Mängel auf. Beides entfernt;
  Sperre und Freigabe siehe oben. Paragrafenangaben auf die geltende
  MPBetreibV (§ 11 Einweisung, § 12 STK, § 13 Medizinproduktebuch,
  § 14 Bestandsverzeichnis, § 15 MTK) vereinheitlicht.
- Demo-Daten (`load_demo_data`) enthalten Fahrzeuge, Medizingeräte, Material und
  eine Dienstanweisung (`core/demo_modules.py`).
