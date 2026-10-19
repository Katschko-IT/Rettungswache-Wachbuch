"""Last-mile redaction for the application's configured log handlers.

External reverse-proxy/access loggers need their own deployment configuration.
"""
import logging

class ActivationRedactingFormatter(logging.Formatter):
    def format(self, record):
        from core.errors import redact_request_path
        # Redact AFTER %-formatting, including mapping arguments and traceback text.
        # Preserve the LogRecord for unrelated consumers; protect the configured sink.
        return redact_request_path(super().format(record))
