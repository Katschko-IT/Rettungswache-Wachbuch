# Wachbuch: Roadmap für die offenen Baustellen

## Ausgangsstand
Arbeitsbaum: /opt/data/workspace/wachbuch-umlaute-pages-20261019. Parent-Vollsuite392 Tests OK,1 Skip; Site10OK. Setup/Wachendaten/Wetter/individuelle Konten/einmalige QR-Aktivierung vorhanden. Drei letzte Parent-Fixes wurden von gemini-4-argon-high ohne reproduzierbaren Defekt im begrenzten Scope nachgeprüft. Keine Produktionsfreigabe. Kein Push/Deployment beauftragt.

## Rollen und Arbeitsweise
- Gemini3.8High als Hauptimplementierer; live exakte AGY-Modell-ID vor Auftrag prüfen, nicht in ein anderes Modell normalisieren. Voraussichtlich gemini-3.8-flash-high, nur nach Katalogbeleg. Wenn 'High' nicht eindeutig auflösbar: Blocker transparent, kein stiller Ersatz.
- Mistral Large übernimmt VIER kleine Aufträge M1–M4 unten; exakte verfügbare Modell-ID und tatsächliche Antwort belegen. 'Vier' bezeichnet hier die vier Pakete; keine erfundene Modell-ID 'large4'.
- Ein integrierender Writer pro Worktree. Mistral liefert in isolierten Kopien mit enger Datei-Allowlist oder reine Test-/Reviewartefakte; keine gleichzeitigen Änderungen am aktiven Baum.
- Nach jedem Paket echte gezielte Tests; nach Integration volle Suite, Migrationprüfung, Site/Lint/Diff, Browserprüfung soweit erreichbar. Externe Geräte-/Netztests nicht durch Mocks als erledigt ausgeben.
- Argon4High erst auf finalem eingefrorenem Stand; Scope/Hashes/Quota/Modellroute offenlegen. Reproduzierbare Befunde fixen und fokussiert nachprüfen.
- Ressourcen-/Quotenregel nach /opt/data/state/adaptive-agent-jobs/BETRIEB.md; 60min sinnvolle Laufzeit, kein kürzerer innerer Abbruch. Keine parallelen Duplikatreviews, kein Modellfallback ohne Freigabe. Jev nur bei begründeter sanitisierten Befundtriage, nicht zur Freigabe/Quotenberechnung.

## Phase1: Pilot-Blocker und verlässliche Testbasis (P0)
### M1: Entwicklungs-/Accesslog-Härtung
Kleine isolierte Aufgabe: django.server/runserver Aktivierungslinks ebenfalls redigieren, ohne Logkorrelation/Status/Lesbarkeit zu verlieren. Reale Request- und Formattertests mit synthetischen Tokens für200/301/403/410/429/500 soweit sinnvoll. Separat Gunicorn/Reverseproxy-Loggingkonfiguration prüfen und explizite sichere Pilotkonfiguration bauen; nicht unbemerkt alle Accesslogs abschalten. Keine Behauptung, beliebige externe Proxylogs seien automatisch geschützt.
### M2: Rate-Limit-Test deterministisch machen
Minutengrenz-Flake reproduzierbar mit kontrollierter Uhr und Counter/Cacheabgrenzung testen. Korrekte Rate-Limit-Semantik erhalten, nicht Produktionsschutz lockern, Counts erhöhen oder Sleeps verwenden. Vorher-/Nachher-Testbeweis.
### Gemini G1: integrierte Pilotbasis
M1/M2 prüfen und gezielt integrieren. Vier bisher unbelegte Routen chat_hide/task_edit/checklist_complete/station_member_keys inventarisieren: echte funktionale und negative Rollen-/Fremdwachentests, keine rein statischen reverse-Referenztests. Lokale Betriebs-/HTTPS-Konfiguration ohne Cloudzwang; echte Betreiber-/Zertifikatsdaten nicht erfinden.

## Phase2: wiederholbarer QR-Login (P1)
### Gemini G2: sicherer wiederholbarer QR-Anmeldeablauf
Zuerst schriftlicher Sicherheitsvertrag und Zustandsmaschine. Keine dauerhaften Bearer-QRs, keine Passwörter im QR, kein MFA-Bypass. Kurzlebige kryptografische Einmal-Challenge, Bindung an wartende Browser-Sitzung/Origin/Wache, ausdrückliche Zustimmung auf bereits authentifiziertem Mitarbeitergerät. Replay/Ablauf/Widerruf/CSRF/RateLimit/Sessionfixation/Tokenleaks/Anmeldeverwechslung testen. Nicht der QR-Scanner allein bestätigt einen anderen Benutzer. Ohne freigegebenen TLS-/Geräteflow failclosed. Aktivierung und Login in UI/Doku sauber trennen. Kamerascanning ist optionale UI mit lokaler Assetquelle; manueller sicherer Ersatz für Kameraberechtigungsfehler.
### M3: unabhängige kleine Auth-Testprüfung
Auf den eingefrorenen G2-Diff fokussierte Gegenprüfung und ergänzende Negativtests/Proofs für Replay, falscheWache, falscheBrowserSession und MFA. Kein Alternativauthsystem, keine parallele Hauptimplementierung. Finale Entscheidung und Integration beim Hauptimplementierer/Parent.

