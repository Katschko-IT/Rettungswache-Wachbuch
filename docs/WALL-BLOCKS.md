# Wandbausteine für das Wachbuch

Stand: 31. Juli 2026

Die Fotos der Wandtafeln und laminierten Boegen in der Rettungswache dienen als
fachliche Vorlage. Digitalisiert wird die **Wachenorganisation**, nicht
Dienstplanung und keine Patienten- oder Einsatzdaten.

## Was an der Wand zu sehen ist

| Analog | Bedeutung | Digitaler Baustein |
| --- | --- | --- |
| Gruene Zone | Taegliche Routine (Fahrzeug, Geraete, Hygiene, Kueche, Muell) | Band `daily` |
| Gelbe Zone | Wochentagsrotation (z. B. Material, Desinfektion, Wochenabschluss) | Band `weekday` |
| Weisser Fussbereich | Individuelle / monatliche Zusatzpunkte | Band `extra` (visuell blau) |
| KW + Wochentage | Wochenbogen Mo–So | Ansicht `/aufgaben/woche/` |
| Abhaken / Magnete | Erledigt / offen mit Person und Zeit | `StationTaskCompletion` + Audit |
| Statusfarben Magnettafel | Gruen / Gelb / Rot als Lage | Nur zusaetzlich; Text bleibt Pflicht |

## Farblogik (Vorschlag und Umsetzung)

Farbe ist **nur Hilfsmittel**. Status und Bereich stehen immer ausgeschrieben.

| Farbe | Bereich | Einsatz |
| --- | --- | --- |
| Gruen | Taeglich | Routine, die jeden Tag gilt |
| Gelb / Amber | Wochentag | Fester Wochentag, analog gelber Zeile am Bogen |
| Blau / Petrol | Zusaetzlich | Individuell, monatlich, einmalig – weisse Zone am Papier |
| Rot | Nur Stoerung | Offene kritische Restmenge / Dringendes, nie als Dekoration |
| Neutral | Offen | Noch nicht erledigt |

Bewusst **kein Magenta** aus dem Infoposter als Systemfarbe: es konkurriert mit
Rot/Dringend. Magenta bliebe optional für spätere reine Hinweis-Kacheln.

## App-Bausteine

1. **Heute-Liste** (`/aufgaben/`): Wandtablet-tauglich, drei farbige Bänder,
   Ein-Tap-Erledigt mit Audit.
2. **Wochenbogen** (`/aufgaben/woche/`): Sieben Spalten wie der laminierte Bogen,
   heutige Spalte hervorgehoben.
3. **Vorlage** (`/aufgaben/verwaltung/`): Schichtleitung/Admin pflegt Titel,
   Band, Wochentag und Hinweise.
4. **Standardvorlage**: Beim ersten Aufruf oder Bootstrap werden typische
   Steinhagen-nahe Aufgaben ohne Ortspflicht angelegt und können angepasst
   werden.
5. **Dashboard-Kachel**: Fortschritt `erledigt/gesamt` als Schnellzugriff.
6. **Modulschalter** `tasks_enabled`: Wache kann den Baustein ausblenden.

## Grenzen

- Keine Zuweisung von Dienstschichten oder Personenplänen.
- Keine Fahrzeug- oder Patientendaten in Freitexten.
- Kein Drag-and-drop offline; Erledigungen brauchen Online-Verbindung.
- Magnettafel-Lagebilder und Infoposter-Artikel bleiben außerhalb, bis es einen
  eigenen freigegebenen Zweck gibt.
