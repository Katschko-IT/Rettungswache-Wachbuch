# DSGVO-/BSI-Compliance-Profil

Stand: 10. August 2026

Dieses Dokument beschreibt den technischen und organisatorischen Sollzustand für einen produktiven Wachbuch-Betrieb in Deutschland. Es ist **keine Rechtsberatung, keine BSI-Zertifizierung und keine pauschale Erklärung der DSGVO-Konformität**. DSGVO-Konformität entsteht erst aus Produkt, konkreter Konfiguration, Rechtsgrundlagen, Verantwortlichkeiten und tatsächlichem Betrieb.

## Referenzrahmen

- DSGVO, insbesondere Art. 5, 13/14, 25, 30, 32, 33/34, 35 und 37–39
- BDSG, insbesondere § 38 für nichtöffentliche Stellen, soweit einschlägig
- TDDDG § 25 für Speicherungen/Zugriffe auf Endeinrichtungen
- BSI TR-02102-1, Version 2025-01: kryptographische Verfahren und Schlüssellängen
- BSI TR-02102-2 und BSI-Mindeststandard TLS, Version 2.4: TLS-Konfiguration
- BSI-Mindeststandard Mobile Device Management, Version 2.0
- BSI TR-03161-1 als zusätzlicher Sicherheitsmaßstab für mobile Anwendungen mit sensiblen Daten; Wachbuch ist dadurch **nicht** automatisch eine Gesundheitsanwendung oder ein Medizinprodukt
- IT-Grundschutz-Prinzipien, insbesondere Schutzbedarfsfeststellung, Patch-/Änderungsmanagement, Datensicherung, Protokollierung und Rollen-/Berechtigungskonzepte

Offizielle Einstiege:

- https://eur-lex.europa.eu/eli/reg/2016/679/oj/deu
- https://www.gesetze-im-internet.de/bdsg_2018/
- https://www.gesetze-im-internet.de/ttdsg/
- https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Publikationen/TechnischeRichtlinien/TR02102/BSI-TR-02102.html
- https://www.bsi.bund.de/DE/Themen/Oeffentliche-Verwaltung/Mindeststandards/TLS-Protokoll/TLS-Protokoll.html
- https://www.bsi.bund.de/DE/Themen/Oeffentliche-Verwaltung/Mindeststandards/Mobile_Device_Management/Mobile_Device_Management.html
- https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Publikationen/TechnischeRichtlinien/TR03161/BSI-TR-03161-1.html

## Produktgrenze

Wachbuch ist für organisatorische Wach-/Stationsabläufe bestimmt. Nicht vorgesehen sind:

- Patientenakten oder ePCR,
- Einsatzdokumentation,
- Alarmierung/Disposition,
- medizinische Diagnosen oder Behandlungsentscheidungen,
- automatisierte Beschäftigtenbewertung,
- heimliche Leistungs-/Verhaltenskontrolle.

Wenn ein Betreiber diese Grenze organisatorisch oder technisch erweitert, ist die Datenschutz-/Sicherheitsbewertung neu durchzuführen.

## Technischer Sollzustand

| Bereich | Sollzustand |
| --- | --- |
| Transport | ausschließlich HTTPS/TLS in Produktion; aktuelle BSI-TLS-Empfehlungen am Reverse Proxy |
| Passwörter | Argon2id bevorzugt; sichere Passwortregeln; kein Klartext |
| MFA | für produktive Zugänge verpflichtend; WebAuthn/Passkey oder TOTP |
| Geheimnisse | AES-256-GCM; separater `CRYPTO_MASTER_KEY`; Schlüsselrotation dokumentiert |
| Datenbank | Least-Privilege-Rollen; verschlüsselter Datenträger/Volume; kein öffentlich erreichbarer DB-Port |
| Backups | verschlüsselt, offsite, Zugriff getrennt, Restore regelmäßig getestet |
| App-Token | Betriebssystem-Secure-Storage auf iOS/Android |
| Offline-Cache | server-/tokengebunden, Secure Storage, Löschung bei Logout/Serverwechsel |
| Android | kein Cleartext, App-Backup deaktiviert, Release-Signing, aktuelle targetSdk-Anforderung |
| iOS | Keychain, ATS/HTTPS, Release-Signing, Privacy-Manifeste |
| Protokollierung | keine Passwörter/Tokens/Request-Bodies; Zugriff nach Need-to-know; definierte Retention |
| Berechtigungen | stationsbezogenes RBAC; Least Privilege |
| Endgeräte | Gerätesperre, Updates, kein Root/Jailbreak; bei Organisationsgeräten MDM empfohlen |
| Lieferkette | Dependency-/Vulnerability-Scans, SBOM, signierte Release-Artefakte, Review-Gates |

## Produktions-Gates

Ein produktiver Betreiber darf die Konfiguration erst freigeben, wenn mindestens:

- [ ] Verantwortlicher und Kontaktwege feststehen.
- [ ] Datenschutzbeauftragte/r – falls zu benennen – im Admin gepflegt und zuständiger Aufsicht gemeldet ist.
- [ ] Art.-13-/Art.-14-Information ausgefüllt und bereitgestellt ist.
- [ ] VVT gepflegt ist.
- [ ] DSFA-Vorprüfung dokumentiert ist; falls erforderlich vollständige DSFA abgeschlossen ist.
- [ ] Lösch-/Aufbewahrungskonzept freigegeben ist.
- [ ] TOMs freigegeben sind.
- [ ] Schutzbedarf bewertet ist.
- [ ] `CRYPTO_MASTER_KEY` separat vom Django-Secret gesetzt ist.
- [ ] MFA für Produktivzugänge erzwungen wird.
- [ ] TLS-Konfiguration geprüft wurde.
- [ ] Datenbankvolume und Backups verschlüsselt sind.
- [ ] Restore-Test erfolgreich dokumentiert wurde.
- [ ] Patch-/Incident-Prozess mit Verantwortlichen und Fristen besteht.
- [ ] Geräte-/MDM-Regeln dokumentiert sind.
- [ ] kein realer Patienten-/Einsatzdatenbestand in Wachbuch enthalten ist.

## Nachweis statt Behauptung

In externen Unterlagen bevorzugte Formulierung:

> Wachbuch ist nach Privacy-by-Design-/Least-Privilege-Prinzipien entwickelt und seine Kryptografie-/Betriebsempfehlungen orientieren sich an den referenzierten BSI-Richtlinien. Eine BSI-Zertifizierung oder pauschale DSGVO-Konformitätsgarantie wird nicht behauptet; der konkrete Betreiber ist für die rechtliche und organisatorische Freigabe seiner Verarbeitung verantwortlich.

## Begleitdokumente

- `DSGVO-TOM.md`
- `DATENSCHUTZ-INFORMATION-ART13.md`
- `LOESCHKONZEPT.md`
- `VVT-TEMPLATE.md`
- `DATENKATALOG.md` (erzeugt mit `python manage.py data_catalog --write`)
- `DATENFLUESSE.md`
- `MITBESTIMMUNG-VORLAGE.md`
- `DSFA-VORPRUEFUNG.md`
- `MOBILE-DEVICE-BETRIEB.md`
- `OPERATIONS.md`
- `SECURITY.md`
