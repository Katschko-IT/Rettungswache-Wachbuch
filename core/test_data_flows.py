"""Tests für die Datenfluss-Übersicht (Paket E2).

Prüft:
- core.data_flows und die Übereinstimmung mit docs/DATENFLUESSE.md (<!-- flow: KEY -->),
- die Erkennung aktiver vs. abgeschalteter Dienste zur Laufzeit,
- die Darstellung auf der öffentlichen Datenschutzseite (/datenschutz/),
- die Hilfetexte für kirchliche Aufsichtsbehörden (KDG / DSG-EKD).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from core.data_flows import (
    FLOW_MAP,
    FLOW_SPECS,
    DataFlow,
    get_active_data_flows,
    get_data_flow,
    get_data_flows,
    get_disabled_data_flows,
    has_active_flows,
    inspect_data_flows,
)
from core.forms import SetupWizardForm, SiteProfileForm
from core.models import Station
from core.site_profile import SiteProfile


class DataFlowsDocSyncTests(TestCase):
    """Vertrag mit docs/DATENFLUESSE.md: jeder Schlüssel hat ein <!-- flow: KEY -->."""

    def test_all_flows_have_matching_doc_comment_and_vice_versa(self):
        doc_path = Path(settings.BASE_DIR) / "docs" / "DATENFLUESSE.md"
        self.assertTrue(doc_path.exists(), f"{doc_path} existiert nicht")
        content = doc_path.read_text(encoding="utf-8")

        doc_keys = set(re.findall(r"<!--\s*flow:\s*([a-z_]+)\s*-->", content))
        spec_keys = {spec.key for spec in FLOW_SPECS}

        self.assertEqual(
            doc_keys,
            spec_keys,
            f"Unterschied zwischen docs/DATENFLUESSE.md ({doc_keys - spec_keys}) "
            f"und core/data_flows.py ({spec_keys - doc_keys})",
        )

    def test_get_data_flow_by_key(self):
        flow = get_data_flow("email")
        self.assertIsNotNone(flow)
        self.assertEqual(flow.key, "email")
        self.assertIn("SMTP", flow.recipient)

        unknown = get_data_flow("does_not_exist")
        self.assertIsNone(unknown)

    def test_in_application_filter(self):
        all_flows = get_data_flows()
        in_app_flows = get_data_flows(in_application_only=True)
        self.assertLess(len(in_app_flows), len(all_flows))
        for flow in in_app_flows:
            self.assertTrue(flow.in_application)

    def test_inspect_data_flows_alias(self):
        self.assertEqual(get_data_flows(), inspect_data_flows())


class DataFlowDetectionTests(TestCase):
    """Erkennung des aktiven Zustands der einzelnen Dienste."""

    def setUp(self):
        Station.objects.all().delete()

    def test_weather_flow_detection(self):
        flow = get_data_flow("weather")
        self.assertFalse(flow.is_active)

        station = Station.objects.create(name="Wache 1", slug="w1", weather_enabled=True)
        flow = get_data_flow("weather")
        self.assertTrue(flow.is_active)

        station.weather_enabled = False
        station.save()
        flow = get_data_flow("weather")
        self.assertFalse(flow.is_active)

    def test_traffic_flow_detection(self):
        flow = get_data_flow("traffic")
        self.assertFalse(flow.is_active)

        station = Station.objects.create(name="Wache 2", slug="w2", traffic_enabled=True)
        flow = get_data_flow("traffic")
        self.assertTrue(flow.is_active)

        station.traffic_enabled = False
        station.save()
        self.assertFalse(get_data_flow("traffic").is_active)

    def test_traffic_local_flow_detection(self):
        flow = get_data_flow("traffic_local")
        self.assertFalse(flow.is_active)

        station = Station.objects.create(name="Wache 3", slug="w3", traffic_local_sources=True)
        self.assertTrue(get_data_flow("traffic_local").is_active)

    def test_feeds_flow_detection(self):
        flow = get_data_flow("feeds")
        self.assertFalse(flow.is_active)

        Station.objects.create(name="Wache 4", slug="w4", feeds_enabled=True)
        self.assertTrue(get_data_flow("feeds").is_active)

    def test_waste_calendar_flow_detection(self):
        flow = get_data_flow("waste_calendar")
        self.assertFalse(flow.is_active)

        Station.objects.create(
            name="Wache 5",
            slug="w5",
            waste_calendar_enabled=True,
            waste_calendar_url="https://abfall.example.org/ics",
        )
        self.assertTrue(get_data_flow("waste_calendar").is_active)

    @override_settings(WEB_PUSH_ENABLED=False)
    def test_web_push_flow_disabled(self):
        self.assertFalse(get_data_flow("web_push").is_active)

    @override_settings(WEB_PUSH_ENABLED=True)
    def test_web_push_flow_enabled(self):
        self.assertTrue(get_data_flow("web_push").is_active)

    @override_settings(PUSH_RELAY_URL="")
    def test_push_relay_disabled(self):
        self.assertFalse(get_data_flow("push_relay").is_active)

    @override_settings(PUSH_RELAY_URL="https://relay.example.org/v1/push")
    def test_push_relay_enabled(self):
        self.assertTrue(get_data_flow("push_relay").is_active)

    @override_settings(SIGNAL_API_URL="", SIGNAL_NUMBER="")
    def test_signal_disabled(self):
        self.assertFalse(get_data_flow("signal").is_active)

    @override_settings(SIGNAL_API_URL="http://signal:8080", SIGNAL_NUMBER="+4915112345678")
    def test_signal_enabled(self):
        self.assertTrue(get_data_flow("signal").is_active)

    @override_settings(EMAIL_HOST="", DEMO_SANDBOX=False)
    def test_email_disabled_without_host(self):
        self.assertFalse(get_data_flow("email").is_active)

    @override_settings(EMAIL_HOST="smtp.example.org", DEMO_SANDBOX=False)
    def test_email_enabled_with_host(self):
        self.assertTrue(get_data_flow("email").is_active)

    @override_settings(EMAIL_HOST="smtp.example.org", DEMO_SANDBOX=True)
    def test_email_disabled_in_demo_sandbox(self):
        self.assertFalse(get_data_flow("email").is_active)

    @override_settings(PING_URL="")
    def test_health_ping_flow(self):
        with patch.dict(os.environ, {"PING_URL": ""}):
            self.assertFalse(get_data_flow("health_ping").is_active)

        with patch.dict(os.environ, {"PING_URL": "https://hc-ping.example/uuid"}):
            self.assertTrue(get_data_flow("health_ping").is_active)

    @override_settings(WACHBUCH_MODE="lan")
    def test_acme_disabled_in_lan_mode(self):
        self.assertFalse(get_data_flow("acme").is_active)

    @override_settings(WACHBUCH_MODE="domain")
    def test_acme_enabled_in_domain_mode(self):
        self.assertTrue(get_data_flow("acme").is_active)

    @override_settings(BACKUP_OFF_TARGET="")
    def test_offsite_flow(self):
        with patch.dict(os.environ, {"BACKUP_OFF_TARGET": ""}):
            self.assertFalse(get_data_flow("offsite").is_active)
        with patch.dict(os.environ, {"BACKUP_OFF_TARGET": "user@backup.example.com:/data"}):
            self.assertTrue(get_data_flow("offsite").is_active)

    def test_hosting_flow_station_vs_external(self):
        SiteProfile.objects.all().delete()
        self.assertFalse(get_data_flow("hosting").is_active)

        profile = SiteProfile.objects.create(
            singleton=1,
            operator_name="Test Operator",
            city="Berlin",
            server_location=SiteProfile.ServerLocation.STATION,
            hosting_provider="",
        )
        self.assertFalse(get_data_flow("hosting").is_active)

        profile.hosting_provider = "Hetzner Online GmbH"
        profile.save()
        self.assertTrue(get_data_flow("hosting").is_active)

        profile.hosting_provider = ""
        profile.server_location = SiteProfile.ServerLocation.GERMANY
        profile.save()
        self.assertTrue(get_data_flow("hosting").is_active)


class PrivacyViewDataFlowsTests(TestCase):
    """Prüfung der Darstellung auf der öffentlichen Seite /datenschutz/."""

    def setUp(self):
        Station.objects.all().delete()
        SiteProfile.objects.all().delete()

    @override_settings(
        EMAIL_HOST="",
        SIGNAL_API_URL="",
        SIGNAL_NUMBER="",
        PUSH_RELAY_URL="",
        WEB_PUSH_ENABLED=False,
        WACHBUCH_MODE="lan",
    )
    def test_privacy_page_lists_data_flows_section(self):
        with patch.dict(os.environ, {"PING_URL": "", "BACKUP_OFF_TARGET": ""}):
            response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Externe Datenflüsse dieser Installation")
        # In default state (no flows active in app), island mode or empty active flows
        self.assertContains(response, 'data-flow="email"')
        self.assertContains(response, 'data-flow-status="disabled"')
        self.assertContains(response, 'data-flow="signal"')
        self.assertContains(response, 'data-flow="web_push"')

    @override_settings(
        EMAIL_HOST="smtp.test.example",
        SIGNAL_API_URL="http://signal:8080",
        SIGNAL_NUMBER="+4915100000000",
        PUSH_RELAY_URL="https://relay.example.org/v1/push",
        WEB_PUSH_ENABLED=True,
    )
    def test_privacy_page_renders_active_flows(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)

        # Active flows present
        self.assertContains(response, 'data-flow="email"')
        self.assertContains(response, 'data-flow="signal"')
        self.assertContains(response, 'data-flow="push_relay"')
        self.assertContains(response, 'data-flow="web_push"')
        self.assertContains(response, 'data-flow-status="active"')

        active_flows = response.context["active_data_flows"]
        active_keys = {f.key for f in active_flows}
        self.assertTrue({"email", "signal", "push_relay", "web_push"}.issubset(active_keys))

    def test_privacy_page_weather_active_when_station_enabled(self):
        Station.objects.create(name="RW Alpha", slug="alpha", weather_enabled=True)
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)

        active_flows = response.context["active_data_flows"]
        active_keys = {f.key for f in active_flows}
        self.assertIn("weather", active_keys)
        self.assertContains(response, 'data-flow="weather"')


class ChurchSupervisoryAuthorityTests(TestCase):
    """Hilfetext-Prüfung für kirchliche Aufsichtsbehörden (KDG / DSG-EKD)."""

    def test_setup_wizard_form_supervisory_authority_help_text(self):
        form = SetupWizardForm()
        help_text = str(form.fields["supervisory_authority"].help_text)
        self.assertIn("KDG", help_text)
        self.assertIn("DSG-EKD", help_text)

    def test_site_profile_form_supervisory_authority_help_text(self):
        form = SiteProfileForm()
        help_text = str(form.fields["supervisory_authority"].help_text)
        self.assertIn("KDG", help_text)
        self.assertIn("DSG-EKD", help_text)
