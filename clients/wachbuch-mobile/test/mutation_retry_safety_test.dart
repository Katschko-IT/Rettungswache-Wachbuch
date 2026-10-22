import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  group('mutation retry safety', () {
    http.Response serverError() => http.Response(
          jsonEncode({
            'ok': false,
            'error': {
              'code': 'server_error',
              'message': 'temporary failure',
              'correlation_id': 'retry-test',
            },
          }),
          500,
          headers: {'content-type': 'application/json'},
        );

    test('token exchange is never automatically replayed', () async {
      var calls = 0;
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        client: MockClient((_) async {
          calls++;
          return serverError();
        }),
      );

      await expectLater(
        api.obtainToken(username: 'user', password: 'secret'),
        throwsA(isA<ApiException>()),
      );
      expect(calls, 1);
    });

    test('defect creation is never automatically replayed', () async {
      var calls = 0;
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'token',
        client: MockClient((request) async {
          calls++;
          expect(request.method, 'POST');
          expect(request.url.path, '/api/v1/defects/');
          return serverError();
        }),
      );

      await expectLater(
        api.createDefect(title: 'Defi prüfen'),
        throwsA(isA<ApiException>()),
      );
      expect(calls, 1);
    });

    test('photo upload is never automatically replayed', () async {
      var calls = 0;
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'token',
        client: MockClient((request) async {
          calls++;
          expect(request.method, 'POST');
          expect(request.url.path, '/api/v1/defects/7/attachments/');
          return serverError();
        }),
      );

      await expectLater(
        api.uploadDefectAttachment(
          7,
          filename: 'foto.jpg',
          contentType: 'image/jpeg',
          bytes: Uint8List.fromList([0xff, 0xd8, 0xff, 0x00]),
        ),
        throwsA(isA<ApiException>()),
      );
      expect(calls, 1);
    });

    test('token revoke is never automatically replayed', () async {
      var calls = 0;
      final api = WachbuchApi(
        baseUrl: 'https://wache.example.org',
        token: 'token',
        client: MockClient((_) async {
          calls++;
          return serverError();
        }),
      );

      await expectLater(api.revokeCurrentToken(), throwsA(isA<ApiException>()));
      expect(calls, 1);
    });

    test('MFA setup required is handled as an MFA requirement', () {
      final error = ApiException(
        403,
        'Zwei-Faktor-Anmeldung muss zuerst eingerichtet werden.',
        code: 'mfa_setup_required',
      );
      expect(error.isMfaRequired, isTrue);
    });
  });
}
