# Vorlagen- und Symbolquellen

## Reale Vorlage statt freier Marketing-Komposition
Ausgewählte Grundlage: offizielles Bootstrap-Product-Beispiel aus Version 5.3.8 (MIT).
- Vorschau: https://getbootstrap.com/docs/5.3/examples/product/
- Original: https://github.com/twbs/bootstrap/blob/v5.3.8/site/src/assets/examples/product/index.astro
- Original-CSS: https://github.com/twbs/bootstrap/blob/v5.3.8/site/src/assets/examples/product/product.css
- Bootstrap-CSS: https://github.com/twbs/bootstrap/blob/v5.3.8/dist/css/bootstrap.min.css

Die Vorlage wird für die existierende Django-Seite und lokale Smartphone-Vorschau adaptiert. Keine Übernahme der Demo-Texte, Platzhalterlinks, fiktiven Käufer oder Verkaufspreise. Bootstrap wird lokal ausgeliefert, nicht über ein CDN.

## Offizielle Flutter-Plattformsymbole
Android und iOS nutzen exakt die Glyphen der mit Flutter 3.47.7 ausgelieferten MaterialIcons-Regular.otf, keine nachgezeichneten Logos.
- Android: Icons.android, Codepoint 0xe085.
- iOS/Apple: Icons.apple, Codepoint 0xf04be.
- Dokumentation: https://api.flutter.dev/flutter/material/Icons/android-constant.html und https://api.flutter.dev/flutter/material/Icons/apple-constant.html
- SVG-Pfade wurden mit fontTools 4.66.1 aus den Originalglyphen exportiert; die Y-Achse wird für SVG invertiert. Die zugehörige MaterialIcons-Lizenz liegt neben den SVGs.
- GitHub-Symbol: Bootstrap Icons 1.13.1 (MIT); lokale Lizenzdatei erhalten.

Plattformlogos sind keine Downloadbuttons. Solange es keine veröffentlichten Store-Einträge gibt, werden keine Google-Play-/App-Store-Links oder entsprechende Verfügbarkeitsversprechen eingefügt.
