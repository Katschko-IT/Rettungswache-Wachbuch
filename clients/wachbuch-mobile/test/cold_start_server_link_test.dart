import 'dart:async';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/api/api_cache.dart';
import 'package:wachbuch_mobile/api/server_links.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/main.dart';

class _InitialLinkSource implements ServerLinkSource {
  _InitialLinkSource(this.initial);

  final Uri? initial;

  @override
  Future<Uri?> getInitialLink() async => initial;

  @override
  Stream<Uri> get uriLinkStream => const Stream<Uri>.empty();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets('different cold-start server link purges old token cache', (
    tester,
  ) async {
    const oldUrl = 'https://old-wache.example.org';
    const newUrl = 'https://new-wache.example.org';
    const token = 'wb_old_session_token';
    final store = SessionStore();
    await store.writeServerUrl(oldUrl);
    await store.writeToken(
      token,
      expiresAt: DateTime.now().add(const Duration(hours: 2)),
    );
    final oldCache = SecureApiCache.forSession(baseUrl: oldUrl, token: token);
    await oldCache.writeJson('me', {'station': 'Alt'});

    await tester.pumpWidget(
      WachbuchApp(
        store: store,
        linkSource: _InitialLinkSource(Uri.parse(newUrl)),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(await store.readServerUrl(), newUrl);
    expect(await store.readToken(), isNull);
    expect(await oldCache.readJson('me'), isNull);
  });

  testWidgets('same-server cold-start link preserves current credentials', (
    tester,
  ) async {
    final url = DemoService.rettungsdienst.serverUrl;
    const token = 'wb_existing_session_token';
    final store = SessionStore();
    await store.writeServerUrl(url);
    await store.writeToken(
      token,
      expiresAt: DateTime.now().add(const Duration(hours: 2)),
    );
    final cache = SecureApiCache.forSession(baseUrl: url, token: token);
    await cache.writeJson('me', {'station': 'Bestehend'});

    await tester.pumpWidget(
      WachbuchApp(
        store: store,
        linkSource: _InitialLinkSource(Uri.parse(url)),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(await store.readServerUrl(), url);
    expect(await store.readToken(), token);
    expect((await cache.readJson('me'))?['station'], 'Bestehend');
  });
}
