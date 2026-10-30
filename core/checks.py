import os

from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def privacy_security_deployment_checks(app_configs, **kwargs):
    """Operator-facing checks for the documented GDPR/BSI production profile.

    These are warnings rather than hard startup failures because an existing
    installation may need a controlled key/retention migration first. The
    production runbook treats unresolved warnings as a release blocker.
    """

    warnings = []

    if not os.getenv("CRYPTO_MASTER_KEY", "").strip():
        warnings.append(
            Warning(
                "Kein dedizierter CRYPTO_MASTER_KEY konfiguriert.",
                hint=(
                    "Für Produktion einen zufälligen 32-Byte-Schlüssel (64 Hex-Zeichen) "
                    "getrennt vom DJANGO_SECRET_KEY verwenden und Rotation dokumentieren."
                ),
                id="wachbuch.W101",
            )
        )

    if not settings.MFA_REQUIRED and settings.DEMO_MODE and not getattr(settings, "DEMO_SANDBOX", False):
        # settings.py schaltet die Pflicht für die gemeinsame Vorführ-Demo ab,
        # auch wenn MFA_REQUIRED=true gesetzt ist; der Hinweis muss das sagen.
        warnings.append(
            Warning(
                "MFA-Pflicht ist durch DEMO_MODE abgeschaltet (gemeinsame Vorführ-Demo).",
                hint=(
                    "Für produktive Wachen DEMO_MODE=false setzen. Eine öffentliche Demo "
                    "mit DEMO_SANDBOX=true behält MFA_REQUIRED für die Konten der Installation."
                ),
                id="wachbuch.W102",
            )
        )
    elif not settings.MFA_REQUIRED:
        warnings.append(
            Warning(
                "MFA_REQUIRED ist deaktiviert.",
                hint=(
                    "Für produktive Administrator-/Beschäftigtenzugänge MFA_REQUIRED=true "
                    "setzen und den Wiederherstellungsprozess dokumentieren. Ist die Pflicht "
                    "im Einrichtungsassistenten bzw. unter Einstellungen → Impressum & "
                    "Datenschutz eingeschaltet, kann diese Warnung entfallen."
                ),
                id="wachbuch.W102",
            )
        )

    if not settings.SECURE_COOKIES:
        warnings.append(
            Warning(
                "Secure-Cookies sind deaktiviert.",
                hint="In Produktion SECURE_COOKIES=true und TLS am Reverse Proxy erzwingen.",
                id="wachbuch.W103",
            )
        )

    if getattr(settings, "RETENTION_AUDIT_DAYS", 0) <= 0:
        warnings.append(
            Warning(
                "Für Audit-Daten ist keine automatische Aufbewahrungsfrist konfiguriert.",
                hint=(
                    "RETENTION_AUDIT_DAYS nach dem freigegebenen Löschkonzept setzen; "
                    "0 darf nur mit dokumentierter Begründung verwendet werden."
                ),
                id="wachbuch.W104",
            )
        )

    return warnings
