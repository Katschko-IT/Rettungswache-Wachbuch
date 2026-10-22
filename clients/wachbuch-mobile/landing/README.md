# Wachbuch Landingpage & Webapp

Statische Projekt-Vorstellung plus vollwertige Web-Demo für
Rettungsdienst, Feuerwehr und Polizei — im selben Design-System.

## Lokal ansehen

```bash
cd landing
python3 -m http.server 4173
# Landing:  http://127.0.0.1:4173/
# Webapp:   http://127.0.0.1:4173/app/
```

### Landing Deep-Links

- `/?demo=rettungsdienst`
- `/?demo=feuerwehr`
- `/?demo=polizei`

### Webapp Deep-Links

- `/app/?service=rettungsdienst`
- `/app/?service=feuerwehr`
- `/app/?service=ffw`
- `/app/?service=polizei`

Die Webapp enthält Übersicht, Übergaben, **Mängel**, **Geräte/Statusboard**,
Quittierung, Kalender, Kaffeekasse, Checklisten und Konto — offline mit
Musterdaten (Fahrplan Phase A–D).

Fachlicher Fahrplan: [`docs/FAHRPLAN-BEHOERDEN.md`](../docs/FAHRPLAN-BEHOERDEN.md).

## Mobile App-Demo

In der Mobile-App: Startbildschirm → **Demo-Modus ausprobieren**.
Dort stehen dieselben drei Organisationsprofile als Offline-Musterdaten bereit.
