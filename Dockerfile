# syntax=docker/dockerfile:1

# --- Build: dependencies + collectstatic ---
FROM python:3.14.9-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN python -m venv /opt/venv

COPY requirements.lock .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes -r requirements.lock

COPY manage.py .
COPY config config
COPY core core
COPY locale locale
COPY templates templates
RUN SECRET_KEY=build-only-secret-key-not-used-at-runtime \
    DJANGO_DEBUG=true \
    DATABASE_URL=sqlite:////tmp/rwsth-build.sqlite3 \
    python manage.py collectstatic --noinput

# --- Runtime: slim image ---
FROM python:3.14.9-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8 AS runtime
# Patch OS packages so the runtime image does not ship known HIGH/CRITICAL CVEs
# (security fixes land in trixie-security before the next image rebuild).
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

LABEL org.opencontainers.image.title="Rettungswache-Wachbuch" \
      org.opencontainers.image.description="Selbst gehostetes Wachbuch fuer Rettungswachen" \
      org.opencontainers.image.source="https://github.com/Katschko-IT/Rettungswache-Wachbuch" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.version="0.15.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app manage.py .
COPY --chown=app:app config config
COPY --chown=app:app core core
COPY --chown=app:app locale locale
COPY --chown=app:app scripts scripts
COPY --chown=app:app templates templates
COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles
RUN chmod 755 /app/scripts/*.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/healthz/', headers={'Host': 'localhost'}), timeout=3)"]

CMD ["/app/scripts/start-web.sh"]
