# Unabhängige Gegenprüfung: AGY und Mistral

## Tatsächlich ausgeführte Prüfungen
- AGY 1.3.2: erster Aufruf mit claude-sonnet-5-5-high lieferte trotz Exit 0 nur eine Startmeldung; kein verwertbarer Review, nicht als Abnahme gezählt.
- AGY mit gemini-3.1-pro-high: erneuter Inline-Aufruf mit vollständigem HTML/CSS/JS und Layoutmessungen lieferte einen substanziellen deutschen Review. Quelltext-/DOM-Prüfung, KEINE behauptete Screenshot-Sichtprüfung.
- Mistral API, mistral-large-4: Katalog bestätigte Vision. Erster kombinierter Request erhielt einen Quellcode-/DOM-Review, behauptete aber fälschlich keine Bilder erhalten zu haben; visuelle Aussagen daraus nicht anerkannt.
- Separater Mistral-Bildrequest mit image_url-Objekten lieferte Bildbeschreibung und UX-Review. Bildlesen durch konkrete sichtbare Beschriftungen plausibilisiert, Aussagen dennoch gegen Browsernachweise abgeglichen.
- SHA256-Vergleich: alle drei Originaldateien und Reviewkopien unverändert. Sieben Viewports im Belegdatensatz. Kein Commit, Push oder Deployment.

## Abgleich mit Elternprüfung
1. Menü außerhalb des Viewports bei 200% Root-Schrift: AGY bestätigt korrekt anhand document_width=412 bei 320/390 px sowie menu.x=281,19 / width=131,17. Mistrals erster Review widerspricht sich und missdeutet diesen Overflow; Browsermessung entscheidet.
2. Alter innerer Scrollstand beim Panelwechsel: AGY und Mistral-Codeprüfung bestätigen fehlenden Reset in show(). Eltern-Browsernachweis bleibt maßgeblich.
3. Smartphone zu spät auf Handy: AGY bestätigt mobile phone.y=875,625 bei 844 px Viewporthöhe. Gestaltungsbefund, kein kaputter Einstieg.
4. Reset vor dem Gerät / optisch abgesetzt: AGY-Codeprüfung und Mistral-Bildprüfung stützen die Kritik. Konkrete Empfehlungen (Toolbar komplett versetzen vs nur Reset unterordnen) sind Designalternativen, keine automatische Änderung.
5. Android/iOS wie klickbare Badges: beide Codeprüfungen bestätigen gleiche Klasse für Link und statische spans. Als irreführende Affordanz bewertet, nicht als defekter Storelink.

## Nicht übernommene Modellbehauptungen
- Negative Bildschirm-y nach Scrollen beweisen keine Überlappung; Mistral-Landscape-Überlappung nicht bestätigt.
- Keine belegte Brand-Mark-Überlappung oder automatisch fehlende flex-Regel; nicht als Bug übernommen.
- Mistrals Aussage, das Gerät wechsle in Querformat, ist kein belegter Produktzustand; Screenshot zeigt den kleinen Viewport mit intern gescrolltem Mockup.
- Sichtbare Menübeschriftung ist nicht generell redundant oder schlecht; Icon-only nicht ungeprüft übernehmen.
- Nicht sichtbare CTA bei großer Schrift im Screenshot sind kein Beweis ihrer Unerreichbarkeit.
- Keine WCAG-Gesamtabnahme, keine realen Geräte, kein Screenreader- oder Storetest.

## Urteil
Die beiden reproduzierbaren P1-Probleme bleiben bestätigt: vergrößerte Navigation und Scrollposition bei Ansichtswechsel. Mobile Produktreihenfolge, Reset-Hierarchie und Plattformaffordanz sind ebenfalls begründete Überarbeitungspunkte. Keine visuelle Freigabe vor Korrektur und erneuter Browserprüfung.

## Rohbelege
/opt/data/cache/presentation-qa/cross-review/: manifest.json, geometry.json, prompt.txt, agy-inline-review.md, mistral-review.md, mistral-vision-review.md, API-Rohantworten und Statusdateien. Diese enthalten keine API-Schlüssel.
