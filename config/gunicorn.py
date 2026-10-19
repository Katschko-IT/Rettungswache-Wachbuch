"""Gunicorn configuration for Rettungswache-Wachbuch.

This configuration optimizes Gunicorn for production use with:
- Multiple worker processes (2x CPU cores + 1)
- Threaded workers for concurrent request handling
- Timeouts and connection limits for stability
- Graceful worker recycling to prevent memory leaks

Usage:
    gunicorn --config config/gunicorn.py config.wsgi:application

For development, use:
    gunicorn --reload --workers 1 --threads 1 config.wsgi:application
"""

import multiprocessing
import os

# Worker Settings
# -----------------
# Number of workers: 2x CPU cores + 1 (recommended for CPU-bound workloads)
# For I/O-bound workloads (like Django with database), you can use more workers
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Worker class: Use gthread for I/O-bound applications (Django + PostgreSQL)
# Options: sync, async, gthread, gevent, tornado
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")

# Number of threads per worker (only used with gthread worker class)
threads = int(os.getenv("GUNICORN_THREADS", 4))

# Maximum number of simultaneous clients per worker
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", 1000))

# Performance Settings
# --------------------
# Maximum number of requests a worker will process before restarting
# This helps prevent memory leaks
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))

# Maximum jitter to add to max_requests (random value between 0 and this number)
# This prevents all workers from restarting at the same time
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 50))

# Timeout for worker processes (seconds)
# Workers that don't complete a request within this time will be killed
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))

# Timeout for graceful worker restart (seconds)
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Keepalive settings (seconds)
# Time to wait for connections on a Keep-Alive connection
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 2))

# Server Settings
# ---------------
# Bind address and port
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Backlog of unaccepted connections
backlog = int(os.getenv("GUNICORN_BACKLOG", 2048))

# Security Settings
# ------------------
# Chroot to this directory (optional, for security)
# chroot = "/app"

# Drop privileges to this user/group (optional, for security)
# uid = "app"
# gid = "app"

# Logging Settings
# -----------------
# Log level: debug, info, warning, error, critical
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")

# Log file path (use - for stdout)
# accesslog = "-"
# errorlog = "-"

# Enable access log
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# StatsD Settings (optional, for monitoring)
# --------------------------------
# statsd_host = "localhost:8125"
# statsd_prefix = "rettungswache"

# PROMETHEUS METRICS (optional, for monitoring)
# -------------------------------------------
# To enable Prometheus metrics, install gunicorn-prometheus:
# pip install gunicorn-prometheus
# Then uncomment the following:
# from gunicorn_prometheus import PrometheusMetrics
# metrics = PrometheusMetrics(worker=workers, worker_class=worker_class)

# Redact one-time activation tokens from access-log atoms.
logger_class = "core.gunicorn_logging.RedactingGunicornLogger"
