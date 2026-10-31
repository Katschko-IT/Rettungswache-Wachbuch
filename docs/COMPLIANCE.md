# Compliance: DSGVO, Cookies, AI Act, NRW öffentlicher Dienst

Stand: 31. Oktober 2026. Technische und organisatorische Orientierung für Betreiber.
Keine Rechtsberatung.

## Kurzfazit

| Thema | Produktstand |
| --- | --- |
| DSGVO | Privacy by Design, Rollen, Audit ohne Freitextkopien, Modulschalter |
| Cookies / TDDDG | keine Analyse- oder Werbe-Cookies; Sitzung, CSRF, Sprache, Darstellung, Geräte-Cookies für Terminal und Display; Transparenz unter `/datenschutz/` |
| EU AI Act | Produkt ist kein KI-System; keine automatisierte Bewertung von Beschaeftigten |
| NRW oeffentlicher Dienst | DSG NRW / LPVG-Hinweise; Mitbestimmung und VVT bleiben Betreiberpflicht |
| Kirchliche Träger | KDG bzw. DSG-EKD mit kirchlicher Aufsicht; MAV statt Betriebsrat (Abschnitt unten) |
| Datenkatalog, Datenflüsse | [`DATENKATALOG.md`](DATENKATALOG.md), [`DATENFLUESSE.md`](DATENFLUESSE.md), Vorlage [`MITBESTIMMUNG-VORLAGE.md`](MITBESTIMMUNG-VORLAGE.md) |
| Versionierung | SemVer in `core/version.py`, Footer, `/healthz/`, Changelog |
| Updates | dokumentierter Release-/Rollback-Ablauf in `OPERATIONS.md` |

## DSGVO und Privacy by Design

Technisch umgesetzt oder vorbereitet:

- Zweckbindung: Wachenorganisation, keine Patienten-/Einsatzakte
- Datenminimierung: Geburtstage ohne Jahr, Audit ohne Fachfreitexte
- Integrität: Append-only-Kasse, Revisionshistorie, DB-Rechte
- Vertraulichkeit: TLS-Proxy (TLS 1.3 / BSI TR-02102-2), sichere Cookies, CSP,
  Rollenisolation, E2EE mit AES-256-GCM (siehe [`CRYPTO-BSI.md`](CRYPTO-BSI.md))
- Passwörter: Argon2id; TOTP-Geheimnisse AES-256-GCM at rest
- Betroffenenrechte: organisatorisch in der Go-live-Checkliste; technisch
  Austrittsbereinigung (Geburtstage), Feed-Retention und optionale Audit-Fristen
  vorbereitet; weitere Fristen nach Freigabe schärfen

Verantwortliche Stelle, Rechtsgrundlagen je Modul, VVT (Art. 30) und ggf. DSFA
müssen vor Pilotbetrieb freigegeben sein.

## Cookies und TDDDG (vormals TTDSG)

§ 25 TDDDG verlangt Einwilligung für nicht notwendige Zugriffe auf Endgeräte.
Dieses Produkt setzt absichtlich **keine** Analyse-, Marketing- oder Social-
Cookies. Notwendige Cookies:

| Cookie | Zweck | Einwilligung |
| --- | --- | --- |
| `rwsth_session` | Anmeldung / Sitzung | nein (technisch notwendig) |
| `rwsth_csrf` | CSRF-Schutz | nein (technisch notwendig) |
| `wachbuch_language` | gewählte Sprache (auch bei der Anmeldung aus dem Profil gesetzt) | nein (vom Nutzer gewünschte Funktion) [prüfen] |
| `wb_theme` | helle oder dunkle Darstellung | nein (vom Nutzer gewünschte Funktion) [prüfen] |
| `rwsth_terminal` | Gerätegeheimnis eines registrierten Wachenterminals (nur dort) | nein (technisch notwendig) |
| `rwsth_display` | Display-Link eines Wachen-Displays (nur dort) | nein (technisch notwendig) |

Dazu kommen Browser-Speicher (Installationshinweis, Chat-Schlüssel nur für die
Sitzung) und der Seiten-Cache des Service Workers; vollständige Liste im
Datenkatalog, Abschnitt „Daten auf Endgeräten“.

Transparenz: Seite `/datenschutz/`. Kein Cookie-Banner für Opt-in-Tracking.
PWA-Service-Worker und lokaler Installationshinweis speichern keine Werbe-IDs.
Werden später Analyse-Tools eingeführt, ist vorher ein Consent-Banner und eine
Rechtsprüfung nötig.

## EU-KI-Verordnung (AI Act)

- Das Wachbuch ist klassische SSR-/PWA-Software ohne eingebettetes Modell, das
  über Personen inferiert.
- Es erzeugt keine Rankings, Scores oder Verhaltensprofile von Beschäftigten.
- Externe KI-Werkzeuge in der **Entwicklung** (z. B. Coding-Assistenten) gehören
  nicht zum betriebenen Produkt; der Betreiber bleibt für eigene KI-Einsätze
  verantwortlich.
