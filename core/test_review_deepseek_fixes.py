"""Regressionstests für DeepSeek-Reparaturen R3, R4, R5."""
from datetime import datetime, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from core.feed_sync import safe_item_url
from core.waste_sync import parse_ics
from core.test_wachalltag_api import WachalltagApiTests


class SafeItemUrlTests(SimpleTestCase):
    @override_settings(FEED_ALLOWED_HOSTS=['allowed.example'])
    def test_malformed_port_returns_empty(self):
        self.assertEqual(safe_item_url('https://allowed.example:abc/item'), '')

    @override_settings(FEED_ALLOWED_HOSTS=['allowed.example'])
    def test_port_too_large_returns_empty(self):
        self.assertEqual(safe_item_url('https://allowed.example:999999/item'), '')

    @override_settings(FEED_ALLOWED_HOSTS=['allowed.example'])
    def test_broken_url_returns_empty(self):
        self.assertEqual(safe_item_url('https://[broken/item'), '')

    @override_settings(FEED_ALLOWED_HOSTS=['allowed.example'])
    def test_valid_url_preserved(self):
        self.assertEqual(
            safe_item_url('https://allowed.example:443/item?q=1'),
            'https://allowed.example:443/item?q=1'
        )


class ParseIcsTests(SimpleTestCase):
    def _parse(self, line):
        return parse_ics(
            'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Synthetic\n' + line + '\nEND:VEVENT\nEND:VCALENDAR'
        )[0][1]

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_tzid_foreign_zone(self):
        dt = self._parse('DTSTART;TZID=America/New_York:20261020T090000')
        self.assertEqual(
            dt.astimezone(ZoneInfo('UTC')),
            datetime(2026, 10, 20, 13, tzinfo=ZoneInfo('UTC'))
        )

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_tzid_quoted(self):
        dt = self._parse('DTSTART;TZID="America/New_York":20261020T090000')
        self.assertEqual(
            dt.astimezone(ZoneInfo('UTC')),
            datetime(2026, 10, 20, 13, tzinfo=ZoneInfo('UTC'))
        )

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_utc_z(self):
        dt = self._parse('DTSTART:20261020T090000Z')
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.utcoffset(), datetime_timezone.utc.utcoffset(None))

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_date_only(self):
        dt = self._parse('DTSTART;VALUE=DATE:20261020')
        self.assertEqual(dt.date().isoformat(), '2026-10-20')

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_unknown_tzid_raises(self):
        with self.assertRaises(ValueError):
            parse_ics(
                'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Synthetic\n'
                'DTSTART;TZID=Not/A_Real_Zone:20261020T090000\n'
                'END:VEVENT\nEND:VCALENDAR'
            )

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_empty_tzid_raises(self):
        with self.assertRaises(ValueError):
            parse_ics(
                'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Synthetic\n'
                'DTSTART;TZID="":20261020T090000\n'
                'END:VEVENT\nEND:VCALENDAR'
            )


class OversizedAttachmentUploadTests(WachalltagApiTests):
    def test_oversized_defect_attachment_returns_413_with_limit_text(self):
        """R3: Upload eines Defekt-Anhangs über 5 MiB muss 413 liefern."""
        # Defekt anlegen
        defect_response = self._json(
            'post',
            '/api/v1/defects/',
            {
                'title': 'Synthetic defect',
                'description': 'Created for oversized attachment test',
                'priority': 'normal'
            }
        )
        self.assertEqual(defect_response.status_code, 201)
        defect_id = defect_response.json()['id']

        # Anhang knapp über 5 MiB erzeugen
        oversized_content = b'x' * (5 * 1024 * 1024 + 1)
        import base64
        data_base64 = base64.b64encode(oversized_content).decode('ascii')

        response = self._json(
            'post',
            f'/api/v1/defects/{defect_id}/attachments/',
            {
                'filename': 'synthetic.png',
                'content_type': 'image/png',
                'data_base64': data_base64
            }
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn('5 MiB', response.content.decode())