## Phase3: Offline konkret abgrenzen (P1/P2)
### Gemini G3: WAN-Ausfall produktnah absichern
Lokaler Server+LAN erreichbar, externes Netz blockiert: Setup/Login/Rollen/Kernabläufe/QRFlow funktionieren lokal; alle nötigen Assets lokal. Wetter darf fehlen; echte Cachealter/Datenstand, kein fiktivesLiveWetter. Persistenz und Neustart testen. Physische Pi-/WLAN-/TLS-Abnahme bleibt offen, bis Hardware bereitsteht.
### M4: Offline-/Browser-/Pilot-Akzeptanzpaket
Kleines Paket: reproduzierbare browsernahe WAN-Ausfalltests und kompakte Pilot-Checkliste inklusive HTTPS/QR-Kamera/individuelle Konten/Logout/Logredaktion/Datenpersistenz. Clientnetzisolation von lokalem Server unterscheiden. Keine produktive Internetabschaltung. Arbeit kann zunächst Testplan/Fixturn statt Hardwarebeweis liefern.
### Gemini G4: vollständig getrenntes Gerät – separater Architektur-Slice
Nicht als Nebenfix in G3 einbauen. Vor Implementation Datensparsamkeit, Logout-/Benutzerwechsel-Löschung, Verschlüsselung/Schlüsselhaltung, zugelassene offline Aktionen, Widerruf/Rollenänderung, Idempotenz und Konfliktentscheidungen spezifizieren. Danach schmaler sicherer Client-Cache/Outbox-Slice nur für ausdrücklich geeignete nichtkritische Aktionen; keine Offline-Adminfreigabe/MFAumgehung/automatische Konfliktüberschreibung. Eigene Abnahme, ehrlicher Restumfang. Wenn Fachentscheidung nicht ableitbar, offenen Entscheidungspunkt markieren statt gefährlichen Default erfinden.

## Phase4: Abschluss und Veröffentlichungsvorbereitung
- Volle aktualisierte Testmatrix und Quellenhashmanifest.
- GitHub-Projektseite (Pages) sachlich auf tatsächlich integrierten Funktionsstand bringen: keine Demo-/Werbeaufmachung, keine Behauptung "produktionsreif/zertifiziert/DSGVO-garantiert", QR-Login und Handy-Offline nicht als vorhanden darstellen. Screenshots nur synthetische Testoberfläche ohne Kundendaten. Existierenden Repo-/Pages-Status zuerst prüfen, Artefakt-Setup und Veröffentlichung über Parent.
- Argon4High auf endgültigem Integrationsstand mit realer Modellroute/Exit/Belegen; keine automatische Gleichsetzung 'keine Befunde' = Produktionsreife.
- README, Funktionsmatrix, Offlinegrenzen und GitHub-Pages-Text auf tatsächlichen Stand bringen.
- Kein Commit/Push/Pages-Aktivierung/Produktivdeployment ohne gesonderte Freigabe.

## Freigaben (Nachtrag 2026-10-19, Nutzerentscheidung)
- Nach grünem abschließendem Review OHNE offene bestätigte Fehler ist Commit/Push zulässig.
- Der finale Commit/Push erfolgt ausschließlich durch den Parent nach eigener Vollabnahme. Child-Agenten committen/pushen nicht.
- Bestehende Vorarbeit/untracked Dateien dürfen dabei nicht vernichtet werden.
- Site-Etappe (GitHub-Projektseite) wird NACH den Funktionen im Roadmapcheckpoint eingeplant, VOR dem finalen Argon-Review.
- Veröffentlichung erst nach grünem finalem Review und erfüllten Gates.

## Externe Abnahmen / nicht softwareseitig vortäuschen
1. Pi/OrangePi vorhanden, stabilerDatenträger/Netzteil, WLAN-AP-Treiber und erreichbare lokale Origin.
2. Reales iPhone/Tablet im isolierten Test-WLAN mit Mobilfunk/VPN ausgeschaltet; vertrauenswürdiges lokalesHTTPS.
3. Echte Postgres-Nebenläufigkeit nur gegen isolierte Testinstanz, keine produktiveDB.
4. Passkey-/WebPush-/ICS-End-to-End nur mit realer freigegebener Testumgebung. Keine Fake-Erfolge.

## Startfreigabe dieser Etappe
Zuerst Phase1/G1/M1/M2 und PlanungG2/M3; dann geeignete Phase2/3-Pakete sequenziell. Nicht alle Phasen in einen unprüfbaren Megaprompt pressen. Parent übernimmt Checkpoints und startet nächste Pakete anhand tatsächlicher Evidenz. Vollständig getrenntes Handy bleibt bis eigener Implementierung ausdrücklich offen.
