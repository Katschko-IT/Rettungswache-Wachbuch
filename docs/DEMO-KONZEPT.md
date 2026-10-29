# Konzept: Öffentliche Demo von Wachwerk

Stand: 29. Oktober 2026. Ergänzt [DEMO.md](DEMO.md) (Technik und Betrieb).

## Ziel

Wer sich für Wachwerk interessiert – Wachleitung, Praxisanleitung,
Kolleginnen und Kollegen, IT oder Datenschutz eines Trägers – soll in
**fünf bis zehn Minuten** erleben, wie ein Schichtwechsel mit Wachwerk
abläuft. Danach soll klar sein, wie man es auf der eigenen Wache betreibt.

## Recherche: Was eine gute Demo ausmacht

Die Quellen sind überwiegend Blogs von Anbietern solcher Werkzeuge. Die
Zahlen sind deshalb Richtwerte, keine unabhängig geprüften Studien.

| Erkenntnis | Quelle | Umsetzung in Wachwerk |
| --- | --- | --- |
| Geführte Touren erklären, Sandboxes lassen frei ausprobieren; beides ergänzt sich. | [Guideflow](https://www.guideflow.com/blog/interactive-demos-vs-sandboxes), [Guideflow Sandbox](https://www.guideflow.com/blog/sandbox-demo-best-practices-sales-teams) | Eigene Demo-Wache je Besuch (Sandbox) **plus** Rundgang mit sechs Aufgaben. |
| Vorher zwei bis drei „Aha-Momente“ festlegen und sie zuerst zeigen. | [Navattic](https://www.navattic.com/blog/best-practices-building-interactive-demos) | Einstieg landet auf der Übersicht „5 Punkte brauchen Aufmerksamkeit“; danach Übergabe, Quittierung, Gerätenachweis. |
| Kurze Touren werden zu Ende gemacht: drei Schritte etwa zwei Drittel, ab fünf bis sieben Schritten deutlich weniger. | [Chameleon Benchmark](https://www.chameleon.io/blog/chameleon-benchmark-report), [Produktly / Indie Hackers](https://www.indiehackers.com/post/onboarding-benchmarks-from-real-data-across-464-saas-products-median-tour-completion-is-29-6288651c93) | Sechs Aufgaben, die erste ist schon erledigt; jede Aufgabe dauert unter einer Minute. |
| Selbst gestartete Touren schneiden deutlich besser ab als automatisch aufpoppende. | [Produktly / Indie Hackers](https://www.indiehackers.com/post/onboarding-benchmarks-from-real-data-across-464-saas-products-median-tour-completion-is-29-6288651c93) | Kein Pop-up. Der Rundgang ist eine ruhige, einklappbare Karte auf der Übersicht; jede Aufgabe hat einen „Los“-Knopf. |
| Checklisten mit 3–7 Punkten und Fortschrittsanzeige erhöhen den Abschluss. | [Supademo](https://supademo.com/blog/product-onboarding-checklist), [Design Revision](https://designrevision.com/blog/saas-onboarding-best-practices.md) | Fortschrittsbalken „x von 6“, Haken erscheinen automatisch, sobald die Aufgabe erledigt ist. |
| Bekannte Open-Source-Projekte setzen Demos nach einer Stunde bzw. wenigen Stunden zurück. | [Nextcloud-Demoserver](https://bayton.org/blog/2017/02/introducing-nextcloud-demo-servers/), [Odoo](https://www.odoo.com/documentation/saas-16.1/es/administration/install/online.html) | Löschung beim Abmelden, nach 30 Minuten Leerlauf, spätestens nach 2 Stunden. |
| Selbst-Hosting gelingt Laien, wenn ein Skript Voraussetzungen prüft, es einen einfachen und einen ausführlichen Weg gibt und Rechte/Ressourcen klar genannt sind. | [n8n](https://docs.n8n.io/deploy/host-n8n/install-options/one-line-setup), [SysReptor](https://docs.sysreptor.com/setup/installation), [Plausible](https://git.bbaovanc.com/github.com/plausible-hosting/commit/a0191a692479612aa6efc865d311bbf029bdb557) | Seite „Selbst betreiben“: drei Wege, Voraussetzungen als Tabelle, fünf Schritte, „Wenn etwas hakt“; Verweis auf die ausführliche Doku. |
| Nach der Demo braucht es einen klaren nächsten Schritt. | [Navattic](https://www.navattic.com/blog/best-practices-building-interactive-demos) | Nach dem Rundgang und nach dem Abmelden: „Wachwerk selbst betreiben“ und „Neue Demo starten“. |

## Der Use Case: „Dein erster Schichtwechsel“

Geschichte: Du übernimmst die Demo-Wache Musterstadt zum Schichtwechsel.

1. **Übersicht lesen** – schon erledigt: Fünf Punkte brauchen Aufmerksamkeit.
2. **Übergabe anlegen** – „Sauerstoff RTW 2 fast leer“, dringend.
3. **Als Kollegin quittieren** – im Banner zur Rolle „Mitglied“ wechseln,
   Übergabe als gelesen bestätigen. Zeigt Rollen und Nachweis.
4. **Medizingerät prüfen** – Funktionskontrolle eintragen; der Nachweis für
   die Prüfung entsteht nebenbei.
5. **Mangel melden** – mit Frist und verantwortlicher Person.
6. **Kaffeekasse** – „Ich habe bezahlt“; der Monat ist sofort abgehakt.

Erkannt wird jede Aufgabe an echten Einträgen in der eigenen Demo-Wache, die
nach dem Anlegen der Musterdaten entstanden sind (`DemoSandbox.ready_at`).
Es gibt kein Tracking und keine Zählung außerhalb der Demo-Wache.

Für unterschiedliche Zielgruppen:

- **Wachleitung / QM:** Schritte 1, 4 und die Seite „Nachweise“ (Bestandsverzeichnis, Lesebestätigung).
- **Kolleginnen und Kollegen:** Schritte 2, 3 und 6.
- **IT / Datenschutz:** Seite „Selbst betreiben“, Quellcode, Insellösung, keine Patientendaten.

## Checkliste vor dem Freischalten

- [ ] Eigener Server, Subdomain mit gültigem Zertifikat (`--mode domain`).
- [ ] `DEMO_MODE=true`, `DEMO_SANDBOX=true`, `COMPOSE_PROFILES` enthält `demo`.
- [ ] Einrichtungsassistent mit eigenem Betreiberkonto durchlaufen; Impressum vollständig, „Öffentlich im Internet erreichbar“ angekreuzt.
- [ ] Kein `EMAIL_HOST`/`SIGNAL_*` nötig – in der Demo ohnehin abgeschaltet.
- [ ] Probelauf: Demo starten, Rundgang durchklicken, abmelden; nach einer Minute ist die Demo-Wache weg (`docker compose logs demo-cleaner`).
- [ ] Am Handy und am Rechner geprüft, hell und dunkel.
- [ ] Auf der Hauptseite (z. B. rwsth.de) einen Link „Demo ausprobieren“ setzen.

## Bewusst nicht umgesetzt

- **Besucherstatistik:** Keine Zählpixel und keine Analyse-Dienste. Stattdessen
  zählt `core/demo_stats.py` je Tag nur drei Zahlen: gestartete Demos,
  abgeschlossene Rundgänge (gezählt beim Löschen der Demo-Wache, für den
  Starttag) und Rückmeldungen – ohne IP-Adresse, Konto, Token oder Bezug zu
  einer Demo-Wache. Master-Admins echter Wachen sehen sie im
  Feedback-Posteingang („Demo-Kennzahlen“, dazu „Gerade aktiv“ und die
  Durchschnittsbewertung), auf dem Server zeigt sie
  `python manage.py demo_stats --tage 30`. Die Startseite nennt laufende Demos
  erst ab drei („Gerade aktiv: N Demo-Wachen“, 60 s zwischengespeichert).
- **„Tab geschlossen“ erkennen:** Browser melden das nicht zuverlässig.
  Stattdessen enden Sitzungs-Cookie und Demo über Fristen.
