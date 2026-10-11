# PWA-Installationshinweis: abschließbares Fenster, keine In-App-Werbung

## Bestätigte Ursachen

1. `.install-banner { display: flex; }` überschreibt die Browser-Standardregel für `hidden`. Damit war der Hinweis trotz `hidden=true` sichtbar; auch „Später“ war optisch wirkungslos. Der Regressionstest gegen den unveränderten Ausgangsstand scheitert mit `AssertionError: Install banner unexpectedly visible`.
2. Gespeicherte Ablehnung wurde nur beim Laden berücksichtigt. Ein späteres `beforeinstallprompt` setzte `hidden=false` ungeprüft zurück.
3. `rwsth-installed` wurde geschrieben, aber nicht ausgewertet. iOS `navigator.standalone` und Änderungen des Anzeige-Modus fehlten.

## Nutzerentscheidung und endgültiges Verhalten

- Innerhalb der App erscheint **kein automatischer Installationshinweis**, auch nicht bei einem nativen Installationsangebot, Seitenwechsel oder Reload. Die App-Shell markiert die Komponente explizit `data-install-manual-only`.
- Bestehende Links auf der neuen Produkt-Hauptseite bleiben unverändert. Keine neuen Storelinks, Downloads oder Installationsbehauptungen.
- Ein vorhandenes/ausdrücklich geöffnetes Fenster besitzt ein echtes **X oben rechts**, unabhängig von der Aktionszeile, mit zugänglichem Namen und mindestens 48×48 CSS-Pixeln.
- Das X schließt dauerhaft in diesem Browserprofil: `rwsth-install-dismissed=permanent`. Frühere „Später“-Zeitstempel werden ebenfalls als dauerhafte Ablehnung respektiert. **Keine Wiedervorlage nach sieben Tagen.**
- Der „Später“-Button entfällt in der App. Legacy-Schließenbuttons bereits ausgelieferter Oberflächen bleiben durch den Handler unterstützt.
- `[hidden]` kann nicht mehr von `display:flex` überschrieben werden.
- Installierter Laufzeitmodus (`standalone/minimal-ui/fullscreen`, iOS `navigator.standalone`) und `appinstalled` blenden sofort aus. Bloßes Akzeptieren eines Prompts ist noch kein Installationsbeweis.
- Storagefehler und abgewiesene native Prompts erzeugen keine unbehandelten JS-Fehler. Bei gesperrtem Storage bleibt die App trotzdem frei von automatischen Installationshinweisen.
- Keine Geräteinventur, Server-Telemetrie oder zusätzliche Bibliothek.

## Ausgeführte Prüfung

`node --check core/static/core/app.js`: erfolgreich.

`scripts/test_install_prompt_browser.py`: **27 Checks erfolgreich**, echte JS/CSS-Dateien sowie das tatsächliche Banner-Markup aus `base.html` in Chromium. Prüft u.a. keine automatischen Vorschläge in der neuen App-Shell, dauerhafte Ablehnung über wiederholte Ereignisse/Reload, Installations-Modi/iOS, Tab-Synchronisation, gesperrten Storage sowie die X-Position bei 320/390/1280px mit mindestens 48px Touchziel. Keine unbehandelten JS-Fehler.

Die nativen Installationsereignisse und Anzeige-Modi sind gezielt simuliert. Dies ist **kein** Nachweis einer physischen OS-Installation auf Android/iOS. Die Änderung ist lokal geprüft, noch nicht veröffentlicht; öffentliche Abnahme erfolgt mit dem vollständigen App-Redesign-Release.

## Plattformgrenzen / Quellen

Safari/iOS bietet `beforeinstallprompt` und `appinstalled` nicht an. In der installierten Home-Screen-App ist `navigator.standalone` erkennbar. Ein normaler Safari-Tab kann nicht allgemein feststellen, ob dieselbe PWA bereits auf dem Home Screen liegt. Browserprofile, Deinstallation und gelöschter Storage verhindern eine universelle OS-Installationsabfrage. Es wird daher nie auf Verdacht In-App-Werbung eingeblendet.

- https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeinstallprompt_event
- https://developer.mozilla.org/en-US/docs/Web/API/Window/appinstalled_event
