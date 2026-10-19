# Kryptografie nach BSI-Empfehlungen (öffentliche Verwaltung)

Stand: 3. August 2026.

Referenz: [BSI TR-02102](https://www.bsi.bund.de/DE/Themen/Unternehmen-und-Organisationen/Standards-und-Zertifizierung/Technische-Richtlinien/TR-nach-Thema-sortiert/tr02102/tr02102_node.html)
(aktuelle Jahresfassung, z. B. 2026-01) sowie TR-02102-2 (TLS).

Dieses Dokument ist **keine Zertifizierung**, sondern die produktseitige
Zuordnung gängiger Verfahren für selbst gehostete Wachbuch-Instanzen
(kommunal / öffentlicher Rettungsdienst).

## Kurzprofil

| Einsatz | Verfahren | Schlüssellänge / Parameter | BSI-Status |
| --- | --- | --- | --- |
| Transport (Proxy) | TLS **1.3** bevorzugt, mind. 1.2 | AEAD, Forward Secrecy | TR-02102-2 |
| Clientseitig verschlüsselte Nachrichten | **AES-256-GCM** | 256 Bit | empfohlen |
| Schlüsselvereinbarung | **ECDH P-256** (secp256r1) | 256 Bit Kurve | empfohlen (>= 250 Bit) |
| Schlüsselableitung | **HKDF-SHA-256** | – | empfohlen |
| Private-Key-Umschlag | **PBKDF2-SHA-256** -> AES-256-GCM | >= 600.000 Iterationen | PBKDF2 zulässig; Argon2 im Browser nicht verfügbar |
| Login-Passwörter | **Argon2id** (Django), PBKDF2-Fallback | Django-Defaults | moderne Verwaltungspraxis |
| TOTP-Geheimnisse at rest | **AES-256-GCM** (Schlüssel aus `SECRET_KEY` via HKDF) | 256 Bit | empfohlen |
| App-Tokens | SHA-256-Hash in DB | – | Integrität / Vergleich |
| Zufall | OS-CSPRNG (`secrets` / Web Crypto) | – | empfohlen |

## Chat / Privat / Post

- Der Browser verschlüsselt Nachrichten vor dem Versand.
- Der Server speichert Ciphertext und Key-Wraps (`A256GCM+ECDH-ES`).
- Private Keys liegen passphrase-umschlossen auf dem Server; der entschlüsselte
  Private Key liegt nach Freigabe nur in `sessionStorage` des Browsers.
- Ein passiver Datenbank- oder Backupzugriff liefert keine Klartexte ohne die
  Passphrase beziehungsweise den entschlüsselten privaten Schlüssel.
- Rollen und Admin-Oberflächen erhalten keine Funktion zum Entschlüsseln
  fremder Nachrichten.

## Bedrohungsmodell und klare Grenze

Die heutige Web-PWA ist **nicht** gegen einen aktiv böswilligen oder vollständig
kompromittierten Anwendungsserver abgesichert. Der Server liefert JavaScript,
Schlüsselverzeichnis und Weboberfläche aus. Ein Angreifer mit Kontrolle über
diese Auslieferung könnte zukünftigen Clientcode oder öffentliche Schlüssel
verändern.

Nicht vorhanden sind derzeit:

- gegenseitig geprüfte Sicherheitsnummern/Fingerprints
- Key Transparency oder extern nachvollziehbares Schlüsselverzeichnis
- unabhängig ausgelieferter und reproduzierbar signierter Client als
  zwingender Kommunikationsweg
- kryptografische Warnung bei jedem unerwarteten Schlüsselwechsel

Daher lautet das belastbare Schutzversprechen: **clientseitig verschlüsselte
Speicherung gegen passive Einsicht in Datenbank und Backups**, nicht Schutz vor
einem aktiv kompromittierten Serverbetreiber. Folgearbeit steht als R-020 in der
[`REMEDIATION-ROADMAP-2026-08.md`](REMEDIATION-ROADMAP-2026-08.md).

## Transport (Betreiberpflicht)

TLS terminiert am Reverse-Proxy. Empfohlen (TR-02102-2):

- TLS 1.3 mit z. B. `TLS_AES_256_GCM_SHA384`
- Kein TLS 1.0/1.1, kein RC4/3DES/CBC ohne AEAD
- `SECURE_COOKIES=true`, HSTS aktiv

Beispiel Caddy (TLS 1.3 default):

```caddy
wache.example.org {
        reverse_proxy 127.0.0.1:8090
}
```

Beispiel nginx (Ausschnitt):

```nginx
ssl_protocols TLSv1.3 TLSv1.2;
ssl_prefer_server_ciphers off;
# TLS 1.3 AEAD-Suiten nutzt OpenSSL automatisch bei TLSv1.3
```

## Was bewusst nicht Produkt-Scope ist

- VS-NfD / Geheimschutz-Freigaben
- Post-Quanten-Hybrid (BSI-Migration geplant; Roadmap später)
- Brainpool-Kurven (Web Crypto / Browser-Support begrenzt; P-256 üblich und BSI-konform)

## Verwandte Docs

- [`SECURITY-PRIVACY.md`](SECURITY-PRIVACY.md)
- [`COMPLIANCE.md`](COMPLIANCE.md)
- [`ASVS-L2.md`](ASVS-L2.md)
- [`OPERATIONS.md`](OPERATIONS.md)
