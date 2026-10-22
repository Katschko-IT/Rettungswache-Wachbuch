# Bereitstellungsanleitung – Rettungswache-Wachbuch

*Letzte Aktualisierung: August 2026 | Version: 0.15.0*

---

## 📋 **Inhaltsverzeichnis**

1. [Bereitstellungsoptionen](#-bereitstellungsoptionen)
2. [Docker Compose (Standard)](#-docker-compose-standard)
3. [Nginx als Reverse Proxy mit WAF](#-nginx-als-reverse-proxy-mit-waf)
4. [Traefik als Reverse Proxy](#-traefik-als-reverse-proxy)
5. [Kubernetes (für große Installationen)](#-kubernetes-für-große-installationen)
6. [Konfiguration](#-konfiguration)
7. [Sicherheitshärtung](#-sicherheitshärtung)

---

## 🚀 **Bereitstellungsoptionen**

| Option | Komplexität | Skalierbarkeit | Empfohlen für |
|--------|-------------|----------------|---------------|
| **Docker Compose** | ⭐ | ⭐⭐ | Entwicklung, kleine Produktion |
| **Docker Compose + Nginx** | ⭐⭐ | ⭐⭐⭐ | Produktion (bis 1000 Benutzer) |
| **Docker Compose + Traefik** | ⭐⭐ | ⭐⭐⭐ | Produktion mit Let's Encrypt |
| **Kubernetes** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Große Installationen |

---

## 🐳 **Docker Compose (Standard)**

### **1. Voraussetzungen**

- Docker Engine ≥ 20.10
- Docker Compose ≥ v2
- Git
- 1 GB RAM, 500 MB Festplattenspeicher

### **2. Installation**

```bash
# Repository klonen
git clone https://github.com/Katschko-IT/Rettungswache-Wachbuch.git
cd Rettungswache-Wachbuch

# Umgebungsvariablen kopieren
cp .env.example .env

# .env mit sicheren Werten füllen
# Alle PLATZHALTER durch zufällige Werte ersetzen:
# openssl rand -hex 32

# Backup-Verzeichnis vorbereiten
sudo mkdir -p backups
sudo chown 70:70 backups

# Container starten
docker compose up --build -d

# Migrationen ausführen
docker compose exec web python manage.py migrate

# Admin-Benutzer erstellen
docker compose exec web python manage.py createsuperuser

# Admin als Stations-Admin festlegen
docker compose exec web python manage.py grant_station_admin BENUTZERNAME
```

### **3. Zugriff**

- **Web-UI**: [http://127.0.0.1:8090/](http://127.0.0.1:8090/)
- **Login**: [http://127.0.0.1:8090/anmelden/](http://127.0.0.1:8090/anmelden/)

⚠️ **Wichtig**: Der Port bindet nur an **Loopback (127.0.0.1)**. Für externe Zugriffe ist ein **Reverse Proxy** erforderlich.

---

## 🔒 **Nginx als Reverse Proxy mit WAF**

Diese Konfiguration bietet:
- **TLS-Terminierung** (HTTPS)
- **Web Application Firewall (WAF)** mit ModSecurity
- **Rate Limiting**
- **Security Headers**
- **Static File Serving**

### **1. Voraussetzungen**

- Nginx ≥ 1.25
- ModSecurity (libmodsecurity) ≥ 2.9
- Certbot für Let's Encrypt
- Domain (z.B. `wache.example.org`)

### **2. Installation**

#### **Nginx + ModSecurity installieren (Ubuntu)**

```bash
# Nginx installieren
sudo apt update
sudo apt install -y nginx

# ModSecurity installieren
sudo apt install -y libmodsecurity3 libapache2-mod-security2

# ModSecurity für Nginx konfigurieren
sudo apt install -y nginx-module-modsecurity

# Nginx mit ModSecurity neu kompilieren (falls nötig)
sudo apt install -y nginx-extras
```

#### **ModSecurity Core Rule Set (CRS) installieren**

```bash
# CRS Repository klonen
git clone https://github.com/coreruleset/coreruleset /etc/nginx/modsec/crs

# CRS konfigurieren
cd /etc/nginx/modsec/crs
cp crs-setup.conf.example crs-setup.conf

# Nginx-Konfiguration für ModSecurity
sudo mkdir -p /etc/nginx/modsec
sudo cp /usr/share/modsecurity-crs/modsecurity_crs_10_setup.conf /etc/nginx/modsec/
```

### **3. Nginx-Konfiguration**

#### **Hauptkonfiguration (`/etc/nginx/nginx.conf`)**

```nginx
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

# ModSecurity laden
load_module modules/ngx_http_modsecurity_module.so;

# Performance-Einstellungen
events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    # Basic Settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 75s;
    types_hash_max_size 2048;
    server_tokens off;
    server_names_hash_bucket_size 128;

    # Buffer Settings
    client_max_body_size 10M;
    client_body_buffer_size 128k;
    client_header_buffer_size 2k;
    large_client_header_buffers 4 8k;

    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log warn;

    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript application/xml+rss application/atom+xml image/svg+xml;

    # Include ModSecurity Configuration
    modsecurity on;
    modsecurity_rules_file /etc/nginx/modsec/modsecurity.conf;

    # Include Sites
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
```

#### **ModSecurity-Konfiguration (`/etc/nginx/modsec/modsecurity.conf`)**

```nginx
# ModSecurity Core Rules
SecRuleEngine On
SecRuleUpdateTargetById 941180 "!REQUEST_HEADERS:User-Agent"

# CRS Setup
Include /etc/nginx/modsec/crs/crs-setup.conf
Include /etc/nginx/modsec/crs/rules/*.conf

# WAF-Regeln für Rettungswache-Wachbuch
SecRule REQUEST_FILENAME "@pm /api/v1/token/ /api/v1/anmeldung/" \
    "id:1001,phase:1,nolog,pass,ctl:ruleRemoveById=941180"

# Rate Limiting für Login-Endpunkte
SecRule REQUEST_FILENAME "@pm /api/v1/token/ /api/v1/anmeldung/" \
    "id:1002,phase:5,nolog,pass,setvar:ip.rate_limit_login=+1"

SecRule IP:RATE_LIMIT_LOGIN "@gt 10" \
    "id:1003,phase:5,deny,status:429,msg:'Too many login attempts'"

# SQL Injection Schutz
SecRule REQUEST_BODY "@detectSQLi" \
    "id:1004,phase:2,deny,status:403,msg:'SQL Injection Attempt'"

# XSS Schutz
SecRule REQUEST_BODY "@detectXSS" \
    "id:1005,phase:2,deny,status:403,msg:'XSS Attempt'"

# Path Traversal Schutz
SecRule REQUEST_FILENAME "@pm ../ @pm ./" \
    "id:1006,phase:1,deny,status:403,msg:'Path Traversal Attempt'"
```

#### **Site-Konfiguration (`/etc/nginx/sites-available/wachbuch`)**

```nginx
# HTTP → HTTPS Redirect
server {
    listen 80;
    server_name wache.example.org;
    
    # Security Headers für HTTP
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    
    # Redirect zu HTTPS
    return 301 https://$host$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name wache.example.org;

    # SSL-Zertifikate
    ssl_certificate /etc/letsencrypt/live/wache.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wache.example.org/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/wache.example.org/chain.pem;

    # SSL-Einstellungen
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers on;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
    add_header Cross-Origin-Opener-Policy "same-origin" always;
    add_header Cross-Origin-Resource-Policy "same-origin" always;
    add_header Cross-Origin-Embedder-Policy "require-corp" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    
    # Content Security Policy
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self' https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; upgrade-insecure-requests; block-all-mixed-content" always;

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    limit_req zone=api burst=200 nodelay;

    # Proxy zu Django
    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 16k;
        proxy_busy_buffers_size 24k;
        proxy_max_temp_file_size 2048m;
    }

    # Static Files direkt servieren
    location /static/ {
        alias /path/to/rettungswache-wachbuch/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    # Health Check
    location /healthz/ {
        proxy_pass http://127.0.0.1:8090/healthz/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Media Files (falls vorhanden)
    location /media/ {
        alias /path/to/rettungswache-wachbuch/media/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }
}
```

### **4. Let's Encrypt Zertifikate einrichten**

```bash
# Certbot installieren
sudo apt install -y certbot python3-certbot-nginx

# Zertifikat anfordern
sudo certbot --nginx -d wache.example.org

# Automatische Erneuerung einrichten
sudo certbot renew --dry-run
```

### **5. Nginx neu starten**

```bash
# Konfiguration testen
sudo nginx -t

# Nginx neu starten
sudo systemctl restart nginx

# Status prüfen
sudo systemctl status nginx
```

---

## 🌐 **Traefik als Reverse Proxy**

Traefik ist eine moderne Alternative zu Nginx mit automatischer Let's Encrypt-Integration.

### **1. docker-compose.override.yml erstellen**

```yaml
# docker-compose.override.yml
version: '3.8'

services:
  traefik:
    image: traefik:v2.10
    container_name: traefik
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.email=admin@wache.example.org
      - --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json
      - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
      - --api.dashboard=true
      - --api.insecure=false
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    networks:
      - web-ingress
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.traefik.rule=Host(`traefik.wache.example.org`)"
      - "traefik.http.routers.traefik.service=api@internal"
      - "traefik.http.routers.traefik.entrypoints=websecure"
      - "traefik.http.routers.traefik.tls.certresolver=letsencrypt"
      - "traefik.http.routers.traefik.middlewares=traefik-auth"
      - "traefik.http.middlewares.traefik-auth.basicauth.users=admin:$$apr1$$9Cv/OMGj$$ZomWQzuQbL.3TRCS81A1g/"

  web:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.web.rule=Host(`wache.example.org`)"
      - "traefik.http.routers.web.entrypoints=websecure"
      - "traefik.http.routers.web.tls.certresolver=letsencrypt"
      - "traefik.http.routers.web.tls.options=default"
      - "traefik.http.services.web.loadbalancer.server.port=8000"
      - "traefik.http.routers.web.middlewares=security-headers,rate-limit"
    networks:
      - web-ingress

networks:
  web-ingress:
    external: false
```

### **2. Traefik Middlewares konfigurieren**

```yaml
# docker-compose.override.yml (Fortsetzung)
services:
  traefik:
    # ... (vorherige Konfiguration)
    command:
      # ... (vorherige Command-Args)
      - --entrypoints.websecure.http.middlewares=security-headers@docker
      - --entrypoints.websecure.http.middlewares=rate-limit@docker

# Middleware für Security Headers
  security-headers:
    image: traefik:v2.10
    container_name: traefik-security-headers
    command: --api.insecure=true --providers.docker
    labels:
      - "traefik.enable=true"
      - "traefik.http.middlewares.security-headers.headers.customresponseheaders.X-Content-Type-Options=nosniff"
      - "traefik.http.middlewares.security-headers.headers.customresponseheaders.X-Frame-Options=DENY"
      - "traefik.http.middlewares.security-headers.headers.customresponseheaders.X-XSS-Protection=1; mode=block"
      - "traefik.http.middlewares.security-headers.headers.customresponseheaders.Referrer-Policy=strict-origin-when-cross-origin"
      - "traefik.http.middlewares.security-headers.headers.customresponseheaders.Permissions-Policy=camera=(), microphone=(), geolocation=(), payment=()"
      - "traefik.http.middlewares.security-headers.headers.customresponseheaders.Strict-Transport-Security=max-age=31536000; includeSubDomains; preload"
      - "traefik.http.middlewares.security-headers.headers.contentsecuritypolicy=default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self' https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"

# Middleware für Rate Limiting
  rate-limit:
    image: traefik:v2.10
    container_name: traefik-rate-limit
    command: --api.insecure=true --providers.docker
    labels:
      - "traefik.enable=true"
      - "traefik.http.middlewares.rate-limit.ratelimit.average=100"
      - "traefik.http.middlewares.rate-limit.ratelimit.burst=200"
```

---

## 🐳 **Kubernetes (für große Installationen)**

### **1. Voraussetzungen**

- Kubernetes Cluster (EKS, GKE, AKS, oder selbst gehostet)
- kubectl ≥ 1.25
- Helm ≥ 3.0
- 4+ CPU Kerne, 8+ GB RAM

### **2. Helm-Chart erstellen**

```yaml
# Chart.yaml
apiVersion: v2
name: rettungswache-wachbuch
version: 0.15.0
description: Selbstgehostetes Wachbuch für Rettungswachen

# values.yaml
replicaCount: 3

image:
  repository: ghcr.io/katschko-it/rettungswache-wachbuch
  tag: latest
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: wache.example.org
      paths:
        - path: /
          pathType: Prefix
  tls:
    - hosts:
        - wache.example.org
      secretName: wachbuch-tls

postgresql:
  enabled: true
  auth:
    postgresPassword: ""
    username: rwsth_app
    password: ""
    database: rwsth
  primary:
    persistence:
      size: 10Gi

redis:
  enabled: true
  architecture: standalone
  auth:
    enabled: false

persistence:
  enabled: true
  size: 5Gi

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi

autoscale:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

### **3. Bereitstellung**

```bash
# Helm Repository hinzufügen
helm repo add bitnami https://charts.bitnami.com/bitnami

# Chart installieren
helm install rettungswache-wachbuch ./chart/rettungswache-wachbuch \
  --set image.tag=0.15.0 \
  --set postgresql.auth.postgresPassword=$(openssl rand -hex 32) \
  --set postgresql.auth.password=$(openssl rand -hex 32)

# Status prüfen
kubectl get pods
kubectl get svc
kubectl get ingress
```

---

## ⚙️ **Konfiguration**

### **1. Umgebungsvariablen (.env)**

Siehe [OPERATIONS.md](OPERATIONS.md) für eine detaillierte Liste aller Konfigurationsoptionen.

### **2. Wichtige Einstellungen**

| Einstellung | Empfehlung | Beschreibung |
|-------------|-------------|--------------|
| `DJANGO_DEBUG` | `false` | Debug-Modus deaktivieren |
| `SECURE_COOKIES` | `true` | Sichere Cookies erzwingen |
| `MFA_REQUIRED` | `true` | MFA für alle Benutzer erzwingen |
| `REDIS_HOST` | `redis` | Redis-Host für Caching |
| `GUNICORN_WORKERS` | `2x CPU + 1` | Anzahl Gunicorn-Worker |

---

## 🔒 **Sicherheitshärtung**

### **1. Checkliste für Produktion**

- [ ] **TLS-Zertifikat** installiert und gültig
- [ ] **Debug-Modus** deaktiviert (`DJANGO_DEBUG=false`)
- [ ] **Sichere Cookies** aktiviert (`SECURE_COOKIES=true`)
- [ ] **MFA** für alle Benutzer erzwungen (`MFA_REQUIRED=true`)
- [ ] **Security Headers** konfiguriert (CSP, HSTS, etc.)
- [ ] **Rate Limiting** aktiviert
- [ ] **Firewall** konfiguriert (nur Ports 80, 443 offen)
- [ ] **Backups** eingerichtet und getestet
- [ ] **Monitoring** eingerichtet (Prometheus, Grafana)
- [ ] **Logging** konfiguriert (ELK-Stack oder ähnlich)

### **2. Sicherheits-Tools**

| Tool | Zweck | Installation |
|------|-------|--------------|
| **Fail2Ban** | Brute-Force-Schutz | `sudo apt install fail2ban` |
| **ClamAV** | Viren-Scanning | `sudo apt install clamav` |
| **Rkhunter** | Rootkit-Erkennung | `sudo apt install rkhunter` |
| **Lynis** | Sicherheits-Audit | `sudo apt install lynis` |

### **3. Regelmäßige Sicherheitsprüfungen**

```bash
# System-Updates prüfen
sudo apt update && sudo apt upgrade -y

# Sicherheits-Updates prüfen
sudo apt list --upgradable | grep -i security

# Offene Ports prüfen
sudo netstat -tulnp

# Laufende Dienste prüfen
sudo systemctl list-units --type=service

# Fail2Ban-Logs prüfen
sudo tail -f /var/log/fail2ban.log

# Nginx-Logs prüfen
sudo tail -f /var/log/nginx/error.log
```

---

## 📚 **Weiterführende Dokumentation**

- [Architektur](ARCHITECTURE.md) – Technische Architektur
- [Sicherheit & Datenschutz](SECURITY-PRIVACY.md) – Sicherheitskonzept
- [API v1](API.md) – REST-API-Dokumentation
- [Betrieb](OPERATIONS.md) – Backup, Updates, Monitoring
- [Go-Live-Checkliste](GO-LIVE-CHECKLIST.md) – Vorbereitung für Produktion

---

*Letzte Aktualisierung: August 2026 | Version: 0.15.0*