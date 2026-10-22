import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/chat.dart';
import 'package:wachbuch_mobile/screens/groups_screen.dart';
import 'package:wachbuch_mobile/state/crypto_session.dart';

import 'test_localization.dart';

// Recipient identity from the interop vector (see e2ee_test.dart).
const Map<String, dynamic> _privateJwk = {
  'kty': 'EC',
  'crv': 'P-256',
  'x': 'AZQtv9vAQ-cNiNrOIXNMnoltPWutBNOBKBaT-vVGU1M',
  'y': 'X-eE4z_DhcDRcTARZ7-_DM0KtrG4dnc3M9lFEJAJFa0',
  'd': 'iDvAFh2kA0hYX7FJk7scKjwJkLatZBpd1u8Au-0t_pQ',
};
const Map<String, dynamic> _publicJwk = {
  'kty': 'EC',
  'crv': 'P-256',
  'x': 'AZQtv9vAQ-cNiNrOIXNMnoltPWutBNOBKBaT-vVGU1M',
  'y': 'X-eE4z_DhcDRcTARZ7-_DM0KtrG4dnc3M9lFEJAJFa0',
};

class _FakeGroupsApi extends WachbuchApi {
  _FakeGroupsApi() : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  int sendCount = 0;

  @override
  Future<List<ChatGroupSummary>> chatGroups() async => const [
        ChatGroupSummary(id: 5, name: 'Frühschicht', memberCount: 2),
      ];

  @override
  Future<GroupThreadData> groupThread(int id) async => GroupThreadData(
        id: id,
        name: 'Frühschicht',
        isManager: true,
        members: const [
          ChatMemberKey(userId: 1, label: 'Ich', hasKeys: true, publicJwk: _publicJwk),
        ],
        messages: const [
          ChatFeedItem(
            id: 1,
            authorId: 2,
            authorName: 'Alex',
            isOwn: false,
            isEncrypted: false,
            legacyBody: 'Moin Gruppe',
          ),
        ],
      );

  @override
  Future<void> sendGroupMessage(int id, Map<String, dynamic> payload) async {
    sendCount++;
  }
}

void main() {
  testWidgets('lists groups', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: GroupsScreen(api: _FakeGroupsApi(), session: CryptoSession())),
    );
    await tester.pumpAndSettle();
    expect(find.text('Frühschicht'), findsOneWidget);
  });

  testWidgets('opens a group thread and sends a message when unlocked', (tester) async {
    final api = _FakeGroupsApi();
    final session = CryptoSession()..unlockWith(Map<String, dynamic>.from(_privateJwk));
    await tester.pumpWidget(
      localizedApp(
        home: GroupThreadScreen(
          api: api,
          groupId: 5,
          title: 'Frühschicht',
          session: session,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Moin Gruppe'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, 'Antwort');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(api.sendCount, 1);
  });
}
