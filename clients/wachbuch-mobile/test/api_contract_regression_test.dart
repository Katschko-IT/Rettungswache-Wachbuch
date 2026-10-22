import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/api_cache.dart';
import 'package:wachbuch_mobile/api/client.dart';

class _MemoryCache implements ApiCache {
  final Map<String, Map<String, dynamic>> values = {};

  @override
  Future<void> clear() async => values.clear();

  @override
  Future<Map<String, dynamic>?> readJson(String key) async {
    final value = values[key];
    return value == null ? null : Map<String, dynamic>.from(value);
  }

  @override
  Future<void> writeJson(String key, Map<String, dynamic> value) async {
    values[key] = Map<String, dynamic>.from(value);
  }
}

void main() {
  test('canonical nested server error preserves code message and correlation id', () async {
    final client = MockClient((request) async {
      return http.Response(
        jsonEncode({
          'ok': false,
          'error': {
            'code': 'mfa_required',
            'message': 'App-Token erforderlich.',
            'correlation_id': 'corr-123',
          },
        }),
        403,
        headers: {'content-type': 'application/json'},
      );
    });
    final api = WachbuchApi(baseUrl: 'https://wache.example', client: client);

    try {
      await api.obtainToken(username: 'michael', password: 'secret');
      fail('ApiException expected');
    } on ApiException catch (error) {
      expect(error.statusCode, 403);
      expect(error.code, 'mfa_required');
      expect(error.message, 'App-Token erforderlich.');
      expect(error.correlationId, 'corr-123');
      expect(error.isMfaRequired, isTrue);
    }
  });

  test('legacy flat server error remains supported', () async {
    final client = MockClient((request) async {
      return http.Response(
        jsonEncode({'ok': false, 'error': 'Anmeldung fehlgeschlagen.'}),
        401,
        headers: {'content-type': 'application/json'},
      );
    });
    final api = WachbuchApi(baseUrl: 'https://wache.example', client: client);

    await expectLater(
      api.me(),
      throwsA(
        isA<ApiException>()
            .having((e) => e.statusCode, 'statusCode', 401)
            .having((e) => e.message, 'message', 'Anmeldung fehlgeschlagen.'),
      ),
    );
  });

  test('successful read is cached and used after network loss', () async {
    var online = true;
    final cache = _MemoryCache();
    final client = MockClient((request) async {
      if (!online) throw http.ClientException('offline', request.url);
      return http.Response(
        jsonEncode({
          'ok': true,
          'user': {'username': 'michael'},
          'membership': {
            'station': {
              'name': 'Wache Nord',
              'modules': {'defects': true},
            },
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final api = WachbuchApi(
      baseUrl: 'https://wache.example',
      token: 'wb_test',
      client: client,
      cache: cache,
      requestTimeout: const Duration(milliseconds: 100),
    );

    final first = await api.me();
    expect(first['user']['username'], 'michael');
    expect(cache.values['me'], isNotNull);

    online = false;
    final offline = await api.me();
    expect(offline['membership']['station']['name'], 'Wache Nord');
  });

  test('cache never hides authorization errors', () async {
    final cache = _MemoryCache();
    await cache.writeJson('me', {
      'ok': true,
      'user': {'username': 'cached'},
    });
    final client = MockClient((request) async => http.Response(
          jsonEncode({
            'ok': false,
            'error': {
              'code': 'auth_required',
              'message': 'Token widerrufen.',
              'correlation_id': 'corr-auth',
            },
          }),
          401,
          headers: {'content-type': 'application/json'},
        ));
    final api = WachbuchApi(
      baseUrl: 'https://wache.example',
      token: 'revoked',
      client: client,
      cache: cache,
    );

    await expectLater(
      api.me(),
      throwsA(
        isA<ApiException>()
            .having((e) => e.statusCode, 'statusCode', 401)
            .having((e) => e.code, 'code', 'auth_required'),
      ),
    );
  });
}
