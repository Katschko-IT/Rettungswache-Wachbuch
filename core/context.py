from django.conf import settings

from .access import CONTENT_ROLES, get_membership
from .models import HandoverEntry


def current_membership(request):
    membership = get_membership(request.user) if request.user.is_authenticated else None
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
    from .navigation import more_config, nav_config

    station = membership.station if membership else None
    return {
        "current_membership": membership,
        "nav_urgent_count": nav_urgent_count,
        "nav_conf": nav_config(station),
        "more_order": more_config(station),
    }


def application_metadata(request):
    from .community_views import registration_enabled
    from .demo import demo_accounts_for_display, demo_mode_enabled, demo_password
    from .privacy_models import DataProtectionOfficer
    from .push import web_push_enabled
    from .webauthn_auth import webauthn_enabled

    demo = demo_mode_enabled()
    public_dpo_contacts = (
        DataProtectionOfficer.objects.filter(
            is_active=True,
            publish_in_privacy_notice=True,
            station__is_active=True,
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
        "demo_accounts": demo_accounts_for_display() if demo else [],
        "public_data_protection_officers": public_dpo_contacts,
    }
