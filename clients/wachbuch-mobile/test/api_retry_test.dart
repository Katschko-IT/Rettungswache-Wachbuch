import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  group('WachbuchApi retry', () {
    test('retries on TimeoutException until success', () async {
      var calls = 0;
      Future<http.Response> handler(http.Request _) async {
        calls++;
        if (calls < 2) {
          await Future<void>.delayed(const Duration(milliseconds: 50));
        }
        return http.Response(
          jsonEncode({
            'ok': true,
            'api_version': 'v1',
            'endpoints': {'token': '/api/v1/token/'},
          }),
          200,
        );
      }

      // Per-request timeout is shorter than the mock delay so the first
      // attempt throws TimeoutException; the second attempt succeeds.
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: MockClient(handler),
        requestTimeout: const Duration(milliseconds: 5),
      );

      final result = await api.discover();

      expect(result['api_version'], 'v1');
      expect(calls, 2);
    });

    test('rethrows ApiException(0) after maxAttempts', () async {
      var calls = 0;
      Future<http.Response> handler(http.Request _) async {
        calls++;
        await Future<void>.delayed(const Duration(milliseconds: 50));
        return http.Response('{}', 200);
      }

      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: MockClient(handler),
        requestTimeout: const Duration(milliseconds: 5),
      );

      await expectLater(
        api.discover(),
        throwsA(
          isA<ApiException>().having(
            (error) => error.statusCode,
            'statusCode',
            0,
          ),
        ),
      );
      expect(calls, 3);
    });

    test('does not retry when first attempt succeeds', () async {
      var calls = 0;
      Future<http.Response> handler(http.Request _) async {
        calls++;
        return http.Response(
          jsonEncode({
            'ok': true,
            'api_version': 'v1',
            'endpoints': {'token': '/api/v1/token/'},
          }),
          200,
        );
      }

      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: MockClient(handler),
      );

      await api.discover();
      expect(calls, 1);
    });

    test('does not retry on 4xx ApiException', () async {
      var calls = 0;
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: MockClient((_) async {
          calls++;
          return http.Response(
            jsonEncode({'error': 'Ungültige Anmeldung.'}),
            401,
          );
        }),
      );

      await expectLater(
        api.me(),
        throwsA(
          isA<ApiException>().having(
            (error) => error.statusCode,
            'statusCode',
            401,
          ),
        ),
      );
      expect(calls, 1);
    });
  });
}
