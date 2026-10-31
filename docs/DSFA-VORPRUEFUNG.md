# Datenschutz-Folgenabschätzung (DSFA) – Vorprüfung

Stand: 10. August 2026

Diese Vorprüfung entscheidet **nicht automatisch**, ob eine DSFA nach Art. 35 DSGVO erforderlich ist. Sie dokumentiert die Entscheidung des konkreten Betreibers und muss bei wesentlichen Änderungen erneut durchgeführt werden.

## 1. Verarbeitung beschreiben

- Betreiber: `[ausfüllen]`
- Wache(n)/Organisationseinheiten: `[ausfüllen]`
- aktivierte Wachbuch-Module: `[ausfüllen]` – Datenkatalog der Wache beifügen (`docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md`)
- betroffene Personengruppen: `[ausfüllen]`
- Datenkategorien: `[ausfüllen]` – laut Datenkatalog (Spalten „Art“ und „Personenbezug“)
- Datenmengen/Nutzerzahl: `[ausfüllen]`
- Aufbewahrungsfristen: `[ausfüllen]` – laut [`LOESCHKONZEPT.md`](LOESCHKONZEPT.md)
- externe Empfänger/Dienstleister: `[ausfüllen]` – laut [`DATENFLUESSE.md`](DATENFLUESSE.md)

## 2. Produktgrenze bestätigen

- [ ] keine Patienten-/Gesundheitsdaten vorgesehen
- [ ] keine Einsatz-/Alarmierungs-/ePCR-Daten vorgesehen
- [ ] keine biometrischen Daten zu Identifikationszwecken im Wachbuch-Datenmodell
- [ ] keine Standortverfolgung von Beschäftigten
- [ ] keine automatisierte Leistungs-/Verhaltensbewertung
- [ ] keine automatisierte Entscheidung mit rechtlicher/ähnlich erheblicher Wirkung
- [ ] keine heimliche Überwachung

Wenn ein Punkt nicht bestätigt werden kann, ist die Risikobewertung deutlich zu verschärfen und die Produktgrenze zu prüfen.

## 3. Kriterien für voraussichtlich hohes Risiko

Für jedes Kriterium `ja/nein` plus Begründung dokumentieren:

| Kriterium | Ja/Nein | Begründung |
| --- | --- | --- |
| systematische/umfassende Bewertung von Personen | `[ ]` | `[ ]` |
| automatisierte Entscheidungen mit erheblicher Wirkung | `[ ]` | `[ ]` |
| systematische Überwachung | `[ ]` | `[ ]` |
| besondere Kategorien / höchstpersönliche Daten | `[ ]` | `[ ]` |
| große Datenmenge / große Zahl Betroffener | `[ ]` | `[ ]` |
| Abgleich/Zusammenführung verschiedener Datenbestände | `[ ]` | `[ ]` |
| besonders schutzbedürftige Betroffene / Abhängigkeitsverhältnis Beschäftigung | `[ ]` | `[ ]` |
| innovative Technik mit unklaren Folgen | `[ ]` | `[ ]` |
| Verarbeitung erschwert Rechte/Freiheiten wesentlich | `[ ]` | `[ ]` |

Für „systematische Überwachung“ und „Abhängigkeitsverhältnis Beschäftigung“ die
Auswertungen mit Personenbezug aus dem Datenkatalog heranziehen (je Modul
„Auswertungen und Personenlisten“, Spalte „Personenbezug“), z. B. Lesebestätigungen
mit Namen, erledigte Aufgaben mit Vornamen und die Einweisungsmatrix mit Quote je
Person. Regelungen dazu: [`MITBESTIMMUNG-VORLAGE.md`](MITBESTIMMUNG-VORLAGE.md),
Baustein 2.3.

## 4. Wachbuch-spezifische Risiken

Mindestens bewerten:

- unzulässige Nutzung von Audit-/Quittierungsdaten zur Leistungskontrolle
- Freitexte mit sachfremden personenbezogenen Daten
- Mängelfotos mit Personen, Kennzeichen, Bildschirminhalten, Patienten-/Einsatzbezug oder EXIF/GPS
- zu lange Aufbewahrung
- zu breite Admin-/Stationsrechte
- verlorene/kompromittierte Mobilgeräte
- Token-/Sessiondiebstahl
- Fehlkonfiguration des Reverse Proxy/TLS
- unverschlüsselte Datenbank-/Backupmedien
- kompromittierte Abhängigkeiten/Container
- unerlaubte Cross-Station-Zugriffe
- Wiederherstellung alter gelöschter Daten aus Backup ohne erneute Löschsynchronisation

## 5. Bestehende Maßnahmen

Auf `DSGVO-TOM.md` verweisen und Wirksamkeit bewerten:

- MFA / WebAuthn
- Argon2-Passworthashing
- HTTPS/TLS
- AES-256-GCM für ausgewählte Geheimnisse
- OS-Secure-Storage im Mobile Client
- RBAC / Stationsisolation
- Audit / append-only Events
- Backup-Verschlüsselung / Least Privilege
- Dependency-Security / SBOM / CI
- MDM-/Gerätevorgaben
- Löschkonzept

## 6. Restrisiko

Vertraulichkeit: `[niedrig/mittel/hoch + Begründung]`  
Integrität: `[niedrig/mittel/hoch + Begründung]`  
Verfügbarkeit: `[niedrig/mittel/hoch + Begründung]`  
Rechte/Freiheiten der Betroffenen: `[niedrig/mittel/hoch + Begründung]`

## 7. Entscheidung

- [ ] DSFA nach Art. 35 DSGVO nach Bewertung **nicht erforderlich**.
- [ ] vollständige DSFA **erforderlich**.
- [ ] Datenschutzbeauftragte/r muss vor Entscheidung ergänzend prüfen.

Begründung: `[ausfüllen]`

Bei hohem Restrisiko trotz geplanter Maßnahmen ist die weitere rechtliche Vorgehensweise einschließlich einer möglichen Konsultation der Aufsichtsbehörde zu prüfen.

## 8. Freigabe

Fachverantwortung: `[Name/Datum]`  
Datenschutzbeauftragte/r: `[Name/Datum]`  
Informationssicherheit/IT: `[Name/Datum]`  
Nächster Review: `[Datum]`
