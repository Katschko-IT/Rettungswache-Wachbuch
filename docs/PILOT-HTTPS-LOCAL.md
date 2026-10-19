# Lokaler HTTPS-Pilotbetrieb (Entwicklung und Staging)

Dieses Dokument beschreibt die sichere Einrichtung eines lokalen TLS-terminierenden
Reverse-Proxies für den Wachbuch-Pilotbetrieb ohne Cloud-Zwang, ohne CDN-Abhängigkeiten
und ohne reale Betreiberdaten.

---

## 1. Übersicht und Vertrauensmodell

Im Pilotbetrieb terminiert ein lokaler Reverse-Proxy (z. B. Nginx) HTTPS auf Port 443
und leitet Anfragen über Loopback (HTTP auf Port 8000) an Gunicorn/Django weiter.

- **Django-Konfiguration:** [`config/pilot_settings.py`](file:///opt/data/workspace/wachbuch-umlaute-pages-20261019/config/pilot_settings.py)
  - `DEBUG = False`
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
  - `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SESSION_COOKIE_SAMESITE = "Lax"`
  - `SECURE_HSTS_SECONDS = 0` (bewusst auf 0 belassen: verhindert, dass Browser Test-Domains permanent auf HTTPS festnageln)
  - `SECURE_SSL_REDIRECT = True` (direkte HTTP-Zugriffe auf den App-Port werden umgeleitet)
  - `X_FRAME_OPTIONS = "DENY"`
  - `ALLOWED_HOSTS` und `CSRF_TRUSTED_ORIGINS` werden strikt fail-closed aus der Umgebung geladen (kein `*`).
- **Nginx-Template:** [`deploy/pilot/nginx-https.conf.template`](file:///opt/data/workspace/wachbuch-umlaute-pages-20261019/deploy/pilot/nginx-https.conf.template)

> [!WARNING]
> **Proxy-Logging und Aktivierungs-Tokens:**
> Der Python-/Gunicorn-Access-Logger (`core.gunicorn_logging.RedactingGunicornLogger`)
> redigiert Einmal-Aktivierungs-Tokens (`/aktivieren/<token>/`) anwendungsseitig.
> Ein vorgeschalteter Nginx-Proxy tut dies **nicht automatisch**.
> Im mitgelieferten Template ist für `^~ /aktivieren/` das Access-Log daher deaktiviert
> (`access_log off;`), um Token-Leaks im Webserver-Log zu verhindern.

---

## 2. Lokales TLS-Zertifikat (Self-Signed / Lokale CA)

Für rein lokale Tests (z. B. Hostname `pilot.local` oder `127.0.0.1`) kann ein
selbstsigniertes Zertifikat oder eine lokale Test-CA (z. B. via `mkcert`) erstellt werden.

### Option A: Self-Signed Zertifikat mit OpenSSL (Synthetisches Testbeispiel)

```bash
# Verzeichnis für Test-Zertifikate (nicht im Git einchecken!)
mkdir -p /tmp/pilot-ssl

openssl req -x509 -nodes -days 30 -newkey rsa:2048 \
  -keyout /tmp/pilot-ssl/pilot.key \
  -out /tmp/pilot-ssl/pilot.crt \
  -subj "/CN=pilot.local/O=Wachbuch Pilot/C=DE" \
  -addext "subjectAltName=DNS:pilot.local,IP:127.0.0.1"
```

### Option B: Lokale CA mit mkcert (Browser-Vertrauen)

```bash
mkcert -install
mkcert -cert-file /tmp/pilot-ssl/pilot.crt -key-file /tmp/pilot-ssl/pilot.key pilot.local 127.0.0.1
```

---

## 3. Lokale Namensauflösung (`/etc/hosts`)

Falls ein Hostname wie `pilot.local` verwendet wird, muss dieser lokal auflösbar sein:

```text
# /etc/hosts
127.0.0.1  pilot.local
```

---

## 4. Umgebungsvariablen und Startkommandos

### Umgebungsvariablen vorbereiten

```bash
export DJANGO_SETTINGS_MODULE=config.pilot_settings
export DJANGO_SECRET_KEY="pilot-lokales-geheimnis-nicht-fuer-produktion"
export DJANGO_DEBUG=false
export ALLOWED_HOSTS="pilot.local,127.0.0.1"
export CSRF_TRUSTED_ORIGINS="https://pilot.local,https://127.0.0.1"
export SITE_URL="https://pilot.local"

# Datenbank (z. B. lokale PostgreSQL oder SQLite-Pilot)
export DATABASE_URL="sqlite:////opt/data/workspace/wachbuch-umlaute-pages-20261019/pilot.sqlite3"
```

> [!IMPORTANT]
> `SITE_URL` und `CSRF_TRUSTED_ORIGINS`:
> Wenn `SITE_URL` auf `https://pilot.local` gesetzt ist, generieren Einladungs-Links
> und QR-Codes die passende kanonische URL. `CSRF_TRUSTED_ORIGINS` muss das HTTPS-Schema
> und den Hostnamen exakt enthalten, da Django POST-Anfragen über HTTPS gegen diesen Ursprung validiert.

### Nginx-Konfiguration erzeugen

```bash
export PILOT_HOST="pilot.local"
export PILOT_CERT="/tmp/pilot-ssl/pilot.crt"
export PILOT_KEY="/tmp/pilot-ssl/pilot.key"
export PILOT_STATIC_ROOT="$PWD/staticfiles"

envsubst '${PILOT_HOST} ${PILOT_CERT} ${PILOT_KEY} ${PILOT_STATIC_ROOT}' \
  < deploy/pilot/nginx-https.conf.template \
  > /tmp/nginx-pilot.conf
```

### Start

1. **Gunicorn Backend (nur Loopback, nicht im LAN exponiert):**
   ```bash
   export GUNICORN_BIND="127.0.0.1:8000"
   gunicorn --config config/gunicorn.py config.wsgi:application
   ```

2. **Nginx Reverse Proxy:**
   ```bash
   nginx -c /tmp/nginx-pilot.conf
   ```

---

## 5. Prüfkommandos

### HTTPS-Verbindung und Zertifikat testen

```bash
# Abruf mit Validierung gegen CA oder self-signed (-k nur zur Protokollprüfung):
curl -iv --resolve pilot.local:443:127.0.0.1 https://pilot.local/healthz/

# Prüfen von Secure-Cookies und Sicherheitsheadern:
curl -sI -k https://127.0.0.1/anmelden/ | grep -iE 'set-cookie|x-frame-options|strict-transport-security'
```

Erwartetes Ergebnis:
- `Set-Cookie: ...; Secure; SameSite=Lax`
- `X-Frame-Options: DENY`
- Kein permanentes HSTS im Header (`Strict-Transport-Security` fehlt oder `max-age=0`)

### CSRF-Schutz validieren

```bash
# POST ohne CSRF-Token muss HTTP 403 liefern:
curl -s -o /dev/null -w "%{http_code}\n" -k -X POST https://127.0.0.1/anmelden/
# Erwartung: 403
```

---

## 6. Ehrliche Grenzen des Pilotbetriebs

1. **Kein Produktionszertifikat:** Selbstsignierte Zertifikate oder lokale CAs eignen sich ausschließlich für lokale Tests. Für einen realen Betrieb ist eine offizielle PKI oder Let's Encrypt erforderlich.
2. **Keine Hardware-/Geräteabnahme:** Lokale Loopback-Tests ersetzen keine Netzwerk- und Geräteabnahme (z. B. Standalone-WLAN auf Raspberry Pi, Mobilgeräte mit iOS/Android, getrennte Subnetze).
3. **Keine Host-/Netzwerkänderungen im Container:** Das Deployment verändert weder Host-Netzwerkports noch bindet es Cloud-Dienste an.
4. **Proxy-Access-Log:** Anwendungsseitige Redaktion schützt die Gunicorn-/Django-Logs, nicht aber ungefilterte externe Proxy-Logs. Die Deaktivierung für `/aktivieren/` im Proxy ist eine notwendige Kompensation.
