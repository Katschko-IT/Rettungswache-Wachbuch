# Release 0.26.0 – Ablauf Schritt für Schritt

Stand: 29. Oktober 2026. Diese Anleitung beschreibt, wie 0.26.0 veröffentlicht
wird und wie Server die neue Version bekommen. Sie gilt sinngemäß für jede
weitere Version. 0.26.0 bleibt ein Pilotstand, **keine Produktionsfreigabe**.

## Warum der Ablauf so ist

Nach einem Merge auf `main` bekommt **kein** Server etwas. `install.sh`,
`wachbuch update` und `wachbuch auto-update` (Modus `alle`) folgen dem
GitHub-Release, das als „Latest“ markiert ist (`releases/latest`). Die Images
entstehen erst beim Tag `vX.Y.Z`.

Bei 0.25.0 wurde das Release von Hand eine Sekunde **vor** dem Bau der Images
angelegt. Gut acht Minuten lang zeigte `releases/latest` auf eine Version ohne
App-Image: Neuinstallationen brachen beim `pull` ab. Seit 0.26.0 legt
`publish-image.yml` das Release selbst an, und zwar erst nach allen Images:

| Job | Was er tut |
| --- | --- |
| `prepare` | prüft vor dem Bauen: Tag = `core/version.py`, `CHANGELOG.md` hat den Abschnitt `## 0.26.0 - Datum`; ermittelt, ob die Version die neueste ist (sonst kein `latest`) |
| `verify` | komplette CI (`ci.yml`): Tests, Migrationen, Images bauen, ganzer Stack, Backup und Restore-Probe |
| `publish` | App-, Backup- und db-Image für amd64 und arm64; erst Sicherheitsscan (Trivy, HIGH/CRITICAL mit Fix), dann Veröffentlichung mit den Tags `0.26.0`, `0.26` und `latest` |
| `release` | GitHub-Release „Wachwerk 0.26.0“ mit dem CHANGELOG-Abschnitt als Text, als „Latest“ markiert |

Scheitert ein Job, entsteht **kein** Release. `releases/latest` bleibt dann bei
0.25.0, und kein Server bemerkt etwas.

**Deshalb: nur den Tag pushen.** Kein `gh release create`, kein Knopf „Draft a
new release“ auf GitHub. Beides legt das Release sofort an, vor den Images.

## 1. Vor dem Merge (im Pull Request)

1. Alle Pakete der Umsetzung sind im PR, die CI ist grün.
2. `core/version.py`: `APP_VERSION = "0.26.0"`.
3. `CHANGELOG.md`: `## Unveröffentlicht` wird zu `## 0.26.0 - JJJJ-MM-TT`.
   Der Abschnitt bis zur nächsten `## `-Überschrift wird wörtlich der
   Release-Text. Darin ein Block **Upgrade-Hinweise**:
   - Migrationen ab `0058`: Der Code von 0.25.0 läuft mit dem neuen Schema
     nicht. Zurück geht es nur mit dem Backup von vor dem Update
     (`wachbuch restore`).
   - Die öffentliche Demo (`--demo`, `DEMO_SANDBOX=true`) braucht 0.26.0.
   - neue oder geänderte Compose-Dienste und Variablen.
4. `README.md` (Abschnitt Projektstand): „Version **0.26.0**“.
5. Prüfen:

   ```bash
   python3 .github/scripts/release.py check-tag v0.26.0   # keine Ausgabe, Exit 0
   python3 .github/scripts/release.py notes 0.26.0        # zeigt den Release-Text
   python manage.py makemigrations --check --dry-run --settings=config.test_settings
   python manage.py test --settings=config.test_settings
   python3 site/tests/check_site.py
   ```

   Die Testsuite enthält `core.test_release_pipeline`. Sie schlägt fehl, wenn
   `core/version.py` und die CHANGELOG-Überschrift nicht zusammenpassen.

## 2. Merge und CI auf `main`

1. PR mergen.
2. Warten, bis `ci.yml` auf `main` grün ist:
   `gh run list --workflow ci.yml --branch main --limit 1`.
3. `pages.yml` veröffentlicht dabei die Projektseite mit dem Knopf
   „Live-Demo ausprobieren“. Der Knopf zeigt auf demo.rwsth.de, das ab
   Schritt 6 mit 0.26.0 läuft. Darum die Schritte 3 bis 6 direkt nacheinander
   erledigen.

## 3. Tag setzen (der einzige Handgriff)

```bash
git fetch origin
git switch --detach origin/main
python3 .github/scripts/release.py check-tag v0.26.0
git tag -a v0.26.0 -m "Wachwerk 0.26.0"
git push origin v0.26.0
```

Der Push startet `publish-image.yml`.

## 4. Auf Images und Release warten

Das dauert etwa 10 bis 20 Minuten (0.25.0: gut acht Minuten, jetzt kommt der
Sicherheitsscan vor dem Veröffentlichen dazu). Am längsten braucht der
arm64-Bau per Emulation.

```bash
gh run watch "$(gh run list --workflow publish-image.yml --limit 1 --json databaseId --jq '.[0].databaseId')"

for image in rettungswache-wachbuch rettungswache-wachbuch-backup rettungswache-wachbuch-db; do
  docker buildx imagetools inspect "ghcr.io/katschko-it/$image:0.26.0" | grep -E 'Platform: +linux/(amd64|arm64)'
done

gh release view v0.26.0 --json tagName,isLatest,publishedAt
gh api repos/Katschko-IT/Rettungswache-Wachbuch/releases/latest --jq .tag_name   # v0.26.0
```

