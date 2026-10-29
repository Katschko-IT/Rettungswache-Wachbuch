from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .access import CONTENT_ROLES, get_membership
from .signal_messenger import signal_enabled
from .models import HandoverEntry


def current_membership(request):
    user = getattr(request, "user", None)
    membership = get_membership(user) if user and getattr(user, "is_authenticated", False) else None
    nav_urgent_count = 0
    if membership and membership.role in CONTENT_ROLES:
        nav_urgent_count = (
            HandoverEntry.objects.filter(
                station=membership.station,
                priority=HandoverEntry.Priority.URGENT,
            )
            .exclude(status=HandoverEntry.Status.DONE)
            .count()
        )
    from .navigation import CATALOG, more_config, nav_config

    station = membership.station if membership else None
    config = nav_config(station)
    nav_keys = [entry["key"] for entry in config["entries"]]
    current = _current_url_name(request)
    for entry in config["entries"]:
        entry["current"] = _matches_prefix(current, entry["active"])
    return {
        "current_membership": membership,
        "nav_urgent_count": nav_urgent_count,
        "nav_conf": config,
        "nav_keys": nav_keys,
        # „Mehr“ gilt als aktiv, wenn die aktuelle Seite zu einem Bereich
        # gehört, der nicht in der Leiste steht.
        "more_active": _more_tab_is_active(request, nav_keys),
        "more_order": more_config(station),
        "display_station": station,
    }


def _current_url_name(request):
    match = getattr(request, "resolver_match", None)
    return getattr(match, "url_name", "") if match else ""


def _matches_prefix(url_name, prefixes):
    return any(url_name == prefix or url_name.startswith(prefix) for prefix in prefixes)


def _more_tab_is_active(request, nav_keys):
    from .navigation import CATALOG

    url_name = _current_url_name(request)
    if not url_name or url_name == "more":
        return False
    in_bar = any(
        key in nav_keys and _matches_prefix(url_name, CATALOG[key][3]) for key in CATALOG
    )
    in_more = any(
        key not in nav_keys and _matches_prefix(url_name, CATALOG[key][3]) for key in CATALOG
    )
    return in_more and not in_bar


def application_metadata(request):
    from .community_views import registration_enabled
    from .demo import demo_accounts_for_display, demo_mode_enabled, demo_password
    from .demo_sandbox import demo_banner, demo_tour, sandbox_enabled
    from .privacy_models import DataProtectionOfficer
    from .push import web_push_enabled
    from .webauthn_auth import webauthn_enabled

    demo = demo_mode_enabled()
    public_dpo_contacts = (
        DataProtectionOfficer.objects.filter(
            is_active=True,
            publish_in_privacy_notice=True,
            station__is_active=True,
            station__demo_sandbox__isnull=True,
        )
        .select_related("station")
        .order_by("station__name", "-is_primary", "display_name")
    )
    return {
        "app_name": settings.APP_NAME,
        "source_url": settings.SOURCE_URL,
        "app_version": settings.APP_VERSION,
        "mfa_enabled": bool(getattr(settings, "MFA_ENABLED", True)),
        "webauthn_enabled": webauthn_enabled(),
        "web_push_enabled": web_push_enabled(),
        "registration_enabled": registration_enabled(),
        "demo_mode": demo,
        "demo_password": demo_password() if demo else "",
        "demo_accounts": demo_accounts_for_display() if demo and not sandbox_enabled() else [],
        "demo_sandbox_enabled": sandbox_enabled(),
        "demo_banner": demo_banner(request),
        "demo_tour": demo_tour(request),
        "public_data_protection_officers": public_dpo_contacts,
        "site_profile": SimpleLazyObject(_current_site_profile),
        "signal_enabled": signal_enabled(),
    }


def _current_site_profile():
    from .site_profile import SiteProfile

    return SiteProfile.current()
