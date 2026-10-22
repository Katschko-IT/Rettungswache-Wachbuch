import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  const baseUrl = 'https://wache.example.org';

  group('WachbuchApi defects/assets/inventory/acks', () {
    test('GET defects parses results with auth header', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/defects/');
        expect(request.headers['Authorization'], 'Token wb_test');
        return http.Response(
          jsonEncode({
            'results': [
              {
                'id': 1,
                'title': 'Defi',
                'status': 'open',
                'priority': 'urgent',
              },
            ],
          }),
          200,
        );
      });

      final items = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test',
        client: client,
      ).defects();

      expect(items.single.title, 'Defi');
      expect(items.single.isUrgent, isTrue);
    });

    test('POST defect status sends body', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/defects/9/status/');
        expect(jsonDecode(request.body), {'status': 'waiting'});
        return http.Response(
          jsonEncode({'id': 9, 'title': 'X', 'status': 'waiting'}),
          200,
        );
      });

      final updated = await WachbuchApi(
        baseUrl: baseUrl,
        token: 't',
        client: client,
      ).updateDefectStatus(9, 'waiting');

      expect(updated.status, 'waiting');
    });

    test('missing defects module (404) is non-retryable', () async {
      var calls = 0;
      final client = MockClient((_) async {
        calls++;
        return http.Response(jsonEncode({'error': 'missing'}), 404);
      });

      await expectLater(
        WachbuchApi(baseUrl: baseUrl, token: 't', client: client).defects(),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'status', 404),
        ),
      );
      expect(calls, 1);
      expect(WachbuchApi.isModuleUnavailable(ApiException(404, 'x')), isTrue);
    });

    test('HTTP 501 from server is not retried', () async {
      var calls = 0;
      final client = MockClient((_) async {
        calls++;
        return http.Response(jsonEncode({'error': 'not implemented'}), 501);
      });

      await expectLater(
        WachbuchApi(baseUrl: baseUrl, token: 't', client: client).assets(),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'status', 501),
        ),
      );
      expect(calls, 1);
    });

    test('GET assets and inventory', () async {
      final client = MockClient((request) async {
        if (request.url.path == '/api/v1/assets/') {
          return http.Response(
            jsonEncode({
              'results': [
                {'id': 'rtw-1', 'label': 'RTW 1', 'status': 'ready'},
              ],
            }),
            200,
          );
        }
        expect(request.url.path, '/api/v1/inventory/');
        return http.Response(
          jsonEncode({
            'results': [
              {'id': 'funk-a', 'label': 'Funk A', 'kind': 'device'},
            ],
          }),
          200,
        );
      });

      final api = WachbuchApi(baseUrl: baseUrl, token: 't', client: client);
      expect((await api.assets()).single.label, 'RTW 1');
      expect((await api.inventory()).single.id, 'funk-a');
    });

    test('inventory checkout and checkin paths', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        if (request.url.path.endsWith('/checkout/')) {
          return http.Response(
            jsonEncode({
              'id': 'funk-a',
              'label': 'Funk A',
              'holder': 'michael',
            }),
            200,
          );
        }
        expect(request.url.path, '/api/v1/inventory/funk-a/checkin/');
        return http.Response(
          jsonEncode({'id': 'funk-a', 'label': 'Funk A', 'holder': null}),
          200,
        );
      });

      final api = WachbuchApi(baseUrl: baseUrl, token: 't', client: client);
      final out = await api.inventoryCheckout('funk-a');
      expect(out.isOut, isTrue);
      final back = await api.inventoryCheckin('funk-a');
      expect(back.isOut, isFalse);
    });

    test('handover ack list and post', () async {
      final client = MockClient((request) async {
        if (request.method == 'GET') {
          expect(request.url.path, '/api/v1/handovers/3/acks/');
          return http.Response(
            jsonEncode({
              'results': [
                {
                  'handover_id': 3,
                  'by': 'alice',
                  'at': '2026-08-09T06:00:00Z',
                },
              ],
            }),
            200,
          );
        }
        expect(request.url.path, '/api/v1/handovers/3/ack/');
        return http.Response(
          jsonEncode({
            'handover_id': 3,
            'by': 'michael',
            'at': '2026-08-09T07:00:00Z',
          }),
          200,
        );
      });

      final api = WachbuchApi(baseUrl: baseUrl, token: 't', client: client);
      expect((await api.handoverAcks(3)).single.by, 'alice');
      expect((await api.acknowledgeHandover(3)).by, 'michael');
    });
  });
}
