import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  const baseUrl = 'https://wache.example.org';

  group('WachbuchApi pinboard', () {
    test('GET pinboard parses results with auth header', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/pinnwand/');
        expect(request.headers['Authorization'], 'Token wb_test');
        return http.Response(
          jsonEncode({
            'results': [
              {
                'id': 2,
                'title': 'Teamabend',
                'body': 'Freitag 19 Uhr',
                'category': 'event',
                'is_pinned': true,
                'author': {'display_name': 'Alex'},
                'updated_at': '2026-08-11T18:00:00Z',
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
      ).pinboard();

      expect(items.single.title, 'Teamabend');
      expect(items.single.isPinned, isTrue);
      expect(items.single.category, 'event');
      expect(items.single.authorName, 'Alex');
    });

    test('POST createPinboardNote sends body and parses response', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/pinnwand/');
        expect(jsonDecode(request.body), {
          'title': 'Kaffee alle',
          'body': 'Bitte nachbestellen',
          'category': 'info',
        });
        return http.Response(
          jsonEncode({
            'id': 5,
            'title': 'Kaffee alle',
            'body': 'Bitte nachbestellen',
            'category': 'info',
            'is_pinned': false,
          }),
          201,
        );
      });

      final note = await WachbuchApi(
        baseUrl: baseUrl,
        token: 't',
        client: client,
      ).createPinboardNote(title: 'Kaffee alle', body: 'Bitte nachbestellen');

      expect(note.id, 5);
      expect(note.title, 'Kaffee alle');
      expect(note.isPinned, isFalse);
    });

    test('missing pinboard module (404) surfaces a clear error', () async {
      final client = MockClient((_) async {
        return http.Response(jsonEncode({'error': 'missing'}), 404);
      });

      await expectLater(
        WachbuchApi(baseUrl: baseUrl, token: 't', client: client).pinboard(),
        throwsA(isA<ApiException>()),
      );
    });
  });
}
