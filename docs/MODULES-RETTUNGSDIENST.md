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
  - BOS-Status 1–6          - FEFO-Verfallsdatum    - MPBetreibV      - SOP-Lenkung
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
- **Taktischer BOS-Status**: Status 1 (Frei Wache), 2 (Frei Funk), 3 (Anfahrt), 4 (Einsatzort), 5 (Sprechwunsch), 6 (Außer Dienst), sowie Spezialstatus `DISINFECTION` und `WORKSHOP`.
- **Fahrzeug-Telemetrie**:
  - `fuel_level_percent`: Kraftstoffstand in Prozent (Warnung < 50%, Kritisch < 30%).
  - `adblue_level_percent`: AdBlue-Füllstand in Prozent (Warnung < 25%).
  - `o2_pressure_bar`: Flaschendruck in bar (Norm: 200 bar Bezugsskala; Warnung < 100 bar, Kritisch < 50 bar).
  - `current_mileage`: Kilometerstand in km.
- **Express-Schichtübernahme (3 Min.)**: Schnelle Dokumentation von Füllständen, Sauberkeit, Gerätevollständigkeit und BtM-Siegelzustand.
- **VAH-Desinfektionsmanagement**:
  - Dokumentation nach VAH-Vorgaben mit Einwirkzeit in Minuten.
  - **Automatisierungs-Feature**: `Vehicle.check_and_release_disinfection()` hebt nach Ablauf der Einwirkzeit die Fahrzeugsperre automatisch auf und setzt das Fahrzeug zurück auf Status 1. Die Freigabe ist ein bedingtes Update mit genau einem Audit-Ereignis (`fleet.disinfection_auto_released`). Ob ein Fahrzeug ohne Bestätigung der Besatzung freigegeben werden soll, ist eine offene Fachentscheidung (siehe `docs/REVIEW-2026-10-22.md`).
- **Gesetzliche Fristen**:
  - Hauptuntersuchung gem. § 29 StVZO.
  - UVV-Prüfung gem. DGUV Vorschrift 70.
  - 10g-Tragentischprüfung gem. DIN EN 1789.

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
  - STK (Sicherheitstechnische Kontrolle gem. § 11 MPBetreibV) max. alle 24 Monate.
  - MTK (Messtechnische Kontrolle gem. § 14 MPBetreibV).
  - Ampel: Rot (<= 30 Tage / abgelaufen), Gelb (31–60 Tage), Grün (> 60 Tage).
- **QR-Code Selbsttest-Ingest**:
  - Scan des Ergebnis-Codes direkt vom Gerätedisplay (z. B. corpuls3 oder Weinmann MEDUMAT Transport).
  - Automatische Auswertung aller Baugruppen, Akkus und Defi-Energie (200 J) mit direkter Speicherung im Prüfprotokoll.
  - Automatische Sperre und Mängelticket-Erstellung bei Fehlermeldungen.
- **Digitale Einweisungsmatrix (§ 10 MPBetreibV)**:
  - Dokumentation von Geräte-Erst- und Wiederholungseinweisungen inklusive Gruppenschulungen.

### 🏢 Organisation & Desk (`/orga/`)
- **QM-Dokumentenlenkung**:
  - Kategorien: Dienstanweisungen (`DAA`), Hygienepläne (`HYG`), Medizinische SOPs (`MED`), Geräteanweisungen (`TECH`), Qualitätsmanagement (`QM`), Arbeitssicherheit (`SAFETY`).
  - Formatierte Versionsnummern (`vX.Y`) mit Revisionshistorie.
  - **Integritätsnachweis**: SHA-256 Prüfsumme über den Dokumenteninhalt zur Manipulationssicherheit gem. GoBD und ISO 27001.
- **Persönliche Lesequittierung**:
  - Mitarbeiter quittieren wichtige Anweisungen mit Zeitstempel.
  - Wachenleitung sieht in Echtzeit die Quittierungsquote je Dokument.
- **Notfall-Kurzwahlliste**:
  - Wichtige Ansprechpartner (ILS, Leitender Notarzt, Giftnotruf, Desinfektor, Werkstatt) mit 1-Tap Click-to-Call.

### 🖥️ Wachen-Display (`/display/`)
- **Optimiert für Wandmonitore und Smart-TVs**:
  - Vollbilddarstellung ohne Tastatur-/Mausinteraktion.
  - Live-Uhrzeit, Wachenname und aktuelles Wetter.
  - Heutige Wachentermine und offene Tagesaufgaben mit Fortschrittsbalken.
  - Taktischer Status aller Rettungsmittel der Wache in Echtzeit.
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
  unter „Desinfektionsmittel“ pflegbar) und erfindet keine Kennzeichen.
- Die Übersicht (`/uebersicht/`) zeigt den Handlungsbedarf der aktiven
  Fachmodule (`core/module_overview.py`).
- Demo-Daten (`load_demo_data`) enthalten Fahrzeuge, Medizingeräte, Material und
  eine Dienstanweisung (`core/demo_modules.py`).
