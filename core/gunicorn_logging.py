"""Gunicorn access-logger that redacts one-time activation tokens.

External reverse-proxy logs are configured separately; this only protects the
gunicorn access log produced by ``--access-logfile``.
"""

from __future__ import annotations

from gunicorn import glogging

from core.errors import redact_request_path


class RedactingGunicornLogger(glogging.Logger):
    """Gunicorn logger that redacts activation tokens in access-log atoms."""

    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        for key in ("r", "U"):
            value = atoms.get(key)
            if value:
                atoms[key] = redact_request_path(value)
        return atoms


__all__ = ["RedactingGunicornLogger"]
