"""Parent-owned acceptance tests. Run unchanged before and after remediation."""
from io import BytesIO
from email.message import Message
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import json,base64
from urllib.response import addinfourl
from django.test import TestCase,SimpleTestCase,Client,override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from core.traffic import _guarded_request,_guarded_request_nina,TrafficUnavailable
from core.feed_sync import safe_item_url
from core.waste_sync import parse_ics
from core import test_wachalltag_api as existing_api_tests
from core.models import UserCryptoIdentity

class TrafficAcceptance(SimpleTestCase):
    def test_redirects_never_reach_second_transport(self):
        for is_nina in [False,True]:
            with self.subTest(nina=is_nina):
                seen=[]
                def https_open(handler,request):
                    seen.append(request.full_url)
                    h=Message();h['Location']='http://127.0.0.1:54321/synthetic-only'
                    r=addinfourl(BytesIO(b''),h,request.full_url,302);r.msg='Synthetic'
                    return r
                def http_open(handler,request):
                    seen.append(request.full_url)
                    r=addinfourl(BytesIO(b'SYNTHETIC_ONLY'),Message(),request.full_url,200);r.msg='Synthetic'
                    return r
                with patch('urllib.request.HTTPSHandler.https_open',new=https_open),patch('urllib.request.HTTPHandler.http_open',new=http_open):
                    with self.assertRaises(TrafficUnavailable):
                        if is_nina:_guarded_request_nina()
                        else:_guarded_request('https://verkehr.autobahn.de/synthetic-only',accept='text/plain')
                self.assertEqual(len(seen),1,'Redirect target must not be requested at all')
    def test_ports_and_credentials_rejected_before_network(self):
        cases=[('https://verkehr.autobahn.de:8443/synthetic',False),('https://u:p@verkehr.autobahn.de/synthetic',False)]
        def forbidden(*a,**k):raise AssertionError('invalid URL reached transport')
        for url,nina in cases:
            with self.subTest(url=url),patch('urllib.request.HTTPSHandler.https_open',side_effect=forbidden):
                with self.assertRaises(TrafficUnavailable):
                    if nina:_guarded_request_nina(url)
                    else:_guarded_request(url,accept='text/plain')

class CryptoAcceptance(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='synthetic-crypto-acceptance',password='synthetic-only')
        self.client=Client(raise_request_exception=False);self.client.force_login(self.user)
    def test_bad_iterations_are_400_not_500(self):
        for value in ['not-an-integer',{'bad':1},[200000]]:
            with self.subTest(value=value):
                response=self.client.post(reverse('crypto_setup'),json.dumps({'kdf_iterations':value}),content_type='application/json')
                self.assertEqual(response.status_code,400)
        self.assertFalse(UserCryptoIdentity.objects.filter(user=self.user).exists())
    def test_json_list_is_400(self):
        response=self.client.post(reverse('crypto_setup'),json.dumps(['synthetic']),content_type='application/json')
        self.assertEqual(response.status_code,400)

class FeedAndCalendarAcceptance(SimpleTestCase):
    @override_settings(FEED_ALLOWED_HOSTS=['allowed.example'])
    def test_bad_item_url_is_dropped_valid_url_is_preserved(self):
        self.assertEqual(safe_item_url('https://allowed.example:abc/item'),'')
        self.assertEqual(safe_item_url('https://allowed.example:999999/item'),'')
        self.assertEqual(safe_item_url('https://[broken/item'),'')
        self.assertEqual(safe_item_url('https://allowed.example:443/item?q=1'),'https://allowed.example:443/item?q=1')
    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_tzid_and_utc_and_date_compatibility(self):
        def parse(line):return parse_ics('BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Synthetic\n'+line+'\nEND:VEVENT\nEND:VCALENDAR')[0][1]
        self.assertEqual(parse('DTSTART;TZID=America/New_York:20261020T090000').astimezone(ZoneInfo('UTC')),datetime(2026,10,20,13,tzinfo=ZoneInfo('UTC')))
        self.assertEqual(parse('DTSTART;TZID="America/New_York":20261020T090000').astimezone(ZoneInfo('UTC')),datetime(2026,10,20,13,tzinfo=ZoneInfo('UTC')))
        self.assertEqual(parse('DTSTART:20261020T090000Z').hour,9)
        self.assertEqual(parse('DTSTART;VALUE=DATE:20261020').date().isoformat(),'2026-10-20')
    def test_unknown_tzid_does_not_silently_become_local_time(self):
        with self.assertRaises(ValueError):parse_ics('BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Synthetic\nDTSTART;TZID=Not/A_Real_Zone:20261020T090000\nEND:VEVENT\nEND:VCALENDAR')

class UploadAcceptance(TestCase):
    setUp=existing_api_tests.WachalltagApiTests.setUp
    _json=existing_api_tests.WachalltagApiTests._json
    def test_size_message_matches_actual_5_mib_input_limit(self):
        created=self._json('post','/api/v1/defects/',{'title':'Synthetic size test','description':'test-only','priority':'normal'})
        self.assertEqual(created.status_code,201)
        response=self._json('post',f"/api/v1/defects/{created.json()['id']}/attachments/",{'filename':'synthetic.png','content_type':'image/png','data_base64':base64.b64encode(b'x'*(5*1024*1024+1)).decode()})
        self.assertEqual(response.status_code,413)
        self.assertIn('5 MiB',response.content.decode())
