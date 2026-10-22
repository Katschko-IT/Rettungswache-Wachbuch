import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wachbuch_mobile/api/client.dart';

void main() {
  const baseUrl = 'https://wache.example.org';
  WachbuchApi api(MockClient c) => WachbuchApi(baseUrl: baseUrl, token: 'wb_test', client: c);

  group('WachbuchApi chat groups', () {
    test('GET groups parses summaries', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/chat/groups/');
        return http.Response(
          jsonEncode({
            'results': [
              {'id': 1, 'name': 'Frühschicht', 'member_count': 3,
               'updated_at': '2026-08-11T09:00:00Z'},
            ],
          }),
          200,
        );
      });
      final groups = await api(client).chatGroups();
      expect(groups.single.name, 'Frühschicht');
      expect(groups.single.memberCount, 3);
    });

    test('POST create group sends name and members', () async {
      Map<String, dynamic>? sent;
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/chat/groups/');
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'ok': true, 'id': 5}), 201);
      });
      final id = await api(client).createChatGroup(name: 'Team', memberIds: [2, 3]);
      expect(id, 5);
      expect(sent!['name'], 'Team');
      expect(sent!['member_ids'], [2, 3]);
    });

    test('GET group thread parses members and messages', () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/chat/groups/5/');
        return http.Response(
          jsonEncode({
            'id': 5,
            'name': 'Team',
            'is_manager': true,
            'members': [
              {'user_id': 1, 'label': 'Alex', 'has_keys': true, 'public_jwk': {'x': 'a'}},
            ],
            'results': [
              {'id': 1, 'author_id': 1, 'author_name': 'Alex', 'is_own': true,
               'is_encrypted': true, 'ciphertext': 'C', 'nonce': 'N',
               'wrap': {'epk': {}, 'wrapped_key': 'iv.d'}},
            ],
          }),
          200,
        );
      });
      final thread = await api(client).groupThread(5);
      expect(thread.name, 'Team');
      expect(thread.isManager, isTrue);
      expect(thread.members.single.userId, 1);
      expect(thread.messages.single.isOwn, isTrue);
    });

    test('POST send group message posts the envelope', () async {
      Map<String, dynamic>? sent;
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/chat/groups/5/');
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'ok': true, 'id': 2}), 201);
      });
      await api(client).sendGroupMessage(5, const {
        'ciphertext': 'C', 'nonce': 'N', 'key_wraps': {'1': {}},
      });
      expect(sent!['ciphertext'], 'C');
    });

    test('POST members add/remove returns updated members', () async {
      Map<String, dynamic>? sent;
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/chat/groups/5/members/');
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'ok': true,
            'members': [
              {'user_id': 1, 'label': 'Alex', 'has_keys': true, 'public_jwk': {'x': 'a'}},
              {'user_id': 2, 'label': 'Mara', 'has_keys': true, 'public_jwk': {'x': 'b'}},
            ],
          }),
          200,
        );
      });
      final members = await api(client).updateGroupMembers(5, add: [2], remove: []);
      expect(members.length, 2);
      expect(sent!['add'], [2]);
    });
  });
}
