# Wave-3-Abnahmen: Readiness-Bewertung

> **Abgelöst** am 30.10.2026 durch [ROADMAP.md](ROADMAP.md). Diese Datei bleibt als Verlauf erhalten.

Stand: 10. Oktober 2026. Bewertung der Abnahme-Readiness für die offenen
Roadmap-Items R-015 bis R-020 (REMEDIATION-ROADMAP-2026-08.md). Diese
Bewertung ersetzt keine Abnahme; sie benennt, was vor der jeweiligen
Abnahme erledigt oder bereitgestellt werden muss.

> **Keine Produktionsfreigabe:** Diese Bewertung ersetzt weder eine externe
> Abnahme noch `GO-LIVE-CHECKLIST.md`. Die ModSecurity-Beispielregeln in
> `docs/DEPLOYMENT.md` sind ungeprüfte Betriebsbeispiele und kein Nachweis
> einer aktiven oder abgenommenen WAF. Vor Nutzung sind insbesondere die
> CRS-Ausnahmen und die Admin-Zugriffskontrolle extern zu prüfen.

## Bewertungsmatrix

| Item | Abnahme | Readiness | Begründung |
|---|---|---|---|
| R-015 | Externer Pentest / ASVS-L2 | **Hoch** | Sicherheits-Regressionstests als CI-Gate, CSP ohne unsafe-inline, MFA/Passkeys, Rate-Limiting DB-backed, Token-API versioniert + OpenAPI. Angriffsfläche ist dokumentiert (docs/SECURITY-PRIVACY.md, ASVS-L2.md). Pentester kann sofort starten; Scope-Liste existiert in der Roadmap |
| R-016 | Monitoring + Incident-Probe | **Mittel** | /healthz, Correlation-IDs, strukturierte Request-Logs (wachbuch.requests), Gunicorn- und Postgres-Tuning vorhanden. Fehlt: Alarmierung (kein definiertes Alert-Backend), Health-Dashboard, Incident-Runbook existiert aber ist ungetestet |
| R-017 | Offsite-Backup + Restore-Nachweis | **Mittel** | backup/restore-Skripte, Least-Privilege-Backuprolle (R-010), Restore-Test-Container in docker-compose vorhanden. Fehlt: verschlüsseltes Offsite-Ziel, dokumentierte RPO/RTO, automatisierter Restore-Nachweis |
| R-018 | Barrierefreiheitsabnahme | **Mittel** | High-Contrast-Theme (Web + App folgt prefers-contrast), Design-System-Regeln, Fokus-Verbesserungen R-008. Fehlt: Screenreader-Test (NVDA/VoiceOver), 400-%-Zoom-Reflow-Nachweis, Abnahme durch reale Nutzer |
| R-019 | Last- und Resilienztest | **Mittel-hoch** | DB-Indexes (Migration 0020), Redis-Cache, Gunicorn-Worker-Tuning, Rate-Limits. Fehlt: definierter Lasttest (k6/locust o.ä.), Messung unter großem Team, DB-Ausfall-Wiederanlauf-Nachweis |
| R-020 | E2EE-Schlüsselverifikation | **Mittel (Teil)** | Fingerprints/Sicherheitsnummern sind umgesetzt: Chat-Schlüssel-Fingerprints (R-020 Teil 1) und Sicherheitsnummer im Web-Crypto-Setup (R-020 Teil 3). Offen bleibt die externe Abnahme sowie QR-Verifikation, Key-Change-Warnungen/ Schlüsselverzeichnis und ein signierter nativer Client mit reproduzierbaren Builds |

## Empfohlene Reihenfolge

1. **R-017 zuerst** – Backup ist die grundlegendste Versicherung und am
   schnellsten mit vorhandener Infrastruktur umsetzbar (Skripte existieren).
2. **R-016 parallel** – Alarmierung auf Basis der vorhandenen Logs/healthz
   ist ein begrenzter Engineering-Aufwand und dehnt sich nicht in die
   Fachlogik aus.
3. **R-015 als nächstes** – externe Prüfung profitiert davon, dass R-016/R-017
   bereits Stands haben; Scope-Liste steht, keine Blocker im Code.
4. **R-019** – nach R-015, damit Erkenntnisse des Pentests in den Lasttest
   einfließen.
5. **R-018** – parallel zu R-019 möglich; Nutzer aus dem Wachbetrieb
   einbinden (siehe GO-LIVE-CHECKLIST).
6. **R-020 zuletzt** – konzeptionelle Arbeit (Fingerprint-/QR-Design,
   reproduzierbare Builds), kein Abnahme-Blocker für Pilotbetrieb, aber
   notwendig für das langfristige E2EE-Vertrauensmodell.

## Vorbedingungen je Abnahme (kompakt)

- **R-015**: Testfenster + Staging-Instanz mit realitätsnahen Daten;
  Scope-Definition aus der Roadmap als Vertrag.
- **R-016**: Alert-Kanal (z.B. Healthchecks auf /healthz, Log-Alarmierung
  auf ERROR-Rate), Incident-Runbook-Trockenübung mit Zeitmessung.
- **R-017**: Offsite-Ziel (verschlüsselt, z.B. Object Storage/Borg-Repo),
  RPO/RTO-Vorgabe vom Betreiber, automatisierter Restore in frischer
  Compose-Umgebung mit Assert auf Fachdaten.
- **R-018**: Testgeräte (Windows + NVDA/JAWS, iOS + VoiceOver), Checkliste
  aus ROADMAP-Item, mindestens zwei reale Nutzer.
- **R-019**: Lasttest-Werkzeug, definiertes Szenario (Wachgröße, Chat- und
  Auditvolumen), Erfolgskriterien (p95-Latenz, Fehlerquote).
- **R-020**: Fingerprint-Format und Web-Sicherheitsnummer sind bereits
  umgesetzt (Teil 1 + 3). Für die Abnahme fehlen explizit: **Web-QR-Abgleich**
  der Sicherheitsnummer, **Key-Change-Warnungen** samt Schlüsselverzeichnis,
  Konzeptentscheidung zur Build-Reproduzierbarkeit eines signierten nativen
  Clients sowie die **externe, unabhängige Abnahme** dieser Restpunkte.
