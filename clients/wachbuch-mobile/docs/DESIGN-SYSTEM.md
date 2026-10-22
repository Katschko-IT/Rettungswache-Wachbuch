# Wachbuch Design System

Stand: 9. August 2026. Systemunabhängiges Design für iOS, Android und Web-PWA.

## Prinzipien

1. **WCAG 2.2 AA als verbindliche Basis** — Textkontrast mindestens 4,5:1; kritische Flächen und High-Contrast-Modus werden strenger ausgelegt
2. **48dp Touch-Ziele** — bedienbar mit Handschuhen und in Eile
3. **Semantik plus Farbe** — Rot/Gelb/Grün/Blau unterstützen Prioritäten und Status, sind aber nie die einzige Information
4. **Mindest-Schriftgröße 14sp** für normalen Inhalt; kleinere Captions nur ergänzend
5. **Dark/Light/HighContrast** — Solar-Berechnung, manueller Override, Emergency-Modus
6. **Textfarbe getrennt von Statusfarbe** — semantische Akzentfarben dürfen den Textkontrast nicht verschlechtern

## Farbpalette

### Prioritäten (Akzent)

| Token | Hex | Bedeutung |
| --- | --- | --- |
| `urgent` | `#DC2626` | Dringend — sofortige Aufmerksamkeit |
| `important` | `#F59E0B` | Wichtig — zeitnahe Bearbeitung |
| `normal` | `#2563EB` | Normal — reguläre Bearbeitung |
| `done` | `#16A34A` | Erledigt — abgeschlossen |

Die Akzentfarbe wird für Punkt, Rand oder Fläche verwendet. Text in Badges/Chips
verwendet `onSurface` bzw. den passenden Material-`on*`-Token statt automatisch
dieselbe Akzentfarbe. Dadurch bleiben auch Amber und Grün auf hellen Flächen gut
lesbar.

### Status

| Token | Hex | Bedeutung |
| --- | --- | --- |
| `statusOpen` | `#2563EB` | Offen |
| `statusInProgress` | `#F59E0B` | In Bearbeitung |
| `statusDone` | `#16A34A` | Erledigt |

### Semantic

| Token | Hex |
| --- | --- |
| `error` | `#DC2626` |
| `success` | `#16A34A` |
| `warning` | `#F59E0B` |
| `info` | `#2563EB` |

### Brand

| Token | Hex |
| --- | --- |
| `primary` | `#0D47A1` |
| `brandHover` | `#082E63` |
| `brandDeep` | `#17343D` |
| `brandAccent` | `#2563EB` |
| `surfaceLight` | `#F7F9FC` |
| `surfaceDark` | `#0B1220` |

Dieselben Werte gelten für die Web-PWA (`core/static/core/app.css`).

## Typography

| Rolle | Größe | Gewicht |
| --- | --- | --- |
| Caption | 12sp | Regular, nur ergänzende Information |
| Body | 14sp | Regular |
| Title | 16sp | Medium |
| Headline | 20sp | SemiBold |
| Display | 28sp | Bold |

## Spacing

| Token | Wert |
| --- | --- |
| `xs` | 4dp |
| `sm` | 8dp |
| `md` | 12dp |
| `lg` | 16dp |
| `xl` | 24dp |
| `2xl` | 32dp |

## Touch-Ziele

Interaktive Primärziele: mindestens **48×48dp**. Nicht interaktive Status-Chips
dürfen kompakter sein, solange sie keine alleinige Interaktionsfläche bilden.

## Komponenten

### PriorityBadge
`lib/ui/priority_badge.dart`
- farbiger Punkt + Rand + ausgeschriebener Text
- Text nutzt kontraststarken Theme-Foreground
- Deutsch/Englisch abhängig von der aktiven App-Locale

### StatusChip
`lib/ui/status_chip.dart`
- Status ausgeschrieben
- farbiger Punkt zusätzlich zum Text
- Text nutzt kontraststarken Theme-Foreground

### CopyIconButton
`lib/ui/copy_button.dart`
- Clipboard + SnackBar-Feedback
- 48dp Minimum

## Themes

### Standard (Solar)
Automatischer Wechsel hell/dunkel nach Sonnenaufgang/-untergang.
Siehe `lib/theme/app_theme.dart` und `lib/theme/solar_theme.dart`.

### HighContrast (Emergency)
`lib/theme/high_contrast_theme.dart` — Schwarz/Weiß mit maximalem Kontrast.
`MaterialApp` setzt `highContrastTheme` / `highContrastDarkTheme`, sobald die
Plattform den System-High-Contrast-Modus meldet. Solar bleibt der Standard.

## Barrierefreiheit

- **Kontrast:** WCAG 2.2 AA als harte Baseline; High-Contrast strenger
- **Touch-Ziele:** 48dp für interaktive Kernaktionen
- **Text-Skalierung:** scrollbare Detailansichten und adaptive Kachelspalten für große Systemschrift
- **Screenreader:** semantische Labels auf Icons und nicht allein farbbasierte Statusinformation
- **Farb-Blindheit:** Punkt/Fläche plus ausgeschriebenes Label
- **Reduced Motion:** keine Information hängt von Animation ab

Manuelle Abnahme mit VoiceOver/TalkBack, 200–400 % Text-/Zoom-Szenarien und
kleinen Displays bleibt Teil der Pilotfreigabe; die Dokumentation behauptet
bewusst keine pauschale AAA-Konformität ohne diese Abnahme.

## Rettungsdienst-spezifische Patterns

1. **Dringend-Badge in Navigation:** Anzahl dringender Übergaben
2. **Große Saldo-Anzeige:** Kaffeekasse-Saldo mit hoher Lesbarkeit
3. **Quick-Access Kacheln:** Dashboard-Module groß und gut tippbar
4. **Offline-Indikator:** sichtbares Banner; echte Lese-Snapshots verschlüsselt und tokengebunden
5. **Demo-Modus Banner:** deutliches Band für Musterdaten
6. **Mängel-Fotos:** explizite Kamera/Galerie-Aktion mit Datenschutz-Hinweis, kein allgemeines Dateiarchiv
