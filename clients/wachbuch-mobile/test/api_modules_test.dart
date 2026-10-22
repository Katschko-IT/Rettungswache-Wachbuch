import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  const baseUrl = 'https://wache.example.org';

  group('WachbuchApi.kalender', () {
    test('GET /api/v1/kalender/ returns typed entries with token header', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/kalender/');
        expect(request.headers['Authorization'], 'Token wb_test123');
        return http.Response(
          jsonEncode({
            'results': [
              {
                'id': 1,
                'title': 'RTW-Dienst',
                'description': 'Frühschicht',
                'starts_at': '2026-08-03T06:00:00+00:00',
                'ends_at': '2026-08-03T14:00:00+00:00',
                'all_day': false,
              },
              {
                'id': 2,
                'title': 'Übung',
                'starts_at': '2026-08-05',
                'all_day': true,
              },
            ],
          }),
          200,
        );
      });

      final entries = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test123',
        client: client,
      ).kalender();

      expect(entries.length, 2);
      expect(entries.first.title, 'RTW-Dienst');
      expect(entries.first.startsAt, isNotNull);
      expect(entries.last.allDay, isTrue);
    });

    test('returns an empty list when the module is disabled (404)', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'error': 'Modul nicht aktiviert.'}),
          404,
        ),
      );

      await expectLater(
        WachbuchApi(baseUrl: baseUrl, token: 't', client: client).kalender(),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('WachbuchApi.kaffeekasse', () {
    test('GET /api/v1/kaffeekasse/ returns balance and ledger', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/kaffeekasse/');
        return http.Response(
          jsonEncode({
            'balance': '42.50',
            'currency': 'EUR',
            'payment_hint': 'PayPal: paypal.me/wache',
            'ledger': [
              {
                'id': 1,
                'amount': '-2.00',
                'description': 'Kaffee',
                'user': {'display_name': 'Michael'},
                'created_at': '2026-08-02T10:00:00+00:00',
              },
            ],
          }),
          200,
        );
      });

      final kasse = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test123',
        client: client,
      ).kaffeekasse();

      expect(kasse.paymentHint, 'PayPal: paypal.me/wache');
      expect(kasse.ledger.length, 1);
      expect(kasse.ledger.first.isNegative, isTrue);
      expect(kasse.isNegative, isFalse);
    });
  });

  group('WachbuchApi.checklisten', () {
    test('GET /api/v1/checklisten/ returns typed lists with items', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/checklisten/');
        return http.Response(
          jsonEncode({
            'results': [
              {
                'id': 1,
                'title': 'Tagescheckliste',
                'items': [
                  {'id': 1, 'label': 'RTW prüfen', 'checked': true},
                  {'id': 2, 'label': 'Material', 'checked': false},
                ],
              },
            ],
          }),
          200,
        );
      });

      final lists = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test123',
        client: client,
      ).checklisten();

      expect(lists.length, 1);
      expect(lists.first.title, 'Tagescheckliste');
      expect(lists.first.checkedCount, 1);
      expect(lists.first.allChecked, isFalse);
    });
  });

  group('WachbuchApi.checklisteAbschluss', () {
    test('POST /api/v1/checklisten/{id}/abschluss/ marks the list completed', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/checklisten/5/abschluss/');
        expect(request.headers['Authorization'], 'Token wb_test123');
        return http.Response(
          jsonEncode({
            'id': 5,
            'title': 'Abendcheckliste',
            'completed': true,
            'completed_at': '2026-08-02T20:00:00+00:00',
            'items': [
              {'id': 1, 'label': 'Tore', 'checked': true},
            ],
          }),
          200,
        );
      });

      final result = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test123',
        client: client,
      ).checklisteAbschluss(5);

      expect(result.id, 5);
      expect(result.completed, isTrue);
      expect(result.completedAt, isNotNull);
      expect(result.items.first.checked, isTrue);
    });

    test('reads the real server completion payload', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'ok': true,
            'id': 99,
            'checklist': 5,
            'completed_by': {'id': 1, 'display_name': 'Sandra'},
            'created_at': '2026-10-22T07:00:00+00:00',
            'interval': 'daily',
            'due_next': '2026-10-23T07:00:00+00:00',
            'overdue': false,
          }),
          201,
        );
      });

      final result = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test123',
        client: client,
      ).checklisteAbschluss(5);

      expect(result.id, 5);
      expect(result.completed, isTrue);
      expect(result.completedAt, DateTime.parse('2026-10-22T07:00:00+00:00').toLocal());
      expect(result.completedBy, 'Sandra');
      expect(result.interval, 'daily');
    });

    test('empty 204-style body still yields a completed checklist', () async {
      final client = MockClient(
        (_) async => http.Response('', 204),
      );

      final result = await WachbuchApi(
        baseUrl: baseUrl,
        token: 'wb_test123',
        client: client,
      ).checklisteAbschluss(8);

      expect(result.id, 8);
      expect(result.completed, isTrue);
    });
  });
}
