# Wachbuch Klar - Designregeln

Stand: 11. August 2026

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

Es wurden keine Logos, Markenfarben oder kopierten Komponentenpakete
eingebunden. Die eigene CSS-Schicht bleibt klein, lokal und offline-fähig.
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
