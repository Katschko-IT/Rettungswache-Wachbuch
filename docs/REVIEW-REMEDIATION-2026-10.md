# Review-Reparatur 2026-10 – Server 0.21.0

Ausgangspunkt: Mistral-Large-4-Review auf `9f87115`, gegengeprüft durch Gemini 3.8 Flash High und DeepSeek v4 Pro. Danach Reparatur durch dieselben zwei Modelle in getrennten Lanes.

## Rollen

- Gemini: R1 (Verkehrs-/NINA-Fetcher), R2 (KDF-Eingabeprüfung) und deren Regressionstests.
- DeepSeek: R3 (Upload-Limitmeldung), R4 (RSS-Artikel-URL), R5 (ICS-Zeitzone) und deren Regressionstests.
- Parent: Vertrag, Abnahmetests, Patch-Anwendung, Ausführung aller Tests, Integration, Dokumentation.

Die Modelle haben **keine Tools** benutzt und keine Dateien selbst geschrieben; sie lieferten strukturierte Ersetzungen, die der Parent allowlist-geprüft, syntaxgeprüft und erst dann in je eine isolierte Lane geschrieben hat. Das ist Modell-Codegenerierung mit kontrollierter Anwendung — kein behaupteter nativer Tool-Schreiblauf.

## Was tatsächlich behoben wurde

- **R1** `core/traffic.py`: eigener Opener ohne Redirect-Verfolgung; HTTP-Redirects führen zu `TrafficUnavailable` statt zu einer zweiten Anfrage. URL-Prüfung erzwingt HTTPS, Allowlist-Host, Port 443/None und verbietet Userinfo. NINA nutzt denselben Opener. Größenlimit, Timeout und TLS-Zertifikatsprüfung unverändert.
- **R2** `core/secure_views.py`: nicht-objektförmiges JSON und nicht konvertierbare `kdf_iterations` liefern 400. Zusätzlich während der Abnahme entdeckt und behoben: `1e999` wird von Python als `inf` geparst und löste einen `OverflowError` mit HTTP 500 aus; jetzt werden nicht-endliche Werte und `OverflowError` abgewiesen. Default (`None`, leerer String) und Grenzen 100.000–1.000.000 bleiben.
- **R3** `core/api/wachalltag.py`: Fehlermeldung nennt das tatsächliche 5-MiB-Eingabelimit; 2-MiB-Ziel der Bildbereinigung unverändert.
- **R4** `core/feed_sync.py`: ungültige Ports, syntaktisch defekte URLs und Nicht-String-Eingaben werden verworfen, statt die Quellenverarbeitung abzubrechen. Gültige Links bleiben unverändert; keine Redirect-/Host-Prüfung abgeschwächt.
- **R5** `core/waste_sync.py`: TZID (auch quoted) wird ausgewertet, unbekannte und **explizit leere** Zeitzonen lösen `ValueError` aus statt still lokaler Zeit; UTC, DATE und naive Lokalzeit bleiben kompatibel.

Zusätzlich entdeckte die gegenseitige Endprüfung zwei weitere echte Lücken (fehlende Typabsicherung in `safe_item_url`, stiller Lokalzeit-Fallback bei `TZID=""`), die DeepSeek nachgebessert hat.

## Abnahmebelege

- Parent-Abnahmetests `core/test_review_acceptance.py`: vor den Fixes **rot** (11 Fehler/1 Fehler beim bestätigten Baseline-Lauf), nach den Fixes **grün**.
- Ergänzender Parent-Edge-Test `core/test_review_input_edges.py` für `1e999`: vor dem Zusatzfix rot (500), danach grün.
- Provider-Regressionstests: `core/test_review_gemini_fixes.py` und `core/test_review_deepseek_fixes.py`, gemeinsam mit den Parent-Tests zuletzt **39 Tests grün**.
- Gezielte Lane-Abnahme nach Integration: **60 Tests grün**; nach den Endkorrekturen **27 Tests grün** im Randfall-Set.
- Strukturgates: `makemigrations --check --dry-run` „No changes detected“, `manage.py check` ohne Befund, i18n-Katalog „vollstaendig und konsistent“, `git diff --check` ohne Whitespace-Fehler.
- Echte, nicht erfundene Netzprüfung des gehärteten Fetchers: Autobahn A33 lieferte 11.682 Bytes, NINA 8 Einträge — beide `success`.
- Vollsuite auf dem integrierten Stand: **838 Tests, alle grün (4 skipped)** in 548 s. Zum Vergleich dieselbe Suite auf dem unveränderten Ausgangsstand: 790 Tests grün. Die Differenz sind die neuen Provider- und Parent-Regressionstests.

## Bewusste Grenzen

- Keine unabhängige Live-Penetration, keine PostgreSQL-Concurrency-, Browser- oder Lasttests.
- Die Modelle haben keine Tests ausgeführt; alle Testläufe sind Parent-Läufe in No-Network-Containern mit synthetischen SQLite-Fixtures.
- Die Gegenprüfungen bezogen sich auf die tatsächlich gelieferten Dateien, nicht auf das gesamte Repository.
- Kein Commit, kein Push, kein Deploy. Änderungen liegen ausschließlich im Arbeitsbaum `/opt/data/workspace/wachwerk-remediation-integration-20261021`.

## Abhängigkeitskorrektur für den CI-Audit

Der CI-Job `django` scheiterte nicht an diesen Änderungen, sondern am `pip-audit`-Schritt mit neun gemeldeten Schwachstellen in `certifi` und `Pillow`. Dieselbe Prüfung war auf `main` bereits rot.

- `certifi` 2026.7.22 → **2026.10.19** (behebt PYSEC-2026-4320)
- `Pillow` 12.3.0 → **13.0.0** (behebt acht CVE-2026-Einträge, darunter CVE-2026-112395/112397/112400/112404/112895/112896/112897/112899)
- `requirements.lock` und `requirements-audit.lock` gezielt aktualisiert; übrige Pins unverändert.
- Zwei fehlerhafte Hash-Zeilenumbrüche im bestehenden `requirements.lock` repariert (fehlender Backslash), die eine Neukompilierung mit `uv` verhinderten.

Nachweis: `pip-audit --strict --requirement requirements.lock` meldet **„No known vulnerabilities found"** (Exit 0), mit `--require-hashes` aus `requirements-audit.lock` installiert. Docker-Build erfolgreich; Vollsuite im gebauten Image mit Pillow 13: **838 Tests grün (4 skipped)**.

Hinweis: Eine vollständige Neukompilierung des Locks würde zusätzlich `packaging` entfernen und `typing-extensions` ergänzen (veraltete Resolver-Altlast). Diese Änderung ist absichtlich nicht enthalten, um den PR auf die Sicherheitskorrektur zu begrenzen.
