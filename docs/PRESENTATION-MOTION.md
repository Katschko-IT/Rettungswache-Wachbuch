# Präsentationsanimationen

Die lokale Vorschau ergänzt die geprüfte Bootstrap-Fassung ohne weitere Bibliotheken:
- Abschnitts-Reveal mit 14 Pixeln Bewegung und 450 ms Übergang.
- Smartphone-Ansichtswechsel mit 280 ms Einblenden.
- Opt-in-Rundgang durch Übersicht, Übergabe, Aufgaben und Kalender. Jede Ansicht bleibt 6,5 Sekunden stehen; nach einem Durchlauf stoppt er.
- Manuelle Bedienung, Tab/Escape, Touch/Scroll im Gerät, unsichtbarer Browser-Tab oder Verlassen der Demo stoppen den Rundgang. Kein automatischer Neustart.
- Keine automatischen Kenntnisnahmen, Aufgabenänderungen oder Speicherung.
- Reduced Motion schaltet CSS-Bewegung ab; ein ausdrücklich gestarteter Rundgang darf weiterhin statisch die Ansichten wechseln.
- Ohne JavaScript wird die Rundgangsteuerung ausgeblendet, die Inhalte bleiben zugänglich.

Nachweise:
- Erweiterte Browserregression in scripts/test_presentation_browser.py: sieben Viewports, 200%-Text, kontrollierter Browserclock-Test für Start/Stopp/Ende/manuelle Unterbrechung.
- Zusätzlicher tatsächlicher 26-Sekunden-Durchlauf mit normaler Bewegung: /opt/data/cache/presentation-qa/motion-proof/result.json; vier Screenshots im selben Ordner.
- 182 Django-Tests erfolgreich, ein Skip.
- Kein Anspruch auf vollständige WCAG- oder physische Geräteabnahme.
