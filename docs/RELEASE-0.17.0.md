# Zwischenrelease 0.17.0

Stand: 19. Oktober 2026. Zweck: Entwicklung, Erprobung und Präsentation.
Keine Produktionsfreigabe, Zertifizierung oder Compliance-Bestätigung.

## Bestandteil

- Bestehende Wachenmodule, versionierte Übergaben und rollenbeschränkte Abläufe.
- Einrichtungsassistent, persönliche Mitarbeiterkonten und einmalige Aktivierung.
- Wiederholbarer QR-Login mit Gerätebestätigung und bestehenden MFA-Anforderungen.
- Optionales Wetter mit kontrolliertem Ausfallverhalten.
- Lokaler Betrieb ohne WAN bei erreichbarem Server und LAN/WLAN.
- Deutsche Textkorrekturen und mitgeliefertes de/en-Sprachfundament für Anmeldung,
  Einrichtung sowie Fehler- und Validierungsmeldungen.
- Statische Projektseite mit lokalen Assets und synthetischen Bildschirmaufnahmen.

## Ausdrücklich nicht Bestandteil

- Vollständig übersetzte Fachmodule, JavaScript/Admin oder zweisprachige Projektseite.
- Integriertes Hilfe-, Wiki- oder technisches Diagnosezentrum.
- Schreibfähiger Handy-Offlinebetrieb ohne Server, Outbox und spätere Synchronisierung.
- Reale iPhone-/Touch-/Passkey-/WebPush-Abnahme oder Freigabe eines Wachenbetriebs.
- Nachweis des produktiven TLS-/Reverse-Proxy-Betriebs, einer produktionsgleichen
  PostgreSQL-Race-Prüfung oder eines betrieblichen Backup-/Restore-Verfahrens.

## Veröffentlichung

README, Produktcode und Projektseite werden gemeinsam geprüft. Vor Veröffentlichung
müssen der eingefrorene Dateistand, vollständige Tests, Katalog-/Migrationsprüfung,
Webseitenprüfung und das abschließende Argon-Review zusammenpassen. Bestätigte
Defekte werden vor Veröffentlichung behoben und nachgetestet. GitHub-CI,
Pages-Deployment und der öffentliche Link werden anschließend separat geprüft.

Diese Veröffentlichung installiert keinen produktiven Wachbuch-Server.