### Wenn etwas scheitert

- **`prepare` rot** (Version oder CHANGELOG passen nicht): Es wurde nichts
  gebaut. Per PR auf `main` korrigieren, dann den Tag entfernen und neu setzen:
  `git push origin :refs/tags/v0.26.0 && git tag -d v0.26.0`, danach Schritt 3.
- **`verify` oder `publish` rot**: Es gibt kein Release, Server und
  Neuinstallationen merken nichts. Liegt es nur am Moment (Netz,
  Trivy-Datenbank, Registry), dann im Lauf „Re-run failed jobs“. Braucht es
  eine Korrektur im Code: zuerst per PR auf `main` beheben, dann den Tag wie oben
  neu setzen. Das ist nur erlaubt, solange **kein** Release existiert. Nach
  dem Release wird ein Tag nie mehr verschoben; die Korrektur kommt dann als
  0.26.1.
- **`release` rot** (Images sind da, Release fehlt): Job neu starten. Er
  bricht nicht ab, wenn das Release schon existiert.

## 5. Wie Server die neue Version bekommen

| Installation | Was passiert |
| --- | --- |
| Neuinstallation (`install.sh`) | installiert 0.26.0, sobald das Release da ist |
| `auto-update an alle` | übernimmt 0.26.0 in der nächsten Nacht (Standard 03:30, bis zu 15 Minuten später): Backup, neue Dateien und Images, Neustart; startet 0.26.0 nicht, läuft wieder 0.25.0 |
| `auto-update an` (Modus `sicherheit`) | bleibt bei 0.25.0. Neu gebaute Images bekommt sie weiter, solange 0.25 zu den zwei neuesten Minor-Versionen gehört, also bis 0.27.0 erscheint. Auf 0.26.0 wechseln: `sudo /opt/wachbuch/wachbuch update` |
| ohne automatische Updates | `sudo /opt/wachbuch/wachbuch update` (oder `update 0.26.0`) |

Protokoll und Stand: `sudo /opt/wachbuch/wachbuch auto-update status`,
Datei `logs/auto-update.log`. Die laufende Version zeigt `/healthz/`
(`{"status": "ok", "version": "0.26.0"}`).

Für Server im Internet empfiehlt sich `auto-update an alle`. Ältere Versionen
erhalten keine Neubauten mehr, und Caddy und Redis wechseln nur mit einer
neuen Version.

**Zurück auf 0.25.0** nur zusammen mit dem Backup von vor dem Update:
`wachbuch update 0.25.0` und danach `wachbuch restore <Backup>` (siehe
OPERATIONS.md, Rollback). Soll 0.26.0 vorerst niemand mehr bekommen:
`gh release edit v0.25.0 --latest`. Dann folgen Neuinstallationen und
`auto-update alle` wieder 0.25.0, bis 0.26.1 erscheint.

## 6. Öffentliche Demo demo.rwsth.de

- **Server schon installiert:** auf dem Server
  `sudo /opt/wachbuch/wachbuch update 0.26.0`, danach
  `sudo /opt/wachbuch/wachbuch auto-update an alle`.
- **Neuer Server:** nach [HETZNER.md](HETZNER.md) mit `--demo` und
  `--auto-update alle` installieren. `--yes` allein wählt `sicherheit`.
- Prüfen:
  - `curl -fsS https://demo.rwsth.de/healthz/` zeigt `0.26.0`.
  - `sudo /opt/wachbuch/wachbuch status`: alle Dienste laufen, darunter
    `demo-cleaner`.
  - Im Browser: Anmelden mit Demo / Demo legt eine eigene Wache an, der
    Rundgang startet, und Abmelden löscht die Wache.
  - Das eigene Betreiberkonto meldet sich nur mit zweitem Faktor an.
  - Die Projektseite <https://katschko-it.github.io/Rettungswache-Wachbuch/>
    führt mit „Live-Demo ausprobieren“ dorthin.

## 7. Nacharbeiten

1. Den wöchentlichen Neubau einmal von Hand starten:
   `gh workflow run refresh-images.yml`. Er baut jetzt v0.26.0 (mit `latest`)
   und v0.25.0. Die Images von PostgreSQL enthalten gosu aus dem offiziellen
   Image; seine gemeldeten Go-CVEs betreffen Teile, die gosu nie aufruft. Der
   Scan schließt die Datei deshalb aus, siehe Kommentar in
   `refresh-images.yml`.
2. Ist der Lauf grün, Issue #127 („Wöchentlicher Image-Neubau fehlgeschlagen
   (v0.25.0)“) schließen. Den veralteten Dependabot-PR #107 (postgres 18.6)
   ebenfalls schließen; PostgreSQL 18 braucht einen eigenen Upgrade-Weg für
   die Datenbank-Volumes.
3. Prüfen, dass der Pages-Lauf auf `main` grün ist:
   `gh run list --workflow pages.yml --limit 1`.

## Wöchentlicher Neubau ab jetzt

`refresh-images.yml` läuft montags 02:17 UTC. Er baut ohne Cache den neuesten
Patch der zwei neuesten Minor-Versionen (`REFRESH_MINOR_VERSIONS`), zum
Beispiel 0.26.0 und 0.25.0. Veröffentlicht wird nur, was Sicherheitsscan und
Starttest besteht. `latest` bekommt nur die neueste Version. Scheitert etwas,
bleiben die bisherigen Images, und es entsteht ein Issue.
