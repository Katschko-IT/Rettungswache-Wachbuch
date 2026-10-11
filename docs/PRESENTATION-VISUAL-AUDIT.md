# Visuelle UX-Prüfung der lokalen Bootstrap-Fassung

## Umfang und Methode
Geprüft wurde der frisch aus dem aktuellen Django-Template exportierte lokale Build, nicht die unveränderte öffentliche Vorschau. Keine Änderung von Produktcode, kein Deployment.

Viewports: 320×740, 390×844, 768×1024, 960×900, 992×900, 1440×1000 sowie 844×390 (Querformat). Für jeden Viewport wurden Hero, ganze Seite und Demo gerendert, DOM-Positionen und Kontrollgrößen gemessen sowie Szenariowechsel ausgeführt. Zusätzlich wurde die Root-Textgröße auf 200% gesetzt; das ist eine Textvergrößerungsprüfung, keine Behauptung über einen echten Browser-Zoom oder reale Geräte.

Reproduzierbare Belege: /opt/data/cache/presentation-qa/visual_audit.py; visual-audit/geometry.json; Screenshots im gleichen Ordner. Visuelle Modellbefunde wurden gegen DOM-Messungen geprüft, nicht ungeprüft übernommen.

## P1 — Vergrößerte Schrift schneidet mobile Navigation ab
Bei 320 und 390 Pixeln Breite wird das Dokument bei doppelter Root-Schriftgröße 412 Pixel breit. Der Menü-Button beginnt bei x=281,19 und endet bei x=412,36. Die Kopfzeile ist nicht umbruchfähig; der sichtbare Bildschirmrand wird überschritten.

Korrektur: Kopfzeile mit robustem Umbruch/zweiter Zeile oder kompakter Navigation gestalten; Außenabstände bei großen Schriftgrößen begrenzen. Nicht mit overflow-x:hidden kaschieren. Regression: Menü-Rechteck muss vollständig im Viewport bleiben.

## P1 — Szenariowechsel behält die innere Scrollposition
Nach Herunterscrollen der Übersicht und Öffnen der Übergabe bleibt im Querformat scrollTop=241 statt 0; bei 320 Pixeln bleiben 25 Pixel. Dadurch beginnt die neue Ansicht nicht mit Titel und Revision. Die Kenntnisnahme ist zwar bedienbar, aber der notwendige Kontext liegt oberhalb des sichtbaren Ausschnitts.

Korrektur: innere Smartphone-Scrollposition bei jedem Ansichtswechsel gezielt auf den Anfang setzen. Regression mit kleinem Viewport und vorherigem Scrollen, nicht nur mit frisch geladenem Panel.

## P2 — Die Demo erscheint auf dem Handy zu spät
Initial beginnt der Smartphone-Rahmen bei 390×844 erst bei y=876; bei 320×740 bei y=942. Haupt-CTA, zweite CTA, Meta-Erklärung, Plattform-Badges, Storehinweis, Szenariowahl und Reset liegen davor. Nach Klicken auf den Demo-Anker ist das Smartphone erreichbar; es handelt sich um Reihenfolge/Präsentation, nicht um einen kaputten Link.

Korrektur: Plattforminformationen weiter nach unten; Text und Demo-Steuerung straffen. Hauptaktion nah an das Produkt; nicht jeden Hinweis in einen eigenen Block verwandeln.

## P2 — Reset ist zu prominent und steht vor dem Produkt
Reset steht im Handy-Hero bei y=807 bzw. y=874 noch vor dem Smartphone. Auf Desktop sitzt er neben dem Szenarioblock und konkurriert mit der Auswahl. Ein Reset ist eine nachgeordnete, potenziell unbeabsichtigt betätigte Aktion.

Korrektur: ruhiger Textbutton unter dem Gerät oder am Ende der Demo; keine Gleichstellung mit Einstieg/Navigation.

## P2 — Plattformen haben falsche Bedienaffordanz
GitHub ist ein Link; Android/iOS sind spans. Alle drei verwenden dieselbe pw-platform-Buttonoptik mit Rahmen, Hintergrund und 48-Pixel-Fläche. Die nicht klickbaren Plattformlabels sehen wie Downloadaktionen aus.

Korrektur: Android/iOS als schlichte Symbol-/Textzeile anzeigen; nur echte Aktionen wie GitHub als Link gestalten. Keine erfundenen Storelinks.

## P3 — Logo-Link als Touchziel zu klein
Normal gerendert ist der Logo-Link 38 Pixel hoch; die übrigen gemessenen sichtbaren Kontrollen erreichen mindestens 44 Pixel. Korrektur: Logo-Link auf mindestens 48 Pixel Klickhöhe erweitern, ohne das Logo selbst größer machen zu müssen.

## Positive Befunde / Grenzen
- Keine horizontal abgeschnittenen gemessenen Kontrollen bei normaler Schriftgröße in den sieben Viewports.
- Handy-Hauptaktion steht vor der sekundären Aktion; gleiche volle Breite in der bisherigen Browserregression bestätigt.
- Alle drei lokalen SVGs laden. GitHub-Ziel ist das tatsächliche Projekt.
- Kein belegter Überlappungsfehler der vier Nummerierungen; entsprechende visuelle Modellvermutungen sind nicht als Bug übernommen.
- Die Funktionstests belegen Bedienabläufe, nicht eine vollständige visuelle, WCAG- oder Geräteabnahme.

## Urteil
Visuell noch keine uneingeschränkte Freigabe. Erst die beiden P1-Befunde beseitigen, dann mobile Reihenfolge/Reset/Plattformaffordanzen korrigieren und diese gleichen Rendergrößen erneut prüfen. Öffentliche Demo und öffentliche Vorschau wurden durch diese Prüfung nicht geändert.
