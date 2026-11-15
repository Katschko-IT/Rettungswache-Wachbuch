# Markencode Staffeta

Staffeta ist ein Übergabe-Produkt: ein Stab wird von Schicht zu Schicht weitergereicht. Der Markencode ist so gebaut, dass man ihn an einem Merkmal erkennt, auch ohne Namen.

## Die Regel in einem Satz

Tinte trägt das Buch, und pro Bildschirm bekommt genau eine Stelle den Stab in Signal-Lime.

## Farben

| Name | Wert | Verwendung |
|---|---|---|
| Tinte | `#14212b` | Text, Linien, Bedienung (Schaltflächen), Zeichen |
| Signal-Lime | `#c8e63c` | nur der Stab: Jetzt-Marke im Schichtband, Wortmarke, Zeichen |
| Papier | `#e9eee8` | Grundfläche hell |
| Blatt | `#ffffff` | Karten und Zeilen hell |
| Nacht | `#0d151b` / `#14212b` | Grund und Blatt dunkel; Text `#e9eee8` |

Gerechnet: Tinte auf Papier 13,9:1, Tinte auf Lime 11,6:1, Lime auf Papier nur 1,2:1 und auf Weiß 1,4:1. Lime trägt deshalb nie allein Text, einen dünnen Rand oder eine Information. Einzige Ausnahme: das „ff“ im Logo. Es ist immer Füllung neben oder unter Tinte, und der Stab hat einen Tinte-Rand.

## Zeichen und Wortmarke

- Der Stab: zwei gekippte Hälften (24°), gegeneinander versetzt. Links die Schicht, die geht (Tinte, auf Dunkel Weiß), rechts die, die kommt (Lime). Auf Lime-Grund nur einfarbig.
- Wortmarke: Das kursive Doppel-f in Sta*ff*eta ist die einzige Lime-Schrift. Sie steht nur im Logo, nie im Fließtext. Das „ff“ hat Abstand zu „a“ und „e“.
- Das Schichtband zeigt „jetzt“ als Stab: Lime-Kern mit Tinte-Rand (`.sb-now`, `.sb-now-core`).

## Grenzen

- Lime ist kein Status. Rot, Bernstein, Grün, Violett und der Fokus-Ring bleiben den Bedeutungen vorbehalten.
- Kein Magenta (Telekom), kein Blau-Violett-Verlauf, keine Schlagschatten-Karten.
- Neue Lime-Flächen nur nach dieser Regel; im Logo und in der Wortmarke ist sie die Ausnahme.

---

# Schichtbuch – Designsystem

Stand: 12. November 2026 (Branch `design/schichtbuch-0.29`). Ersetzt
„Wachbuch Klar 2“ vollständig; frühere Stilvorgaben gelten nicht mehr.
Der Produktname ist ein Arbeitsname: Er steht nur im Logo und im Text, nie in
Formen, Mustern oder Farbnamen.

## Konzept: ein Buch, das 24 Stunden offen liegt

Das Produkt ist das gemeinsame Gedächtnis einer Wache über den Schichtwechsel
hinweg. Es ist kein Einsatz-, Alarm- oder Leitstellensystem und soll auch nicht
so aussehen: kein Blaulicht-Cockpit, keine Kachelwand mit Großzahlen, keine
Warnstreifen. Es sieht aus wie das, was es ersetzt – ein sorgfältig geführtes
Wachbuch – und zeigt das, was es wirklich verwaltet: Zeit.

Daraus folgen fünf Entscheidungen. Jede ist an einer Stelle im Code zu finden.

1. **Papier mit eigener Farbe.** Tag ist Hauptbuchpapier: ein kühles, leicht
   grünes Weiß (`--surface` `#f8fbf6` auf der Unterlage `--bg` `#e6ece6`).
   Journale und Kontenbücher werden so getönt, damit die Seite unter
   Leuchtstoffröhren nicht blendet. Bewusst **kein** Creme und kein Beige: Die
   warme Standardfläche wirkt beliebig und passt nicht in eine Fahrzeughalle.
2. **Nacht ist dasselbe Buch unter der Lampe.** Warme, blauarme Flächen
   (`#1b1915` auf `#100f0c`), Schrift in Papierfarbe (`#ece5d5`), nie reines
   Weiß auf Schwarz. Wer um drei Uhr nachts vom Fahrzeug kommt, wird nicht
   geblendet.
3. **Tinte bedient, Stempel bedeuten.** Bedienung, Links und Auswahl sind
   Petroltinte (`--brand`). Sie trägt nie eine Bedeutung. Farbe mit Bedeutung
   gehört allein den vier Stempeln: dringend, fällig, gesperrt, erledigt.
4. **Logbuch statt Karten.** Einträge stehen wie im Buch: links die
   Randspalte mit der Uhrzeit, daneben die Randlinie (`--margin-rule`), rechts
   der Inhalt, darunter eine feine Zeilenlinie. Abschnitte haben eine
   Kopflinie in Tinte. Keine Schatten, keine farbigen Seitenstreifen, keine
   Symbol-Kacheln, keine Zeile über der Überschrift.
5. **Das Schichtband.** Eine waagerechte 24-Stunden-Leiste mit Jetzt-Marke,
   geschriebenen Einträgen, Terminen, fälligen Prüfungen und Sperrzeiten
   (Einwirkzeit nach Desinfektion). Es steht oben auf der Übersicht und über
   die volle Breite des Wachen-Displays. Links von der Jetzt-Marke ist der Tag
   „geschrieben“ (getönt), rechts ist er offen (liniert).

