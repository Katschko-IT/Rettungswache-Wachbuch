# UX-Verbesserungsplan Wachwerk (Grundlage: UI/UX-Audit 0.26.0 und Muster aus dem Wettbewerb)

Aufwand: S bis 1 Tag · M 2–5 Tage · L mehr als 1 Woche.
Priorität: P0 Grenze, Compliance oder Fehlbedienung · P1 hoher Alltagsnutzen · P2 Feinschliff.
Grundlage sind Screenshots am Rechner (1440×900), Tablet (820×1180) und Handy (390×844) sowie von Sperrbildschirm und Wand-Display. Alle Punkte folgen [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md): Ziele mindestens 48 × 48 px, höchstens eine Primäraktion je Ansicht, Listen und Schreibformulare auf getrennten Seiten.

Jeder Punkt wird als eigener kleiner PR umgesetzt, mit Negativtest (AGENTS.md § 5), ohne Inline-Skripte und `style`-Attribute. Bei Layout-Änderungen kommt ein Screenshot-Test für die betroffenen Viewports dazu.

## Welle A – in 0.27 (vor dem Pilot), gesamt ca. 2,5 Wochen

| # | Änderung | Dateien | Aufwand |
|---|---|---|---|
| A1 (P0) | FMS-Status 1–4 entfernen, Überschrift „Fahrzeugzustand“, fünf neutrale Zustände ohne Ziffern (Einsatzbereit, Eingeschränkt, Desinfektion, Werkstatt, Außer Dienst); Display und Sperrbildschirm übernehmen die Begriffe (es gibt keine Fuhrpark-API) | `templates/core/fleet_vehicle_detail.html` Z. 48–93, `core/fleet_models.py` Z. 36, `templates/core/_display_surface.html`, `templates/core/terminal_home.html` | M |
| A2 (P0) | Fahrzeugübernahme: Ja/Nein ohne Vorauswahl, „Nein“ öffnet den Mangel; km-Feld leer mit Hinweis „zuletzt …“ und `inputmode="numeric"`; Füllstände als Schnellwahl ¼/½/¾/voll | `core/fleet_models.py` Z. 248–254, `core/fleet_forms.py` Z. 89–105, `fleet_vehicle_detail.html` Z. 167–205 | S |
| A3 (P0) | MPG-Liste: „Check“ heißt „Funktion geprüft“; Rückfrage (`data-confirm`); gesperrt mit Link „Einweisung fehlt“; 5 Minuten Storno als neuer Datensatz | `templates/core/mpg_dashboard.html` Z. 153–160, `mpg_device_detail.html` Z. 100–120, MPG-Views | S–M |
| A4 (P0) | Desinfektion: Bemerkungsfeld umbenennen, Hinweis „keine Patienten- oder Einsatzangaben“; Stufen statt Erregernamen | `core/fleet_models.py` Z. 202–217, Desinfektionsformular | S |
| A5 (P1) | Fokus nicht verdecken (WCAG 2.4.11): `scroll-padding-bottom` im Mobil-Breakpoint | `core/static/core/app.css` (ab Z. 228) | S |
| A6 (P1) | Tagesaufgaben: nach „Erledigt“ mit Anker `#aufgabe-<id>` zurück und `scroll-margin-top`; „Erledigt“-Knopf 48 × 48 px, Status nur bei erledigt | `templates/core/tasks_today.html`, `task_row.html`, Aufgaben-Views, `modules.css` | S |
| A7 (P1) | Sperrbildschirm 800×480: `@media (max-height:540px)`, Fahrzeug-Chips einzeilig mit „+N weitere“, Entsperren-Knopf unten fest; Viewport in den Kiosk-Test aufnehmen | `core/static/core/lockscreen.css`, `terminal_home.html` | S |
| A8 (P1) | Übergabe-Detail: „Gelesen – quittieren“ als einzige Primäraktion direkt unter der Information, am Handy fixiert; Status als Segment-Knöpfe; Metadaten einzeilig; Marker „neu für dich“; Badge zählt „ungelesen und dringend“ | `templates/core/handover_detail.html`, `handover_list.html`, `dashboard.html` Z. 60–70, `base.html` Z. 115 | S–M |
| A9 (P2) | 403-Seite bei Rollenmangel: nennt die zuständige Rolle und Person, Knopf „Zurück“ statt „Anmelden“ | `templates/errors/403.html` | S |
| A10 (P2) | Kontraste ≥ 4,5:1 (Demo-Rundgang, Kaffeemonate, Display-Hinweis), `<li>` statt `role="listitem"`, Ziele ≥ 48 × 48 px, Login-Knopf am Handy vollbreit, Demo-Banner nach Schritt 1 einzeilig | `demo.css`, `app.css`, `display.css`, `tasks_week.html`, `registration/login.html`, `_demo_tour.html` | S |
| A11 (P2) | DESIGN-SYSTEM.md nachziehen: Tokentabelle aus `tokens.css` erzeugen, Schrift, 5-Punkte-Navigation | `docs/DESIGN-SYSTEM.md`, `scripts/sync_design_assets.py` | S |