- Verboten im Betrieb: Audit- oder Aufgabendaten als Social Scoring oder zur
  heimlichen Leistungsüberwachung zu nutzen.

Ändert sich das Produkt (z. B. KI-gestützte Schichtvorschläge), ist eine neue
AI-Act- und Datenschutzprüfung erforderlich.

## Öffentlicher Dienst NRW

Für kommunale oder landesnahe Rettungsdienststellen typischerweise relevant:

- DSG NRW und spezielle Regelungen für öffentliche Stellen
- LPVG NRW § 72: Mitbestimmung bei technischen Einrichtungen, die geeignet sind,
  Verhalten oder Leistung zu überwachen (Login, Audit, Zeitstempel)
- keine Gemeinschaftskonten; persönliche Konten und Rollenmodell
- Auskunfts-, Berichtigungs- und Löschprozesse organisatorisch festlegen
- Löschfristen je Datenart (Übergaben, Audit, Kasse, Aufgaben) freigeben

Die Anwendung ersetzt weder Personalratsbeteiligung noch behördliche Freigaben.

## Kirchliche Träger (KDG, DSG-EKD)

Viele Rettungswachen gehören zu kirchlichen Trägern (katholisch z. B. Malteser
oder Caritas, evangelisch z. B. Johanniter oder Diakonie [prüfen]). Für sie gilt:

- **Datenschutzrecht:** Art. 91 DSGVO erlaubt Kirchen eigenes Datenschutzrecht.
  Katholische Träger wenden das KDG an, evangelische das DSG-EKD [prüfen].
- **Aufsicht:** Statt der Landesdatenschutzbehörde ist eine kirchliche Aufsicht
  zuständig: bei KDG die Datenschutzaufsicht des Bistums (z. B. ein
  Katholisches Datenschutzzentrum), bei DSG-EKD in der Regel der Beauftragte
  für den Datenschutz der EKD (BfD EKD); einige Landeskirchen haben eine eigene
  Aufsicht. Diese Stelle gehört in die Datenschutzinformation (Einstellungen →
  Impressum & Datenschutz, Feld „Zuständige Datenschutz-Aufsichtsbehörde“).
- **Mitbestimmung:** Das BetrVG gilt nicht (§ 118 Abs. 2 BetrVG). Zuständig ist
  die Mitarbeitervertretung nach MAVO bzw. MVG-EKD; die Vereinbarung ist eine
  Dienstvereinbarung [prüfen]. Bausteine: [`MITBESTIMMUNG-VORLAGE.md`](MITBESTIMMUNG-VORLAGE.md).
- **VVT, Betroffenenrechte, Beschwerde:** nach dem kirchlichen Gesetz; Aufbau
  wie in [`VVT-TEMPLATE.md`](VVT-TEMPLATE.md) und
  [`DATENSCHUTZ-INFORMATION-ART13.md`](DATENSCHUTZ-INFORMATION-ART13.md) [prüfen].

Paragraphen kirchlicher Gesetze nennt Wachwerk in der Oberfläche nicht; sie
sind mit der oder dem Datenschutzbeauftragten am amtlichen Text zu prüfen.

## Versionierung

- Canonical Version: [`core/version.py`](../core/version.py) (`APP_VERSION`)
- Override: Umgebungsvariable `APP_VERSION`
- Anzeige: Footer und JSON-Feld `version` unter `/healthz/`
- Änderungen: [`CHANGELOG.md`](../CHANGELOG.md) nach Keep-a-Changelog / SemVer
- Image-Label: `org.opencontainers.image.version` im Dockerfile

Empfohlene Nummernkreise:

- `0.x.y` vor formalem Go-live
- Patch: Sicherheits-/Bugfixes ohne Schemabruch
- Minor: neue Module oder Rueckwaertskompatible Features
- Major: brechende Migrationen oder Auth-Wechsel

## Updates und Rollback

Siehe ausführlichen Ablauf in [`OPERATIONS.md`](OPERATIONS.md). Mindeststandard:

1. Changelog und Migrationshinweise lesen
2. Backup + Restore-Test
3. Abhängigkeiten/Image-Digest prüfen und scannen
4. Staging oder Wartungsfenster
5. `docker compose up -d --build`, Healthcheck inkl. Versionsfeld
6. Fachsmoke: Login, Übergabe, Tagesaufgaben, optional Feeds
7. Bei Störung: vorheriges Image + Dump-Restore, keine manuellen Tabellenfixes

## Betreiber-Checkliste (Ergänzung)

- [ ] Verantwortliche Stelle und anwendbares Recht (DSG NRW / BDSG / Kirche) bestimmt
- [ ] VVT und Betroffeneninformation freigegeben
- [ ] Cookie-/Datenschutzseite verlinkt und inhaltlich angepasst
- [ ] AI-Act-Prüfung dokumentiert (Produkt ohne KI-System)
- [ ] Personalvertretung zu Login/Audit/Aufgaben beteiligt
- [ ] Versions- und Updateprozess im Betriebshandbuch verankert
