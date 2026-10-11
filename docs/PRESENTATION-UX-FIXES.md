# Abnahme der UX-Korrekturen

## Umsetzung
- Header darf bei großer Schrift umbrechen; mobiles Dropdown bleibt innerhalb der Kopfzeilenbreite.
- Ansichtswechsel setzt die innere Smartphone-Scrollposition auf null.
- Reset steht als Textaktion unter dem Gerät. Plattformhinweise folgen dem Produkt; Android/iOS sind keine Scheinbuttons.
- Mobiler Hero ist kompakter. Systemgrenzen bleiben im FAQ ausdrücklich erhalten.
- Umbruch bei vergrößerter Schrift gilt auch für lange Texte und Demo-Aktionen; Logo-Klickhöhe mindestens 48 px.

## Tatsächlich ausgeführte Tests
- Neuer Regressionstest scheiterte am alten Export mit `Reset must follow device`.
- Frischer Export: sieben Browsergrößen bestanden, einschließlich 320/390/768/960/992/1440 px und 844x390 Querformat.
- Erweiterte Assertions: Geräteposition, Reset-Reihenfolge, Plattformlabels, Menü/Links bei 200% Root-Schriftgröße, Seitenausdehnung und Demo-Kontrollgrenzen, Scrollreset nach vorherigem Scrollen.
- Revisionen, Kenntnisnahme/Aufgabentrennung, Tastatur, FAQ, Reduced Motion, No-JS und keine XHR/Storage-Nutzung weiterhin bestanden.
- Django: 181 Tests, OK, ein Skip. Node-Syntax und git diff --check bestanden.
- Root-Schriftvergrößerung ist kein echter Browserzoom und keine vollständige WCAG-Abnahme.

## Layoutnachweis
- 390x844: Smartphone beginnt bei y=623.6 statt zuvor 875.6.
- 320x740: Smartphone beginnt bei y=651.7 statt zuvor 942.5.
- Alle sieben Größen: innere Scrollposition nach Wechsel null; Dokumentbreite bei 200% entspricht Viewportbreite.
- Reset liegt unter dem Gerät. Keine gemessenen horizontalen Kontrollüberläufe bei normaler Schrift.

## Belege und Grenzen
Logs: /opt/data/cache/presentation-qa/ux-browser.log, ux-django.log, ux-negative.log und ux-visual.log.
Screenshots und Messungen: /opt/data/cache/presentation-qa/visual-audit/.
AGY/Mistral-Gegenprüfung dokumentiert den vorherigen Stand, nicht eine erneute Modellabnahme nach diesen Korrekturen.
Geschützte öffentliche Demo wird nicht geändert. Öffentliche Vorschau-Abnahme wird separat nach erfolgreicher Veröffentlichung dokumentiert.
