# Wachbuch Klar - Designregeln

Stand: 30. Oktober 2026

## Entscheidung

Die Webapp verwendet kein vollständiges Admin-Template. Tabler und vergleichbare
Dashboard-Vorlagen bringen für diesen Anwendungsfall zu viele Karten,
Kennzahlen, Icons und Bootstrap-Abhängigkeiten mit. Pico CSS ist leicht, bildet
aber komplexere Rollen-, Fehler- und Prüfprozesse nicht ausreichend ab.

`Wachbuch Klar` ist deshalb eine kleine projektspezifische Oberfläche. Die
Web-PWA teilt die kanonischen Design-Tokens mit dem Flutter-Client
(`clients/wachbuch-mobile`, siehe dort `docs/DESIGN-SYSTEM.md` und
`lib/theme/`). Visuelle Richtung: **öffentlicher Dienst / BOS**
(Rettungsdienst, Feuerwehr, Polizei) – feldlesbar, hoher Kontrast, ruhiges Blau,
keine Marketing-Ästhetik.

Übernommen werden erprobte, nicht markengebundene Muster aus offenen
Designsystemen:

| Quelle | Lizenz | Uebernommenes Muster |
|---|---|---|
| [GOV.UK Frontend](https://github.com/alphagov/govuk-frontend) | MIT | Task-first Seiten, Formstruktur, Fehlerzusammenfassung, Summary Lists |
| [NHS.UK Frontend](https://github.com/nhsuk/nhsuk-frontend) | MIT | Mobile-first Layout, klare Typografie, lineare Aufgabenlisten |
| [USWDS](https://github.com/uswds/uswds) | Public Domain/CC0 mit dokumentierten Dritt-Lizenzen | Responsive, semantische Tabellen |
| [Tabler](https://github.com/tabler/tabler) | MIT | Nur Referenz fuer App-Shells; bewusst nicht eingebunden |
| [Pico CSS](https://github.com/picocss/pico) | MIT | Semantisches HTML als Referenz; bewusst nicht eingebunden |
| [Source Sans 3](https://github.com/adobe-fonts/source-sans) | SIL OFL 1.1 | Lokale Webfonts (`core/static/core/fonts/`), offline-faehig |

Es wurden keine fremden Logos, Markenfarben oder kopierten Komponentenpakete
eingebunden. Kopfleiste und Startseite zeigen das eigene Wachwerk-Logo
(`core/static/core/brand-wachwerk.png`); rot-weiße Warnstreifen werden bewusst
nicht als Schmuck verwendet. Die eigene CSS-Schicht bleibt klein, lokal und offline-fähig.
Minimales JavaScript dient ausschließlich der installierbaren PWA
(Service-Worker, Installationshinweis, Online-Status) und ist keine
Voraussetzung für die Kernabläufe.

## Kanonische Tokens (Web = Client)

| Rolle | Hex | Verwendung |
|---|---|---|
| `brand` / Primary | `#0D47A1` | Header, Primaeraktion, aktive Navigation |
| `brandDeep` | `#082E63` | Hover/Pressed, dunkle Flaechen |
| `brandInk` | `#17343D` | Ueberschriften |
| `accent` | `#2563EB` | Links, Info, Prioritaet normal |
| `bg` | `#F7F9FC` | Seitenhintergrund |
| `surface` | `#FFFFFF` | Flaechen mit Rand `#DCE4EF` |
| `urgent` | `#DC2626` | Dringend / Fehler (nur semantisch) |
| `important` | `#F59E0B` | Wichtig / Warnung |
| `done` / success | `#16A34A` | Erledigt / Erfolg |
| `focus` | `#F0B429` | Tastaturfokus und Service-Akzentstreifen |

Flächen nutzen Rand statt schwerer Schatten. Touch-Ziele: mindestens **48 x 48
CSS-Pixel** (Client und WCAG 2.5.5).

## Zehn verbindliche Regeln

1. Jede Seite hat genau eine Hauptaufgabe und genau eine `h1`.
2. Pro Ansicht gibt es höchstens eine hervorgehobene Primaeraktion.
3. Das Dashboard zeigt Status der aktiven Übergaben, einen kurzen Schnellzugriff
   auf Schichtaufgaben sowie die nächsten drei Termine.
4. Kritische Informationen stehen offen sichtbar, nie in einem geschlossenen
   Accordion oder nur hinter Farbe.
5. Status und Priorität werden immer ausgeschrieben. Farbe ist nur zusätzlich.
6. Jedes interaktive Ziel ist mindestens 48 x 48 CSS-Pixel groß.
7. Mobile beginnt einspaltig; weitere Spalten entstehen erst ab ausreichendem
   Inhaltsplatz, nicht anhand bestimmter Gerätemodelle.
8. Fließtext bleibt auf ungefähr 65 bis 70 Zeichen pro Zeile begrenzt.
9. Listen und Schreibformulare liegen auf getrennten URLs.
10. Rot ist für dringende Zustände und Fehler reserviert, nicht für Dekoration.

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
  in den Ausgangsstand.
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
| Stornieren | cancel | – | Die eigene Funktionskontrolle innerhalb von 5 Minuten zurücknehmen. Das Storno ist ein neuer Datensatz, die Kontrolle bleibt erhalten (Paket B). |
| Einweisung | instruction | – | Einweisung einer Person in ein Medizingerät nach MPBetreibV. Einträge werden nur ergänzt, nie geändert (Paket B). |
| Gültige Einweisung | valid instruction | – | Die aktuell geltende Einweisung einer Person in ein Gerät (Paket B). |
| Einweisungspflicht | instruction requirement | – | Je Wache einschaltbar, nur durch den Master-Admin. Ohne gültige Einweisung ist „Funktion geprüft“ für diese Person gesperrt; ein Befund „Nein“ und eine Mangelmeldung werden trotzdem gespeichert. |
| Gesperrt | locked | – | Medizingerät vorübergehend nicht nutzbar, etwa nach nicht bestandener Funktionskontrolle oder bei offenem Mangel. Aufgehoben nur über die Freigabe. Als Zustand nur für Medizingeräte. Heute teils „Außer Betrieb (Gesperrt)“ (B4). |
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
| `defects` | Mängel | Mängel | Kachel „Mängel & Werkstatt“ |
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
- **Barrierefreiheit & Touch-Ziele:** Mindestzielgroesse von **48 x 48 CSS-Pixeln** (`--touch`), sichtbarer Fokusring (`:focus-visible` mit Token `#f0b429`), Kennzeichnung der aktiven Seite via `aria-current="page"`.
- **Mobiles Verhalten:** Im Viewport unter 48rem bricht `.public-nav` sauber um (kein horizontales Scrollen bei 320 CSS-Pixeln) und überdeckt niemals die fixe mobile `app-nav` am unteren Bildschirmrand.


## Fachmodule (`modules.css`)

Die Modulseiten (MPG, Lager, Fuhrpark, Orga, Display, Mehr) nutzen nur
Komponenten aus `app.css` und ein kleines Vokabular in `modules.css`:

- Layout: `.stack`, `.cluster`, `.split`, `.grid-auto`, `.grid-2`,
  `.muted`, `.text-small`, `.mono`.
- Bausteine: `.filter-tabs`, `.state`/`.dot` (Zustand als Punkt + Text),
  `.module-row` mit `.row-main`/`.row-due`/`.row-actions`, `.note-box`,
  `.modal-panel`, `.field-row`, `.check-list`/`.checkbox-field`,
  `.scanner-view`, `.qr-sticker` (QR und Druck bleiben hell).
- Keine Hash-Klassen, kein `!important`, keine festen Farben: Farben nur
  über Tokens, damit hell und Nachtdienst gleich funktionieren. Feste
  Werte stehen ausschließlich in Token-Blöcken (`:root`, `--lock-*` für den
  bewusst dunklen Sperrbildschirm, `--hero-*` für die Startseiten-Bühne).
- Symbole aus `core/static/core/icons.svg` (`core/_icon.html`), keine Emojis.

Statusfarben (gleich wie in der Flutter-App): dringend = danger, offen =
info, in Arbeit = warning, wartend = neutral, erledigt = success. Für
Zustände ohne Modellstatus gibt es die Töne `.status-label.danger`,
`.warning`, `.info`, `.success`.

## Installierbare App (PWA)

Die Webapp bleibt serverseitig gerendert und kann als Standalone-App auf Handy
oder Wachenterminal installiert werden:

- Web-App-Manifest mit Shortcuts zu Übersicht, Übergaben und Dringend
- Service Worker mit Shell-Precache und Network-first für Lese-Navigation
- Offline-Hinweisseite; keine Offline-Schreibwarteschlange
- Safe-Area- und Standalone-Anpassungen für Notch und Home-Indicator
- ICS-Export einzelner Wachentermine für den Gerätekalender
- `theme_color` `#0D47A1`, `background_color` `#F7F9FC`

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

Referenzen:

- [WCAG 2.2 Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)
- [WCAG 2.2 Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [WCAG 2.2 Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
- [GOV.UK Form structure](https://www.gov.uk/service-manual/design/form-structure)
- [NHS.UK Layout](https://service-manual.nhs.uk/design-system/styles/layout)
- [USWDS Table](https://designsystem.digital.gov/components/table/)
