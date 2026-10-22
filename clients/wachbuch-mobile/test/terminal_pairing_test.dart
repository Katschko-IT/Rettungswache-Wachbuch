import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/api/server_address.dart';
import 'package:wachbuch_mobile/api/server_trust.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/screens/server_setup_screen.dart';

import 'test_localization.dart';

const _fingerprint =
    'ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12';
const _link = 'wachbuch://connect?url=https%3A%2F%2F10.42.0.1'
    '&pin=sha256%2F$_fingerprint&pair=kopplungscode-1234567';

/// Antwortformen von core/api/views.py (pairing_exchange, api_status).
http.Client _server({int pairingStatus = 200}) => MockClient((request) async {
      if (request.url.path == '/api/v1/token/kopplung/') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        if (pairingStatus != 200 || body['code'] != 'kopplungscode-1234567') {
          return http.Response(
            jsonEncode({'ok': false, 'detail': 'Kopplungscode ist ungültig oder abgelaufen.'}),
            401,
          );
        }
        return http.Response(
          jsonEncode({
            'ok': true,
            'token': 'wb_paired',
            'expires_at': '2027-01-20T10:00:00+00:00',
          }),
          200,
        );
      }
      return http.Response(
        jsonEncode({'ok': true, 'service': 'wachbuch', 'api_version': 'v1'}),
        200,
      );
    });

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    ServerTrust.resetForTest();
  });

  group('parseServerLink', () {
    test('reads certificate fingerprint and pairing code', () {
      final link = parseServerLink(_link);
      expect(link.url, 'https://10.42.0.1');
      expect(link.certSha256, _fingerprint);
      expect(link.pairingCode, 'kopplungscode-1234567');
      expect(parseServerAddress(_link), 'https://10.42.0.1');
    });

    test('plain links carry neither', () {
      final link = parseServerLink('https://wache.example.org');
      expect(link.certSha256, isNull);
      expect(link.pairingCode, isNull);
    });

    test('rejects malformed fingerprints, codes and unknown keys', () {
      const base = 'wachbuch://connect?url=https%3A%2F%2F10.42.0.1';
      expect(() => parseServerLink('$base&pin=md5%2Fabc'), throwsArgumentError);
      expect(() => parseServerLink('$base&pin=sha256%2F1234'), throwsArgumentError);
      expect(() => parseServerLink('$base&pair=kurz'), throwsArgumentError);
      expect(() => parseServerLink('$base&next=evil'), throwsArgumentError);
      expect(
        () => parseServerLink('$base&pair=kopplungscode-1234567&pair=kopplungscode-7654321'),
        throwsArgumentError,
      );
    });
  });

  group('ServerTrust', () {
    test('remembers fingerprints across loads', () async {
      await ServerTrust.remember('https://10.42.0.1', _fingerprint.toUpperCase());
      ServerTrust.resetForTest();
      await ServerTrust.load();
      expect(ServerTrust.pinFor('https://10.42.0.1'), _fingerprint);
      expect(ServerTrust.pinFor('https://andere.example.org'), isNull);
    });

    test('rejects invalid fingerprints', () async {
      expect(() => ServerTrust.remember('https://10.42.0.1', 'xyz'), throwsArgumentError);
    });

    test('matches only the exact certificate bytes', () {
      final der = utf8.encode('zertifikat');
      final pin = sha256.convert(der).toString();
      expect(ServerTrust.certificateMatches(der, pin), isTrue);
      expect(ServerTrust.certificateMatches(utf8.encode('anderes'), pin), isFalse);
    });
  });

  test('exchangePairingCode returns the app token', () async {
    final api = WachbuchApi(baseUrl: 'https://10.42.0.1', client: _server());
    final token = await api.exchangePairingCode('kopplungscode-1234567');
    expect(token.value, 'wb_paired');
    expect(token.expiresAt, isNotNull);
    expect(
      () => api.exchangePairingCode('falsch-falsch-falsch'),
      throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 401)),
    );
  });

  testWidgets('setup screen pairs in one step from a terminal QR', (tester) async {
    String? pairedUrl;
    AuthToken? pairedToken;
    var serverReady = false;
    await tester.pumpWidget(
      localizedApp(
        home: ServerSetupScreen(
          store: SessionStore(),
          apiFactory: (url) => WachbuchApi(baseUrl: url, client: _server()),
          onServerReady: (_) async => serverReady = true,
          onPaired: (url, token) async {
            pairedUrl = url;
            pairedToken = token;
          },
        ),
      ),
    );
    await tester.enterText(find.byType(TextFormField), _link);
    await tester.tap(find.widgetWithText(FilledButton, 'Bestätigen'));
    await tester.pumpAndSettle();

    expect(pairedUrl, 'https://10.42.0.1');
    expect(pairedToken?.value, 'wb_paired');
    expect(serverReady, isFalse);
    expect(ServerTrust.pinFor('https://10.42.0.1'), _fingerprint);
  });
}