**CI:** axe-core-Lauf (Playwright) für die 43 Seiten hell und dunkel; Fehler mit der Schwere critical oder serious brechen den Build ab.

## Welle B – in 0.28 (mit „Prüfen und Nachweisen“), gesamt ca. 3,5 Wochen

| # | Änderung | Dateien | Aufwand |
|---|---|---|---|
| B1 (P1) | Wand-Display als festes 16:9-Raster:<br>- `height:100dvh; overflow:hidden`<br>- Dringendes in der Kopfzeile neben der Uhr<br>- Fahrzeuge über die volle Höhe<br>- Seitenwechsel statt Scrollen (`prefers-reduced-motion`)<br>- Bedienknöpfe nach 5 s ausblenden und über den Display-Link gar nicht zeigen<br>- Icons statt Emojis, Laufband in voller Breite<br>- Profile „Fahrzeughalle“ und „Aufenthaltsraum“ (Muster First Arriving, rescuetrack)<br>- Screenshot-Test für 1920×1080 und 1280×720 | `_display_surface.html`, `display.html` Z. 22–24, `display.css` Z. 365–400, `display.js`, `core/display.py` | M |
| B2 (P1) | Fahrzeugseite aufteilen: Status, Fristen und letzte Übernahme plus eine Primäraktion „Übernahme starten“; „Desinfektion erfassen“ und „Mangel melden mit Foto“ als sekundäre Aktionen, alle auf eigenen URLs; Übernahme als geführte Liste mit Fortschritt; Mangel über `/maengel/neu/?fahrzeug=<slug>` mit Foto, auch auf der MPG-Seite (Z. 335) | `fleet_vehicle_detail.html`, `core/fleet_views.py`, `core/urls.py`, `mpg_device_detail.html` | M |
| B3 (P1) | „Mangel in drei Tipps“ (Muster SafetyCulture/DIVERA):<br>- Knöpfe „Foto aufnehmen“ (`capture="environment"`) und „Datei wählen“<br>- Kategorie und Priorität als Segment-Chips, „Normal“ sichtbar vorgewählt<br>- einheitliche Feldreihenfolge<br>- „Bezug“ als Auswahl (Fahrzeug, Gerät, Raum), danach als Fremdschlüssel statt `asset_ref`-Freitext<br>- Hinweis „Bereits gemeldet: …“ bei offenem Mangel am selben Objekt | `templates/core/defect_form.html` Z. 19, `handover_form.html` Z. 21, `core/forms.py`, `core/wachalltag_models.py` Z. 72, `core/wachalltag_web.py` Z. 113 | S (Oberfläche), M (Fremdschlüssel) |
| B4 (P1) | Begriffe vereinheitlichen:<br>- Glossar in DESIGN-SYSTEM.md, ein Name je Modul für Kachel, h1, `<title>` und Leiste<br>- „Fahrzeuge“, „Geräte & Schlüssel“, „Dienstanweisungen & Telefonbuch“, „Füllstände“ statt „Telemetrie“, „Display-Links“ statt „Tokens“, kein „Cockpit“, „Desk“, „Asset“<br>- `ngettext` für Plurale, „seit 3 Tagen“ statt „3d“<br>- die 60 unübersetzten Meldungen der Fachmodule<br>- ein Test vergleicht Kachel, Titel und h1 | `templates/core/more.html`, `fleet_dashboard.html`, `orga_dashboard.html`, `assets_inventory.html`, `warehouse_dashboard.html`, `core/fleet_models.py` Z. 151–167, `core/coffee_views.py` Z. 199, `core/wachalltag_web.py`, `core/navigation.py` | M |
| B5 (P1) | Objektkarte als neues Template, gemeinsam für QR-Codes aller Objekte: Status, letzte Prüfung, nächste Frist, offene Mängel, eine Primäraktion und eine sekundäre; am Handy mit dem ersten Bildschirm nutzbar | neu `templates/core/object_card.html`, QR-Views | M |