Verworfen wurden: das Blaulicht-/Leitstellen-Cockpit (Verwechslung mit
Einsatzsystemen, Dauer-Alarm stumpft ab), der ruhig-amtliche Stil nach
GOV.UK/NHS (solide, aber austauschbar – die Regeln bleiben, der Stil nicht)
und das SaaS-Dashboard mit Kacheln (zerlegt einen zeitlichen Ablauf in
Kästchen).

Die Webapp verwendet weiterhin kein Admin-Template und kein CSS-Framework.
Übernommen werden nur Regeln, keine Optik, aus offenen Designsystemen:

| Quelle | Lizenz | Uebernommenes Muster |
|---|---|---|
| [GOV.UK Frontend](https://github.com/alphagov/govuk-frontend) | MIT | Task-first Seiten, Formstruktur, Fehlerzusammenfassung, Summary Lists |
| [NHS.UK Frontend](https://github.com/nhsuk/nhsuk-frontend) | MIT | Mobile-first Layout, klare Typografie, lineare Aufgabenlisten |
| [USWDS](https://github.com/uswds/uswds) | Public Domain/CC0 mit dokumentierten Dritt-Lizenzen | Responsive, semantische Tabellen |
| [Tabler](https://github.com/tabler/tabler) | MIT | Nur Referenz fuer App-Shells; bewusst nicht eingebunden |
| [Pico CSS](https://github.com/picocss/pico) | MIT | Semantisches HTML als Referenz; bewusst nicht eingebunden |
| [Atlassian Design](https://atlassian.design/foundations/color) | – | Akzentfarbe trägt nie Bedeutung; Auswahl braucht ein zweites Signal |
| [Stripe Apps](https://docs.stripe.com/stripe-apps/patterns/communicating-state.md) | – | Flüchtiges als Meldung, Dauerhaftes als Banner; Leerzustand nennt den nächsten Schritt |
| [Atkinson Hyperlegible Next](https://www.brailleinstitute.org/freefont/) | SIL OFL 1.1 | Einzige Schrift, lokal in `core/static/core/fonts/` (Lizenzdatei liegt dabei) |

Es wurden keine fremden Logos, Markenfarben oder Komponentenpakete eingebunden
und keine weitere Schrift. Die CSS-Schicht bleibt klein, lokal und
offline-fähig; es gibt keine externen Ressourcen.

## Tokens (`core/static/core/tokens.css`)

`tokens.css` ist die einzige Quelle für Farben, Radien und Maße.
`scripts/sync_design_assets.py` kopiert sie nach `site/` und
`docs/praesentation/`. Die Flutter-App (`clients/wachbuch-mobile`,
`lib/theme/design_tokens.dart`) nutzt dieselben Namen; ihre Werte sind noch
auf dem alten Stand und müssen nachgezogen werden.

| Rolle | Token | Tag | Nacht |
|---|---|---|---|
| Unterlage | `--bg` | `#e6ece6` | `#100f0c` |
| Blatt | `--surface` | `#f8fbf6` | `#1b1915` |
| Einzug, Tabellenkopf | `--surface-soft` | `#eef3ec` | `#25221c` |
| Tinte (Text) | `--text` | `#13212a` | `#ece5d5` |
| Gedämpft | `--muted` | `#4a5a5e` | `#b0a794` |
| Zeilenlinie (dekorativ) | `--line` | `#c9d4cb` | `#36322a` |
| Rand von Bedienelementen | `--line-strong` | `#66766f` | `#857c6b` |
| Randlinie der Randspalte | `--margin-rule` | `#8fb5ba` | `#3e5e61` |
| Petroltinte (Bedienung) | `--brand` | `#0b5563` | `#7cc6ce` |
| Schrift auf Petrol | `--on-primary` | `#ffffff` | `#06262b` |
| Dringend | `--danger` / `--on-danger` | `#a3231b` / `#ffffff` | `#ff9282` / `#2a0a06` |
| Fällig, wichtig | `--warning` (Rand `--warning-accent`) | `#7a4a00` (`#b37400`) | `#f2b84b` |
| Gesperrt | `--violet` (= `--locked`) | `#5a3d99` | `#c3adf5` |
| Erledigt, bereit | `--success` | `#2a6418` | `#9ad07a` |
| Tastaturfokus | `--focus` / `--focus-halo` | `#1846d6` / `#13212a` | `#a9c1ff` / `#ece5d5` |

### Kontrast (WCAG 2.2, relative Leuchtdichte, von Hand gerechnet)

Die Werte sind mit der WCAG-Formel aus den Hex-Werten gerechnet und auf eine
Stelle gerundet; `core/test_028_defects_display.py` prüft einen Teil davon
automatisch, der CI-Job `a11y` (axe-core) misst im Browser nach.

| Paar | Tag | Nacht | Soll |
|---|---|---|---|
| Text auf Blatt / Unterlage | 15,7 / 13,7 | 14,0 / 15,3 | 4,5 |
| Gedämpft auf Blatt / Unterlage / Einzug | 6,9 / 6,0 / 6,4 | 7,4 / 8,0 / 6,6 | 4,5 |
| Petrol auf Blatt | 8,1 | 9,1 | 4,5 |
| Schrift auf Petrol (Hauptknopf) | 8,4 | 8,2 | 4,5 |
| Dringend auf Blatt / auf eigener Tönung | 7,2 / 6,1 | 8,1 / 7,4 | 4,5 |
| Schrift auf gefülltem Dringend-Stempel | 7,5 | 8,5 | 4,5 |
| Fällig auf Blatt / auf eigener Tönung | 7,2 / 6,4 | 9,8 / 8,3 | 4,5 |
| Gesperrt auf Blatt / auf eigener Tönung | 7,9 / 6,7 | 8,9 / 7,6 | 4,5 |
| Erledigt auf Blatt / auf eigener Tönung | 6,9 / 6,1 | 9,8 / 8,1 | 4,5 |
| Rand von Bedienelementen auf Blatt / Unterlage | 4,6 / 4,0 | 4,3 / 4,7 | 3,0 |
| Rand „fällig“ (`--warning-accent`) auf Blatt | 3,7 | 9,8 | 3,0 |
| Fokusring auf Blatt / Unterlage | 7,0 / 6,1 | 9,8 / 10,7 | 3,0 |

## Typografie

Eine Schrift: Atkinson Hyperlegible Next (400, 600, 700), lokal gebündelt.
Unverwechselbar wird die Oberfläche durch Satz und Raster, nicht durch eine
zweite Schrift.

- Überschriften in Satzschreibung, 700, leicht enger gesetzt. Keine Versalien,
  keine gesperrten Kleinzeilen über der Überschrift: Ort und Datum stehen als
  Datumszeile **unter** der `h1` (`.context-line`).
- Uhrzeiten, Zähler und Beträge immer in Tabellenziffern
  (`font-variant-numeric: tabular-nums`).
- Randspalte 600, Inhalt 400, Titel eines Eintrags 700.
- Fließtext höchstens 65 bis 70 Zeichen je Zeile.

## Formen

- Blätter (`.section-block`, `.form-card`, `.summary-list`): Fläche
  `--surface`, 1 px Linie, 4 px Radius, kein Schatten.
- Abschnitt = Kopfzeile mit 1 px Tintenlinie darunter, Zeilen mit
  Zeilenlinien. Die Kopfleiste der App schließt mit einer Doppellinie wie der
  Kopf einer Buchseite.
- Logbuchzeile (`.list-row` mit `time`): Randspalte `--rail` mit Uhrzeit,
  Randlinie `--margin-rule` (1 px), Inhalt, Stempel rechts.
- Knöpfe: 4 px Radius, mindestens 48 px hoch. Hauptknopf gefüllt in Petrol,
  Nebenknopf Blatt mit Tintenrand. Kein Farbverlauf, kein Schatten.
- Nicht verwenden: farbige Seitenstreifen an Flächen (`border-left` in
  Signalfarbe), Symbol auf getönter Kachel, Pillen mit vollem Radius für
  Status, Schatten auf Blättern.

## Stempel (Status)

Jeder Status ist ein Stempel: ausgeschriebenes Adjektiv in Satzschreibung,
rechteckig (2 px Radius), nie klickbar. Die **Randform** ist das zweite
Signal neben der Farbe – sie bleibt auch in Graustufen und bei
Farbfehlsichtigkeit lesbar.

| Bedeutung | Klassen (`.status-label`, `.badge`, `.urgency-pill`, `.state`) | Form | Farbe |
|---|---|---|---|
| Dringend, überfällig, nicht bestanden | `.priority-urgent`, `.danger`, `.badge-fail`, `.urgency-overdue` | **gefüllte Fläche** | `--danger` mit `--on-danger` |
| Kritisch | `.urgency-critical` | 2 px durchgezogen | `--danger` |
| Fällig, wichtig, in Arbeit | `.priority-important`, `.warning`, `.status-in_progress`, `.urgency-warning` | **gestrichelter Rand** | `--warning` |
| Gesperrt | `.locked`, `.violet` | **doppelter Rand** | `--violet` |
| Erledigt, bereit, bestanden | `.success`, `.status-done`, `.badge-pass`, `.urgency-ok` | durchgezogen mit Haken | `--success` |
| Offen, normal, Hinweis | `.status-open`, `.priority-normal`, `.neutral`, `.info` | durchgezogen | `--text` |
| Wartend | `.status-waiting` | gepunktet | `--muted` |

„Dringend“ ist der einzige Stempel mit gefüllter Fläche. „Gesperrt“ hat eine
eigene Farbe, weil eine Sperre kein Alarm ist, sondern ein fester Zustand
(Einwirkzeit, offener Mangel am Medizingerät, Rückruf einer Charge).

## Schichtband (`.shift-band`)

Datenquelle: `core/shift_band.py`. Das Band nutzt nur vorhandene Zeitdaten
und legt nichts an.

- Achse: 00 bis 24 Uhr der Wachenzeit, Stundenmarken alle 6 Stunden.
- Jetzt-Marke: senkrechte Tintenlinie mit Dreieck. Links davon ist das Band
  getönt („geschrieben“), rechts liniert („offen“).
- Marken: Übergaben des Tages (Strich, dringende gefüllt), Termine mit Uhrzeit
  (Raute), fällige Checklisten (gestrichelter Strich), Einwirkzeit je Fahrzeug
  (schraffierte Spanne in `--violet`).
- Unter dem Band steht jede Marke noch einmal als Text mit Uhrzeit: Das Band
  ist nie die einzige Quelle einer Information.
- Schichtgrenzen zeigt das Band **nicht**: Die Wache speichert bisher keine
  Schichtzeiten (`core/models.py`, `Station`). Sobald es sie gibt, werden sie
  als senkrechte Doppellinie ergänzt.
- Technik: Inline-SVG mit Attributen (kein `style=`, CSP-fest), funktioniert
  ohne JavaScript. `ui.js` rückt die Jetzt-Marke im Minutentakt nach.
- Display: dieselbe Leiste über die volle Breite, aufgebaut von `display.js`
  aus den vorhandenen Feldern `events[].time` und
  `fleet_vehicles[].locked_until`.
- Zeichenerklärung: Die Startseite und die Projektseite zeigen unter dem Band
  eine Legende (`templates/core/_shift_band_key.html`, `.shift-band-key`) mit
  Übergabe, Dringend, Termin, Gerät gesperrt, Frist fällig und Jetzt. Das Band
  selbst bleibt `aria-hidden`; die Legende steht außerhalb davon.
- Jetzt-Marke („Stab“): Tinte-Rand (`--on-signal`, im Display fest `#14212b`)
  mit Lime-Kern `--signal`. Lime steht nie allein, weil es auf hellem Papier
  keinen Kontrast hat.

### Wandmonitor: Schriftgrößen nach Lesedistanz

Maßstab ist DIN 1450 (Mittellänge in cm = Lesedistanz in cm / 250; für helle
Schrift auf dunklem Grund +10 %). Gerechnet für ein 43-Zoll-Gerät mit 1080p
(0,496 mm je Pixel), Versalien-Stempel mit Versalhöhe ≈ 0,7 em, gemischte
Schrift mit Mittellänge ≈ 0,5 em:

| Element | Größe vorher → jetzt (1920 px) | Lesedistanz vorher → jetzt |
|---|---|---|
| Fahrzeug-Stempel (Versalien) | 24 → 28,8 px | 1,9 → 2,3 m |
| Skala unter dem Band | 24 → 28,8 px | – |
| Quellenangabe Verkehr | 19,2 → 24 px | 1,1 → 1,4 m |
| Meta-Zeile Verkehr | 22 → 25,9 px | 1,2 → 1,5 m |

Das sind Rechenwerte, keine Messung vor Ort. Für 3 m Abstand reichen diese
Größen nicht: Auch Terminzeile und Name (33,6 und 30,7 px) tragen auf 43 Zoll
nur ca. 1,7–1,9 m, auf 55 Zoll ca. 2,2–2,4 m (Stempel bis ca. 2,9 m). Für 3 m
müsste die Hauptschrift rund 2,8 vw statt 1,75 vw betragen; das ändert das
Raster und ist bewusst nicht Teil dieses Branches. Die Werte stehen in
`display.css` (`--vw`-Skalierung) und gelten für den Kiosk-Rahmen 16:9.

## Bewegung

Bewegung gibt es nur bei einem Zustandswechsel, nie als Schmuck:

- Eine Meldung nach einer Aktion „setzt auf“ wie ein Stempel (160 ms).
- Farbwechsel beim Überfahren und Drücken (120 ms).
- Die Jetzt-Marke rückt im Minutentakt, ohne Animation.
- `prefers-reduced-motion: reduce` schaltet alles ab.

## Geräte

- **Handy:** einspaltig, Randspalte schmal (Datum über Uhrzeit), Schichtband
  oben, Hauptaktion über der unteren Leiste in Daumenreichweite.
- **Desktop:** Logbuch links, Seitenspalte rechts (Fahrzeuge, Aufgaben,
  Termine).
- **Wachen-Display:** immer Nacht-Palette (blendet in der Halle nicht), Uhr
  und Schichtband über die volle Breite, Fahrzeuge mit Stempeln, keine
  Bewegung außer dem Minutentakt.
- **Druck und QR:** bleiben hell (`--paper`, `--paper-ink`).

## Zehn verbindliche Regeln

1. Jede Seite hat genau eine Hauptaufgabe und genau eine `h1`.
2. Pro Ansicht gibt es höchstens eine gefüllte Hauptaktion.
3. Die Übersicht zeigt zuerst das Schichtband, dann was Aufmerksamkeit
   braucht, dann die Übergaben für die nächste Schicht.
4. Kritische Informationen stehen offen sichtbar, nie in einem geschlossenen
   Accordion oder nur hinter Farbe.
5. Status und Priorität werden immer ausgeschrieben. Farbe und Randform sind
   nur zusätzlich.
6. Jedes interaktive Ziel ist mindestens 48 x 48 CSS-Pixel groß (kleine
   Knöpfe in dichten Listen mindestens 44 x 44).
7. Mobile beginnt einspaltig; weitere Spalten entstehen erst ab ausreichendem
   Inhaltsplatz, nicht anhand bestimmter Gerätemodelle.
8. Fließtext bleibt auf ungefähr 65 bis 70 Zeichen pro Zeile begrenzt.
9. Listen und Schreibformulare liegen auf getrennten URLs.
10. Rot ist für dringende Zustände und Fehler reserviert, Petrol für
    Bedienung. Keine Farbe ist Dekoration.

## Glossar

Das Glossar gilt ab 0.27 für alle Texte der Oberfläche: Webseiten,
Wachenterminal, Wachen-Display, E-Mails und Benachrichtigungen. Neue Texte
verwenden nur die Begriffe der ersten Spalte. Die Spalte „Englisch“ ist die
Vorgabe für `locale/en/LC_MESSAGES/django.po`. Ältere Übersetzungen weichen
teils noch ab (zum Beispiel „Gesperrt“ → „Closed“, „Übernahme“ → „handover“)
und werden mit UX-PLAN B4 (0.28) bereinigt.

So wird das Glossar geprüft:

- `core/test_glossary.py` liest die Tabelle zwischen den HTML-Kommentaren
  `glossar:begin` und `glossar:end`. Jedes Wort in Backticks in der Spalte
  „Nicht verwenden“ ist für neue übersetzbare Texte gesperrt, auch mit den
  Endungen -s, -e, -en und -n und in Bindestrich-Wörtern wie
  „Fahrzeug-Cockpit“ oder „Heilkunde-SOPs“. Geprüft werden alle markierten Texte in Python, Templates
  und JavaScript (wie `scripts/i18n_catalog.py` sie sammelt).
- Bestehende Vorkommen sind je Begriff als Ausgangsstand (`BASELINE` im Test)
  eingefroren. Sie verschwinden mit der Umbenennung in B4. Wer ein altes
  Vorkommen entfernt, muss nichts nachtragen. Den Ausgangsstand erhöht nur,
  wer ein altes Vorkommen mit Begründung behalten muss. Ein neues Wort in
  Backticks gilt sofort; seine vorhandenen Vorkommen kommen mit ihrer Anzahl
  in den Ausgangsstand. Die Sperrliste steht auch in `AGENTS.md` (§ 6),
  damit jedes Paket sie vor dem ersten Text kennt; der Test hält beide gleich.
- Wörter ohne Backticks sind Hinweise ohne Prüfung. Sie sind in anderer
  Bedeutung richtig („Telemetrie“ im Sinne von „keine Telemetrie“), oder
  andere Tests decken sie ab (FMS-Status und Einsatzphasen prüfen die Tests
  der Produktgrenze).
- `SOP` ist bewusst gesperrt, auch als „Heilkunde-SOP“: Die Oberfläche sagt
  „Dienstanweisung“. Inhalte, die eine Wache selbst anlegt, prüft der Test
  nicht. Der Titel einer Dienstanweisung darf also „SOP …“ heißen.
- Die Begriffe „Gesperrt“, „Außer Dienst“ und „Außer Betrieb nehmen“ und die
  Modulnamen im nächsten Abschnitt sind für 0.27 festgelegt (Stand 30.10.2026).

<!-- glossar:begin -->
| Begriff | Englisch | Nicht verwenden | Bedeutung |
|---|---|---|---|
| Wache | station | – | Die Rettungswache. Alle Daten gehören genau einer Wache. |
| Übergabe | handover | – | Schichtübergabe als Eintrag mit Status. Nie für ein Fahrzeug, dafür gibt es „Fahrzeugübernahme“. |
| Lesebestätigung | read confirmation | `Lesequittierung` | Vermerk, dass eine Person eine Übergabe, Neuigkeit oder Dienstanweisung gelesen hat. |
| Gelesen – quittieren | read – acknowledge | – | Schaltfläche für die Lesebestätigung. Nur mit dem eigenen Konto, nie am Wachenterminal. |
| Mangel | defect | – | Festgestellter Fehler, der behoben werden muss, mit Priorität und Frist. |
| Tagesaufgaben | daily tasks | – | Digitale Wandtafel der Wache. In der Leiste kurz „Aufgaben“. |
| Wochenbogen | weekly sheet | – | Wochenansicht der Tagesaufgaben. |
| Erledigt | done | – | Status und Schaltfläche, wenn eine Aufgabe abgeschlossen ist. |
| Offen | open | – | Gegenstück zu „Erledigt“. Bleibt ausgeschrieben (Regel 5). |
| Checkliste | checklist | – | Prüfliste, etwa für die Schichtübernahme oder den Wachenrundgang. |
| Dienstanweisung | work instruction | `SOP` | Versioniertes Dokument der Wache mit Lesebestätigung, auch für heilkundliche Maßnahmen. |
| Außer Kraft | no longer in force | – | Dienstanweisung, die nicht mehr gilt. Sie bleibt mit allen Lesebestätigungen erhalten (Paket B). |
| Fahrzeugzustand | vehicle condition | `Fahrzeugstatus`, FMS-Status | Genau fünf Zustände: Einsatzbereit, Eingeschränkt, Desinfektion, Werkstatt, Außer Dienst. Keine Einsatzphasen, keine Statusziffern. |
| Einsatzbereit | ready for service | – | Fahrzeugzustand. |
| Eingeschränkt | restricted | – | Fahrzeugzustand: nutzbar, aber mit Einschränkung. |
| Desinfektion | disinfection | – | Fahrzeugzustand und Vorgang. Ein Fahrzeug bis zur Freigabe nach der Desinfektion ist im Zustand „Desinfektion“, nicht „Gesperrt“. Stufen heißen nach ihrer Wirkung (etwa „Schlussdesinfektion (viruzid)“), nie nach Erregern. Art und Stufe sehen bis 0.28 nur die durchführende Person, Schichtleitung und Master-Admin; alle anderen sehen „Desinfektion“ mit Datum und Mittel. |
| Werkstatt | workshop | – | Fahrzeugzustand. |
| Außer Dienst | out of service | – | Fahrzeugzustand, vorübergehend. Nur für Fahrzeuge. |
| Fahrzeugübernahme | vehicle takeover | `Cockpit` | Prüfung des Fahrzeugs zu Schichtbeginn, nie „Übergabe“. Seiten heißen „Fahrzeugseite“ oder „Geräteseite“, nicht „Cockpit“. |
| Füllstände | fill levels | Telemetrie | Kraftstoff, AdBlue und Sauerstoff am Fahrzeug. „Telemetrie“ nur im Datenschutzsinn („keine Telemetrie“). |
| Medizingerät | medical device | `Asset` | Gerät nach MPBetreibV mit Gerätebuch, Prüffristen und Einweisungen. |
| Funktionskontrolle | function check | – | Kontrolle vor dem Gebrauch. Die Schaltfläche heißt „Funktion geprüft“. |
| Stornieren | void | – | Die eigene Funktionskontrolle innerhalb von 5 Minuten zurücknehmen. Das Storno ist ein neuer Datensatz, die Kontrolle bleibt erhalten (Paket B). |
| Einweisung | instruction | – | Einweisung einer Person in ein Medizingerät nach MPBetreibV. Einträge werden nur ergänzt, nie geändert (Paket B). |
| Gültige Einweisung | valid instruction | – | Die aktuell geltende Einweisung einer Person in ein Gerät (Paket B). |
| Einweisungspflicht | instruction requirement | – | Je Wache einschaltbar, nur durch den Master-Admin. Ohne gültige Einweisung sind „Funktion geprüft“ und die Freigabe des Geräts für diese Person gesperrt; ein Befund „Nein“ und eine Mangelmeldung werden trotzdem gespeichert. |
| Gesperrt | locked | – | Medizingerät vorübergehend nicht nutzbar, etwa nach nicht bestandener Funktionskontrolle oder bei offenem Mangel. Aufgehoben nur über die Freigabe. Bei Geräten und Fahrzeugen als Zustand nur für Medizingeräte (Fahrzeuge: „Desinfektion“, „Werkstatt“, „Außer Dienst“). Weitere feste Bedeutungen: Charge nach Rückruf gesperrt (Lager), Wachenterminal gesperrt (Sperrbildschirm), Konto gesperrt. Heute teils „Außer Betrieb (Gesperrt)“ (B4). |
| Außer Betrieb nehmen | decommission | – | Dauerhaft; alle Nachweise bleiben erhalten (Paket B). Oberbegriff für Fahrzeuge, Geräte, Mittel und Dienstanweisungen. Am Objekt heißt es „Ausmustern“ (Fahrzeug, Medizingerät) oder „Außer Kraft“ (Dienstanweisung). Nie für eine vorübergehende Sperre. |
| Ausmustern | retire | – | Fahrzeug oder Medizingerät dauerhaft außer Betrieb nehmen. Danach im Zustand „Ausgemustert“ (Paket B). |
| Wachenterminal | station terminal | – | Touch-Gerät in der Wache mit eigenem Dienstkonto, kein persönliches Konto. Nur Alltagsbereiche; keine Lesebestätigung, keine Medizingeräte, keine Fahrzeugübernahme (AGENTS.md § 4). |
| Sperrbildschirm | lock screen | – | Ruheanzeige des Wachenterminals mit Uhr, Übergaben, Aufgaben und Fahrzeugen. |
| Wachen-Code | station code | – | Vierstelliger Code, der das Wachenterminal entsperrt. |
| Wachen-Display | station display | – | Vollbildanzeige, etwa in der Fahrzeughalle, geöffnet über einen Display-Link. |
| Display-Link | display link | `Display-Token` | Widerrufbarer Zugangs-Link für ein Wachen-Display. |
| Push-Benachrichtigung | push notification | `Push-Mitteilung` | Benachrichtigung auf Handy oder PC. |
| Audit | audit | `Logbuch` | Nachvollziehbare Protokollierung der Änderungen. Einträge werden nur ergänzt. |
| Geräte & Schlüssel | equipment & keys | `Poolbestand` | Modul für Geräte, Schlüssel und Poolmaterial mit Ausgabe und Rückgabe. |
| Dienstanweisungen & Telefonbuch | work instructions & phone book | `Desk` | Modul für die Dienstanweisungen und das Telefonbuch der Wache. |
| Mitglied | member | – | Rolle. |
| Schichtleitung | shift lead | – | Rolle. |
| Kassenwart | cashier | – | Rolle für die Kaffeekasse. |
| Master-Admin | master admin | – | Rolle, „der Master-Admin“. |
| Auditor | auditor | – | Rolle mit Lesezugriff ohne fachliche Freitexte. |
| Druckansicht | print view | – | Seite zum Ausdrucken leerer Formulare für die Papier-Rückfallebene (Paket G). Kein PDF. |
| Stammdaten-Import | master data import | – | Import von Artikeln, Lagerorten, Medizingeräten und Fahrzeugen als CSV (Paket F). Konten nur als Einladungen. |
<!-- glossar:end -->

### Modulnamen (Ziel für B4, 0.28)

Jedes Modul hat einen Namen für die Kachel unter „Mehr“, die Überschrift
(`h1`) und den Seitentitel. Die Leiste darf eine Kurzform nutzen. Neue Seiten
in 0.27 verwenden diese Namen. Bestehende Seiten behalten ihren Namen, bis B4
sie umbenennt. Die erste Spalte ist der Schlüssel `data-more` der Kachel in
`templates/core/more.html`; „–“ in der Spalte „Leiste“ heißt: nicht in der
Leiste wählbar.

<!-- modulnamen:begin -->
| Bereich | Kachel, h1 und Titel | Leiste | Heute abweichend |
|---|---|---|---|
| `fleet` | Fahrzeuge | Fahrzeuge | Kachel und h1 „Fuhrpark & Fahrzeuge“, Titel „Fuhrpark & Hygiene“, Leiste „Fuhrpark“ |
| `mpg` | Medizingeräte | Medizingeräte | Kachel, h1 und Titel „MPG & Medizingeräte“, Leiste „MPG & Geräte“ (mehrdeutig neben „Geräte“) |
| `assets` | Geräte & Schlüssel | Geräte & Schlüssel | Kachel „Geräte & Poolbestand“, h1 und Titel „Geräte & Status“, Leiste „Geräte“ |
| `orga` | Dienstanweisungen & Telefonbuch | Dienstanweisungen | Kachel und Titel „Organisation & Desk“, h1 „Organisation & Dienstanweisungen“, Leiste „Organisation“ |
| `defects` | Mängel | Mängel (Vorschlag, Entscheidung offen, B4) | Kachel „Mängel & Werkstatt“ |
| `tasks` | Tagesaufgaben | Aufgaben | – |
| `calendar` | Kalender | Kalender | Kachel „Wachenkalender“ |
| `reports` | Auswertung | Auswertung | Kachel „Auswertung & Kennzahlen“ |
| `display_tokens` | Display-Links | – | Kachel „Display-Tokens“, h1 und Titel „Wachen-Display“ (wie das Display selbst) |
| `audit` | Audit | – | Kachel „Audit-Logbuch“ |
| `push` | Push-Benachrichtigungen | – | Kachel „Push-Mitteilungen“, Titel „Benachrichtigungen“ |
| `team` | Team & Rollen | – | Titel „Team“ |
| `invites` | Offene Aktivierungen | – | Kachel „Mitarbeiter-Aktivierungen“ |
<!-- modulnamen:end -->

## Informationsarchitektur

Die globale Navigation besitzt vier Punkte:

- `Uebersicht`: priorisierte aktive Übergaben und nächste Termine
- `Uebergaben`: Aktiv, Dringend und Archiv mit Pagination
- `Kalender`: chronologische Agenda
- `Mehr`: aktivierte Zusatzmodule und rollenabhaengige Verwaltung

Kalendertermine, Tagesaufgaben, Kassenbuchungen, Geburtstagsfreigaben und
Teamfreigaben werden jeweils auf einer eigenen Seite erfasst. Region zeigt nie
Nachrichten und Verkehr gleichzeitig, sondern einen ausgewählten Inhaltstyp.

Tagesaufgaben folgen der Wandtafel: grüne tägliche Routine, gelbe
Wochentagsrotation, blaue zusätzliche Punkte. Details in
[`WALL-BLOCKS.md`](WALL-BLOCKS.md).

### Öffentliche Navigation (Public Nav)

Neben der viergliedrigen Fachnavigation (`Uebersicht`, `Uebergaben`, `Kalender`, `Mehr`) existiert ein eigenständiger öffentlicher Navigationsbereich (`.public-nav`):

- **Zweck:** Bereitstellung von Links zu öffentlichen Seiten (`Vorfuehrung`, `Datenschutz`), die auch ohne Anmeldung und ohne JavaScript sofort erreichbar sind.
- **Sichtbarkeit:** Persistent im Header auf allen Seiten (Desktop, Tablet, Mobile, Login, Vorführung, Demo).
- **Entkopplung:** Die 4-Punkte-Fachnavigation (`app-nav`) für angemeldete Wachenmitglieder bleibt unberührt und wird nicht durch zusätzliche Menuepunkte überfrachtet.
- **Barrierefreiheit & Touch-Ziele:** Mindestzielgroesse von **48 x 48 CSS-Pixeln** (`--touch`), sichtbarer Fokusring (`:focus-visible` mit `--focus` und Saum `--focus-ring`, siehe „Barrierefreiheit“), Kennzeichnung der aktiven Seite via `aria-current="page"`.
- **Mobiles Verhalten:** Im Viewport unter 48rem bricht `.public-nav` sauber um (kein horizontales Scrollen bei 320 CSS-Pixeln) und überdeckt niemals die fixe mobile `app-nav` am unteren Bildschirmrand.


## Fachmodule (`modules.css`)

Die Modulseiten (MPG, Lager, Fuhrpark, Orga, Display, Mehr) nutzen nur
Komponenten aus `app.css` und ein kleines Vokabular in `modules.css`:

- Layout: `.stack`, `.cluster`, `.split`, `.grid-auto`, `.grid-2`,
  `.muted`, `.text-small`, `.mono`.
- Bausteine: `.filter-tabs`, `.state` (Zustand als Stempel) und `.dot`
  (kleine Formmarke vor einem Filter; der Text daneben nennt den Zustand),
  `.module-row` mit `.row-main`/`.row-due`/`.row-actions`, `.note-box`,
  `.modal-panel`, `.field-row`, `.check-list`/`.checkbox-field`,
  `.scanner-view`, `.qr-sticker` (QR und Druck bleiben hell).
- Keine Hash-Klassen, kein `!important`, keine festen Farben: Farben nur
  über Tokens, damit hell und Nachtdienst gleich funktionieren. Feste
  Werte stehen ausschließlich in Token-Blöcken (`:root`, `--lock-*` für den
  bewusst dunklen Sperrbildschirm, `--display-*` für das Wachen-Display).
  Beide nutzen die Werte der Nacht-Palette. Ausnahme in `public.css`: die
  Terminalfläche `.code-block` und der Geräterahmen der Bildschirmfotos.
- Symbole aus `core/static/core/icons.svg` (`core/_icon.html`), keine Emojis.

Statusfarben (gleich wie in der Flutter-App): dringend = danger, offen =
info, in Arbeit = warning, wartend = neutral, erledigt = success. Für
Zustände ohne Modellstatus gibt es die Töne `.status-label.danger`,
`.warning`, `.info`, `.success`.

## Druckansichten (`paper.css`)

Die Papier-Rückfallebene (`/papier/`) druckt mit dem Browser, ohne
PDF-Bibliothek (Roadmap, Grundsatz 7):

- `core/static/core/paper.css` wird nur auf den Seiten unter `/papier/`
  geladen (`templates/core/paper_base.html`, Körperklasse `paper-view`).
- Klassen: `.paper-sheet` (ein A4-Blatt), `.paper-head`, `.paper-table`,
  `.paper-rows` (Zeilen zum Ausfüllen), `.paper-box` (Ankreuzfeld als
  CSS-Kästchen, `aria-hidden`), `.paper-screen-only` (nur am Bildschirm).
- `@media print` blendet alles außer `main#inhalt` aus
  (`body.paper-view > :not(#inhalt)`), ohne `!important`.
- Das Blatt bleibt hell, auch im Nachtdienst (`--paper`/`--paper-ink`).
- A4 hochkant, ein Blatt je Objekt (`break-after: page`), Tabellenköpfe
  wiederholen sich auf Folgeseiten. Keine Seitenzahlen in Randfeldern.
- Nummerierte Spaltenköpfe tragen die volle Beschriftung als
  `.visually-hidden`.

## Installierbare App (PWA)

Die Webapp bleibt serverseitig gerendert und kann als Standalone-App auf Handy
oder Wachenterminal installiert werden:

- Web-App-Manifest mit Shortcuts zu Übersicht, Übergaben und Dringend
- Service Worker mit Shell-Precache und Network-first für Lese-Navigation
- Offline-Hinweisseite; keine Offline-Schreibwarteschlange
- Safe-Area- und Standalone-Anpassungen für Notch und Home-Indicator
- ICS-Export einzelner Wachentermine für den Gerätekalender
- `theme_color` `#f8fbf6` (Blatt), `background_color` `#e6ece6` (Unterlage);
  die `theme-color`-Metas in `base.html` nennen Blatt hell und Blatt Nacht
  (`#1b1915`)
- Verbindungsbanner (`.connection-chip`): erscheint, sobald das Gerät offline
  ist oder der Server der Wache nicht antwortet (`app.js`, `probeServer`),
  bleibt stehen und nennt den Weg zum Papier-Rückfall

## Responsive Verhalten

- Bis `48rem` beziehungsweise typischerweise 768 CSS-Pixel: eine Spalte,
  vierteilige Navigation am unteren Rand, mobile Key-Value-Tabellen.
- Über `48rem`: Navigation unter dem App-Header, Identität bleibt sichtbar.
- Bis `64rem`: Inhaltsbereiche bleiben einspaltig, damit Tablets nicht in enge
  Zwei-Spalten-Layouts gezwungen werden.
- Über `64rem`: nur die Übersicht darf Übergaben und Termine nebeneinander
  darstellen.
- Bei 320 CSS-Pixel darf die Gesamtseite nicht horizontal scrollen.

## Barrierefreiheit

Ziel ist WCAG 2.2 AA mit interner Touchziel-Vorgabe von 48 CSS-Pixeln
(Angleichung an den Client). Verbindlich sind sichtbarer Tastaturfokus,
semantische Tabellen, permanente Feldlabels, Erhalt fehlerhafter Eingaben, Text
plus Farbe für Status und `prefers-reduced-motion`-freundliche Darstellung ohne
notwendige Animation. `prefers-contrast: more` schaltet auf Schwarz/Weiß wie
die Flutter-HighContrast-Themes.

Regeln seit 0.28 (geprüft durch den CI-Job `a11y` mit axe-core, hell und
dunkel, sowie `core/test_028_defects_display.py`):

- **Fokusring:** 3 px Kobaltblau (`--focus`, Tag `#1846d6`, Nacht `#a9c1ff`)
  mit 3 px Abstand. Kobalt kommt sonst nirgends vor und ist deshalb nie mit
  dem Ocker von „fällig“ zu verwechseln; es erreicht gegen `--surface`,
  `--bg` und `--surface-soft` in beiden Modi mindestens 6:1. Durch den
  Abstand steht der Ring auch um gefüllte Knöpfe immer auf dem Blatt.
  `--focus-halo` (Tinte, Tag `#13212a`, Nacht `#ece5d5`) und `--focus-ring`
  sind der zusätzliche Saum als `box-shadow` für Bausteine, die den Fokus
  eines inneren Felds zeigen (Chips mit `:has(input:focus-visible)`, Knöpfe
  „Foto aufnehmen“ und „Datei wählen“); der Saum erreicht gegen die drei
  Flächen mindestens 3:1 (WCAG 1.4.11).
  Kein Fokusring mit Tokens anderer Bereiche (z. B. `--display-accent`).
- **Ausgewählte Chips** nutzen dasselbe Farbpaar wie `.button.primary`:
  `--brand` mit `--on-primary` (hell und dunkel mindestens 4,5:1), nie fest
  `#ffffff`.
- **Gedämpfte Einträge** (z. B. Monate ohne Beitrag in der Kaffeekasse) nie
  über `opacity`: Text in `--muted` bei voller Deckkraft (mindestens 4,5:1),
  dazu ein Textlabel („kein Beitrag“, „kommt noch“) und eine gestrichelte Kante.
- **Versteckte Felder** (`.visually-hidden`) setzen Breite, Höhe, Polster und
  Mindesthöhe mit `!important` auf das Clip-Muster und liegen in einem Baustein
  mit `position: relative`; sonst verbreitern Formularregeln die Seite auf dem
  Handy. Der CI-Job prüft das Mangelformular bei 390x844 auf seitliches
  Scrollen.
- **Feldlabels:** Jedes `<label>` gehört zu einem Feld (`for` oder
  verschachtelt). Gruppen (Foto, Kategorie, Priorität) sind `<fieldset>` mit
  `<legend>`; keine internen Begriffe wie „Tipp 1“ in sichtbaren Texten.

Referenzen:

- [WCAG 2.2 Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)
- [WCAG 2.2 Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [WCAG 2.2 Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
- [GOV.UK Form structure](https://www.gov.uk/service-manual/design/form-structure)
- [NHS.UK Layout](https://service-manual.nhs.uk/design-system/styles/layout)
- [USWDS Table](https://designsystem.digital.gov/components/table/)
