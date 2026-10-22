import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  const baseUrl = 'https://wache.example.org';

  WachbuchApi api(MockClient client) =>
      WachbuchApi(baseUrl: baseUrl, token: 'wb_test', client: client);

  group('WachbuchApi chat/messaging', () {
    test('GET identity returns bundle map', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/chat/identity/');
        expect(request.headers['Authorization'], 'Token wb_test');
        return http.Response(
          jsonEncode({'ok': true, 'configured': true, 'kdf_iterations': 600000}),
          200,
        );
      });
      final bundle = await api(client).chatIdentity();
      expect(bundle['configured'], true);
      expect(bundle['kdf_iterations'], 600000);
    });

    test('POST registerChatIdentity sends the bundle', () async {
      Map<String, dynamic>? sent;
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/chat/identity/');
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'ok': true}), 200);
      });
      await api(client).registerChatIdentity(
        publicJwk: const {'kty': 'EC', 'crv': 'P-256', 'x': 'X', 'y': 'Y'},
        wrappedPrivateJwk: 'iv.data',
        kdfSalt: 'salt',
        kdfIterations: 600000,
      );
      expect(sent!['wrapped_private_jwk'], 'iv.data');
      expect(sent!['kdf_iterations'], 600000);
    });

    test('GET member keys parses directory', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/chat/keys/');
        return http.Response(
          jsonEncode({
            'members': [
              {'user_id': 1, 'label': 'Alex', 'has_keys': true, 'public_jwk': {'x': 'a'}},
              {'user_id': 2, 'label': 'Mara', 'has_keys': false, 'public_jwk': null},
            ],
          }),
          200,
        );
      });
      final keys = await api(client).chatMemberKeys();
      expect(keys.length, 2);
      expect(keys.first.hasKeys, isTrue);
      expect(keys.last.publicJwk, isNull);
    });

    test('GET station chat parses ciphertext envelopes', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/chat/');
        return http.Response(
          jsonEncode({
            'results': [
              {
                'id': 5,
                'author_id': 1,
                'author_name': 'Alex',
                'is_own': true,
                'is_encrypted': true,
                'ciphertext': 'CT',
                'nonce': 'N',
                'wrap': {'epk': {}, 'wrapped_key': 'iv.d'},
              },
            ],
          }),
          200,
        );
      });
      final feed = await api(client).stationChat();
      expect(feed.single.isEncrypted, isTrue);
      expect(feed.single.readable, isTrue);
      expect(feed.single.toEnvelope()['ciphertext'], 'CT');
    });

    test('POST station chat sends the envelope payload', () async {
      Map<String, dynamic>? sent;
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/chat/');
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'ok': true, 'id': 9}), 201);
      });
      await api(client).sendStationChat(const {
        'ciphertext': 'CT',
        'nonce': 'N',
        'key_wraps': {'1': {'epk': {}, 'wrapped_key': 'iv.d'}},
      });
      expect(sent!['ciphertext'], 'CT');
      expect((sent!['key_wraps'] as Map).containsKey('1'), isTrue);
    });

    test('start private conversation returns id', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/chat/private/');
        expect(jsonDecode(request.body), {'peer_id': 2});
        return http.Response(jsonEncode({'ok': true, 'id': 3, 'peer_keys': []}), 201);
      });
      expect(await api(client).startPrivateConversation(2), 3);
    });

    test('private thread parses other + peer keys + messages', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/chat/private/3/');
        return http.Response(
          jsonEncode({
            'other': {'id': 2, 'name': 'Mara'},
            'peer_keys': [
              {'user_id': 1, 'label': 'Alex', 'has_keys': true, 'public_jwk': {'x': 'a'}},
            ],
            'results': [
              {'id': 1, 'author_id': 2, 'author_name': 'Mara', 'is_own': false,
               'is_encrypted': true, 'ciphertext': 'C', 'nonce': 'N',
               'wrap': {'epk': {}, 'wrapped_key': 'iv.d'}},
            ],
          }),
          200,
        );
      });
      final thread = await api(client).privateThread(3);
      expect(thread.otherName, 'Mara');
      expect(thread.peerKeys.single.userId, 1);
      expect(thread.messages.single.authorName, 'Mara');
    });

    test('send mail posts recipients with envelope', () async {
      Map<String, dynamic>? sent;
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/post/');
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'ok': true, 'id': 12}), 201);
      });
      final id = await api(client).sendMail(
        recipientIds: const [2, 3],
        payload: const {'ciphertext': 'C', 'nonce': 'N', 'key_wraps': {}},
      );
      expect(id, 12);
      expect(sent!['recipient_ids'], [2, 3]);
      expect(sent!['ciphertext'], 'C');
    });

    test('mail detail parses envelope and recipients', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/post/12/');
        return http.Response(
          jsonEncode({
            'envelope': {'id': 12, 'is_encrypted': true, 'ciphertext': 'C', 'nonce': 'N',
                         'wrap': {'epk': {}, 'wrapped_key': 'iv.d'}, 'author_name': 'Alex'},
            'recipients': [
              {'id': 2, 'name': 'Mara', 'read': true},
            ],
          }),
          200,
        );
      });
      final detail = await api(client).mailDetail(12);
      expect(detail.envelope.isEncrypted, isTrue);
      expect(detail.recipients.single.read, isTrue);
    });

    test('module-disabled (404) surfaces a clear error', () async {
      final client = MockClient((_) async => http.Response(jsonEncode({'error': 'x'}), 404));
      await expectLater(
        api(client).stationChat(),
        throwsA(isA<ApiException>()),
      );
    });
  });
}