## Welle C – in 0.29, gesamt ca. 3,5 Wochen

| # | Änderung | Dateien | Aufwand |
|---|---|---|---|
| C1 (P1) | Navigation:<br>- „Hilfe“ als „?“ in die Kopfzeile<br>- frei werdender Platz rollenabhängig (Fahrzeuge oder Aufgaben)<br>- „Mehr“ gegliedert: Zuletzt genutzt, Alltag, Information, Verwaltung (nur Admins); doppelte Kacheln entfernen<br>- Schnellaktion „+ Neu“ als Auswahlblatt (Übergabe, Mangel mit Foto, Fahrzeugübernahme, Entnahme, Zahlung)<br>- persönliches Anheften | `core/navigation.py` Z. 39–41, `templates/base.html` Z. 104–130, `templates/core/more.html`, `core/views.py` Z. 1112 | M |
| C2 (P2) | „Für dich“ auf der Übersicht, höchstens 4 Zeilen: ungelesene Übergaben und Neuigkeiten, mir zugewiesene Mängel, fällige Unterweisung oder Einweisung, Kaffeekasse offen; Karte „Seit deinem letzten Besuch“, nur für die Person selbst sichtbar | `templates/core/dashboard.html` Z. 33–80, Dashboard-View | M |
| C3 (P1) | Wacheneinstellungen gliedern: Abschnitte mit `<fieldset>`; abhängige Felder erst sichtbar, wenn das Modul an ist; Zahlungsdaten in die Kaffeekasse-Einstellungen; Schalterzeilen als 48-px-Labels | `templates/core/station_settings.html`, `core/forms.py` Z. 970–1000, `app.css` | M |
| C4 (P2) | Lager: „Entnahme buchen“ als kurzer eigener Schritt von der Listenzeile aus (Charge nach FEFO vorgewählt, Menge mit −/+); Suche und Scanner oben; seltene Aktionen in „Weitere Aktionen“ | `warehouse_dashboard.html`, `warehouse_item_detail.html` Z. 75–82, 219–245 | M |
| C5 (P2) | Wochenbogen: am Handy nur „heute“ aufgeklappt; am Desktop 7 kompakte Spalten, vergangene Tage abgeblendet, Monatsaufgaben nur am Fälligkeitstag; Aufgabe „Fahrzeugcheck“ verlinkt die Übernahme bzw. hakt sich selbst ab | `tasks_week.html`, `modules.css`, Aufgaben-Views | M |
| C6 (P2) | „Geräte & Status“ zeigt Fahrzeuge und Medizingeräte nur lesend mit Link zum führenden Modul; Statuswechsel per Dialog statt 13 Formularen | `assets_inventory.html`, `core/wachalltag_web.py` Z. 252–352 | M |
| C7 (P2) | Kalender: Monatsüberschriften mit Jahr, Filter-Chips (Termine, Feiertage, Geburtstage), Feiertage nur für 2 Monate, ICS-Export im Menü je Termin | `templates/core/calendar.html`, Kalender-View | S–M |
| C8 (P2) | Kaffeekasse: einzeilige Buchungen, neutrale Farbe mit Vorzeichen, echte Plurale, bei nur einer Zahlungsart Text statt Radio | `coffee.html`, `coffee_pay.html`, `modules.css` | S |

## Vor 1.0

- BITV- bzw. WCAG-2.1-AA-Abnahme (R-018) mit Screenreader (NVDA, VoiceOver) und 400 % Zoom.
- Test mit echten Nutzern in der Pilotwache: 5 Aufgaben, Ziel SUS ≥ 70.
- Bedienung mit Handschuhen am Terminal prüfen.
- Vorlage für die Barrierefreiheitserklärung.
- Ampeln nie nur über Farbe (WCAG 1.4.1).

## Messgrößen

Gemessen wird nur in moderierten Bedientests oder per anonymer Umfrage, nie im laufenden Betrieb (keine Dauer und keine Aktivität je Person, AGENTS.md § 1). Am Handy, Demo-Banner ausgeblendet:

| Ablauf | Ziel |
|---|---|
| Fahrzeugübernahme | höchstens 1 Navigations-Tap, unter 3 Minuten (Median) |
| Mangel mit Foto | höchstens 3 Taps |
| Quittieren | ohne Scrollen erreichbar |
| Wand-Display bei 1920×1080 | 0 px Überlauf |
| axe-core | 0 Funde der Schwere serious |
