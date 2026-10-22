import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/chat.dart';
import 'package:wachbuch_mobile/screens/chat_screen.dart';
import 'package:wachbuch_mobile/state/crypto_session.dart';

import 'test_localization.dart';

// Reference identity vector (same scheme as the web/server; see e2ee_test.dart).
const String _passphrase = 'geheime-passphrase-123';
const String _wrappedPrivateJwk =
    'Z_A6DPrOotSc9XoK.2knn7KOS4e3ru7xuNnFm9YozNFSAV9_Tbo_tVL6XbfXO5jtM4Ur24t0HTkLgkbRac_OGlq88jRL0ZyUt9vvGIWg7cldxfHMoBjEy_xMobtUkOZt1mt-DTyorZMXokcXeJxgCT3QmDHRCqnAciL2stgeDBBcsM4lsssSV50jxpqiKsMYroRVZp4fYYdtmJFp6Jo5AiP8WL7nTucS0rMfd6UivGwCwcvrIi5jhYUemS7cdTfZEyek5SdOzned1NOHibY76-fchIcac';
const String _kdfSalt = 'XNHX0iGeLdemhxsc1uG_jw';

class _FakeChatApi extends WachbuchApi {
  _FakeChatApi() : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  int sendCount = 0;

  @override
  Future<Map<String, dynamic>> chatIdentity() async => {
        'ok': true,
        'configured': true,
        'wrapped_private_jwk': _wrappedPrivateJwk,
        'kdf_salt': _kdfSalt,
        'kdf_iterations': 600000,
      };

  @override
  Future<List<ChatMemberKey>> chatMemberKeys() async => const [
        ChatMemberKey(
          userId: 1,
          label: 'Ich',
          hasKeys: true,
          publicJwk: {
            'kty': 'EC',
            'crv': 'P-256',
            'x': 'AZQtv9vAQ-cNiNrOIXNMnoltPWutBNOBKBaT-vVGU1M',
            'y': 'X-eE4z_DhcDRcTARZ7-_DM0KtrG4dnc3M9lFEJAJFa0',
          },
        ),
      ];

  @override
  Future<List<ChatFeedItem>> stationChat() async => [
        const ChatFeedItem(
          id: 1,
          authorId: 2,
          authorName: 'Alex',
          isOwn: false,
          isEncrypted: false,
          legacyBody: 'Hallo Team',
        ),
      ];

  @override
  Future<void> sendStationChat(Map<String, dynamic> payload) async {
    sendCount++;
  }
}

void main() {
  testWidgets('unlocks with passphrase, shows messages and sends', (tester) async {
    final api = _FakeChatApi();
    await tester.pumpWidget(
      localizedApp(home: ChatScreen(api: api, session: CryptoSession())),
    );
    await tester.pumpAndSettle();

    // Locked state prompts for the passphrase.
    expect(find.text('Chat entsperren'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, _passphrase);
    await tester.tap(find.text('Entsperren'));
    await tester.pumpAndSettle();

    // Feed becomes visible after unlocking.
    expect(find.text('Hallo Team'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, 'Neue Nachricht');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(api.sendCount, 1);
  });

  testWidgets('wrong passphrase shows an error', (tester) async {
    final api = _FakeChatApi();
    await tester.pumpWidget(
      localizedApp(home: ChatScreen(api: api, session: CryptoSession())),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField).first, 'falsch');
    await tester.tap(find.text('Entsperren'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Falsche Passphrase'), findsOneWidget);
  });
}
