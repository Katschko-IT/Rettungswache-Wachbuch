# Verzeichnis von Verarbeitungstätigkeiten (VVT) – Vorlage Wachbuch

Stand: 10. August 2026

Vorlage für die Dokumentation nach Art. 30 DSGVO. Betreiber müssen sie an ihre tatsächlichen Zwecke, Rechtsgrundlagen, Empfänger und Fristen anpassen.

Grundlagen zum Ausfüllen:

- Datenkategorien, Rollen und technische Fristen der eingeschalteten Module: Datenkatalog der Wache (`docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md`; Referenz [`DATENKATALOG.md`](DATENKATALOG.md)).
- Empfänger und Drittländer: [`DATENFLUESSE.md`](DATENFLUESSE.md).
- Fristen: [`LOESCHKONZEPT.md`](LOESCHKONZEPT.md).
- Kirchliche Träger führen das Verzeichnis nach KDG bzw. DSG-EKD [prüfen]; Aufbau und Inhalte entsprechen weitgehend Art. 30 DSGVO. Hinweise: [`COMPLIANCE.md`](COMPLIANCE.md), Abschnitt „Kirchliche Träger“.

## Verarbeitungstätigkeit: Wachbuch – interne Wach-/Stationsorganisation

### Verantwortlicher

- Organisation: `[ausfüllen]`
- Anschrift/Kontakt: `[ausfüllen]`
- Datenschutzbeauftragte/r: `[ausfüllen / im Admin gepflegt]`
- Fachverantwortliche Stelle: `[ausfüllen]`
- IT-Betrieb: `[ausfüllen]`

### Zwecke

- Authentifizierung und Berechtigungsverwaltung
- organisatorische Übergaben/Aufgaben/Checklisten
- Mängel- und Geräte-/Fahrzeugstatus
- Inventar-/Poolverwaltung
- Kalender und optionale Organisationsmodule
- Sicherheits-/Auditnachvollziehbarkeit
- weitere tatsächlich aktivierte Zwecke: `[ausfüllen]`

Nicht vorgesehen: Patienten-, Einsatz-, Alarmierungs-, ePCR- oder medizinische Behandlungsdaten.

### Kategorien betroffener Personen

- Beschäftigte/Organisationsmitglieder
- Administratoren
- ggf. externe berechtigte Nutzer: `[ausfüllen]`

### Kategorien personenbezogener Daten

Je Modul im Datenkatalog der Wache (Spalten „Art“ und „Personenbezug“). Zusammengefasst:

- Konten-/Identifikationsdaten
- Rollen-/Stationszuordnung
- organisatorische Freitexte und Zeitstempel
- Quittierungen, Aufgaben-/Checklistenstatus
- Inventar-/Gerätezuordnungen
- Mängeldaten und ausdrücklich ausgewählte Mängelfotos
- Audit-/Sicherheitsereignisse
- optionale freiwillige Angaben

### Empfänger

- berechtigte interne Rollen
- IT-Administration/Betrieb
- Auftragsverarbeiter: `[Hosting/Backup/Monitoring/etc.]`
- sonstige Empfänger: `[ausfüllen]`
- eingeschaltete externe Dienste laut [`DATENFLUESSE.md`](DATENFLUESSE.md): `[Liste]`

### Drittlandübermittlungen

`[keine / konkret beschreiben inkl. Land, Empfänger, Garantie/Transfermechanismus]`

Drittlandbezug haben je nach Einstellung insbesondere Signal, Push-Relay (Apple/Google) und Web-Push; siehe [`DATENFLUESSE.md`](DATENFLUESSE.md).

### Löschfristen

Siehe freigegebenes `LOESCHKONZEPT.md` (im Pilot: Abschnitt „Vorschlag für den Pilot“ nach Freigabe); technisch umgesetzte Fristen stehen im Datenkatalog der Wache. Wesentliche Fristen hier zusammenfassen:

`[ausfüllen]`

### Technische und organisatorische Maßnahmen

Siehe `DSGVO-TOM.md`, insbesondere:

- TLS/HTTPS
- RBAC/Stationsisolation
- MFA
- sichere Passwort-Hashes
- verschlüsselte Geheimnisse / Key Management
- verschlüsselte Datenträger und Backups
- Least-Privilege-Datenbankrollen
- Logging ohne Secrets
- Patch-/Vulnerability-Management
- Restore-/Incident-Prozesse
- MDM/Endgeräteschutz

### Rechtsgrundlagen

Nicht aus dem Produkt ableiten. Je Zweck durch verantwortliche Stelle ausfüllen:

`[ausfüllen]`

### Auftragsverarbeitung

- AV-Vertrag erforderlich? `[ja/nein + Begründung]`
- Anbieter: `[ausfüllen]`
- Unterauftragsverarbeiter geprüft: `[ja/nein]`
- TOM des Auftragsverarbeiters geprüft: `[Datum]`

### Risiko-/DSFA-Bezug

- DSFA-Vorprüfung: `[Datum/Ergebnis]`
- vollständige DSFA erforderlich: `[ja/nein + Begründung]`
- Schutzbedarf: `[normal/hoch/sehr hoch je Grundwert]`

### Review

Verantwortlicher: `[Name/Rolle]`  
Letzte Prüfung: `[Datum]`  
Nächste Prüfung: `[Datum]`
