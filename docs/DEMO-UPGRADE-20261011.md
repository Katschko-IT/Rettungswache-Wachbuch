# Update der öffentlichen Demo

Der Branch verbindet `feature/presentation-smartphone` (0bc6c896b36292f3ec8f14b98c2ae098821ad992, einschließlich der aktuellen main-Historie) mit `demo/wachleitung` (de6324b). Die öffentliche Demo behält ihren Login und die bestehenden Verwaltungs-/Registrierungs-/Egress-Sperren. Die neue Landing zeigt keinen passwortlosen Demo-Einstieg.

Vorabprüfung: gesamte Django-Suite mit temporärer Testdatenbank: 325 Tests, OK, ein Skip. `makemigrations --check --dry-run`: keine Änderungen. Konflikte in Settings wurden durch Erhalt von Produktions-Templatecache und Public-Demo-Guard gelöst.

Datenbewahrung: laufende SQLite-Datenbank mittels SQLite-Backup-API sichern; bestehende Nutzer und alle core-Tabellen nach Migration anhand ihrer bisherigen Spalten unverändert nachweisen. Startup der bestehenden Instanz ohne `load_demo_data`, damit kein erneutes Seeding Accounts/Daten überschreibt. Migration zuerst auf isolierter Kopie erproben. Vor Deploy Image und Compose als Rückweg sichern.

Die mobile Produktvorschau bleibt eine separate statische Instanz. Releasebelege, tatsächliche Images und Backup-Pfade werden nach Deployment im Betriebsverzeichnis dokumentiert. Keine Store-Veröffentlichung oder Änderung der Firewall/Proxy-Routen.
