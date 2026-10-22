import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  group('WachbuchApi', () {
    test('discover uses the public API root without authorization', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.toString(), 'https://wache.example.org/api/v1/');
        expect(request.headers, isNot(contains('Authorization')));
        return http.Response(
          jsonEncode({
            'ok': true,
            'api_version': 'v1',
            'endpoints': {'token': '/api/v1/token/'},
          }),
          200,
        );
      });

      final result = await WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: client,
      ).discover();

      expect(result['api_version'], 'v1');
    });

    test('obtainToken sends credentials and returns the token', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/token/');
        expect(request.headers, isNot(contains('Authorization')));
        expect(jsonDecode(request.body), {
          'username': 'michael',
          'password': 'secret',
          'label': 'Testgerät',
        });
        return http.Response(
          jsonEncode({
            'token': 'wb_test123',
            'expires_at': '2026-12-01T12:00:00Z',
          }),
          200,
        );
      });

      final token =
          await WachbuchApi(
            baseUrl: 'https://wache.example.org',
            client: client,
          ).obtainToken(
            username: 'michael',
            password: 'secret',
            label: 'Testgerät',
          );

      expect(token.value, 'wb_test123');
      expect(token.expiresAt, isNotNull);
    });

    test('discover rejects non-Wachbuch JSON payloads', () async {
      final client = MockClient(
        (_) async => http.Response(jsonEncode({'hello': 'world'}), 200),
      );

      await expectLater(
        WachbuchApi(
          baseUrl: 'https://wache.example.org',
          client: client,
        ).discover(),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('Wachbuch-Server'),
          ),
        ),
      );
    });

    test('API errors expose structured MFA codes', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({
            'error': 'Zwei-Faktor erforderlich.',
            'code': 'mfa_required',
          }),
          403,
        ),
      );

      try {
        await WachbuchApi(
          baseUrl: 'https://wache.example.org',
          client: client,
        ).obtainToken(username: 'a', password: 'b');
        fail('expected ApiException');
      } on ApiException catch (error) {
        expect(error.isMfaRequired, isTrue);
        expect(error.code, 'mfa_required');
      }
    });

    test('authenticated requests send the Wachbuch token', () async {
      final client = MockClient((request) async {
        expect(request.headers['Authorization'], 'Token wb_test123');
        return http.Response(
          jsonEncode({
            'user': {'username': 'michael'},
          }),
          200,
        );
      });

      final me = await WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'wb_test123',
        client: client,
      ).me();

      expect((me['user'] as Map)['username'], 'michael');
    });

    test('JSON API errors preserve status and message', () async {
      final client = MockClient(
        (_) async =>
            http.Response(jsonEncode({'error': 'Ungültige Anmeldung.'}), 401),
      );

      await expectLater(
        WachbuchApi(
          baseUrl: 'https://wache.example.org',
          client: client,
        ).discover(),
        throwsA(
          isA<ApiException>()
              .having((error) => error.statusCode, 'statusCode', 401)
              .having(
                (error) => error.message,
                'message',
                'Ungültige Anmeldung.',
              ),
        ),
      );
    });

    test('HTML proxy errors become a readable API error', () async {
      final client = MockClient(
        (_) async => http.Response('<html>Bad Gateway</html>', 502),
      );

      await expectLater(
        WachbuchApi(
          baseUrl: 'https://wache.example.org',
          client: client,
        ).discover(),
        throwsA(
          isA<ApiException>()
              .having((error) => error.statusCode, 'statusCode', 502)
              .having(
                (error) => error.message,
                'message',
                contains('Serverfehler'),
              ),
        ),
      );
    });

    test('request timeout becomes a readable connection error', () async {
      final client = MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        return http.Response('{}', 200);
      });

      await expectLater(
        WachbuchApi(
          baseUrl: 'https://wache.example.org',
          client: client,
          requestTimeout: const Duration(milliseconds: 10),
        ).discover(),
        throwsA(
          isA<ApiException>()
              .having((error) => error.statusCode, 'statusCode', 0)
              .having(
                (error) => error.message,
                'message',
                contains('Zeitlimit'),
              ),
        ),
      );
    });

    test('invalid JSON in a successful response is rejected clearly', () async {
      final client = MockClient((_) async => http.Response('not-json', 200));

      await expectLater(
        WachbuchApi(
          baseUrl: 'https://wache.example.org',
          client: client,
        ).discover(),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('ungültige Antwort'),
          ),
        ),
      );
    });

    test('handoverDetail loads the existing detail endpoint', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/handovers/42/');
        expect(request.headers['Authorization'], 'Token wb_test123');
        return http.Response(
          jsonEncode({
            'id': 42,
            'title': 'RTW auffüllen',
            'details': 'Fach 3 kontrollieren.',
            'author': {'display_name': 'Michael'},
            'version': 2,
          }),
          200,
        );
      });

      final detail = await WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'wb_test123',
        client: client,
      ).handoverDetail(42);

      expect(detail['details'], 'Fach 3 kontrollieren.');
      expect((detail['author'] as Map)['display_name'], 'Michael');
    });

    test('revokeCurrentToken deletes the presented token', () async {
      final client = MockClient((request) async {
        expect(request.method, 'DELETE');
        expect(request.url.path, '/api/v1/token/');
        expect(request.headers['Authorization'], 'Token wb_test');
        return http.Response(jsonEncode({'ok': true, 'revoked': true}), 200);
      });

      await WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'wb_test',
        client: client,
      ).revokeCurrentToken();
    });

    test('revokeCurrentToken treats 401 as already revoked', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'ok': false,
            'error': {'code': 'auth_required', 'message': 'ungültig'},
          }),
          401,
        );
      });

      await WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'wb_old',
        client: client,
      ).revokeCurrentToken();
    });

    test('close releases the underlying HTTP client', () {
      final client = _TrackingClient();
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: client,
      );

      api.close();

      expect(client.closed, isTrue);
    });
  });
}

class _TrackingClient extends http.BaseClient {
  bool closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    return http.StreamedResponse(const Stream.empty(), 200);
  }

  @override
  void close() {
    closed = true;
    super.close();
  }
}
