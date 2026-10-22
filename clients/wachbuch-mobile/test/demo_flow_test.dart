import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/main.dart';
import 'package:wachbuch_mobile/screens/server_setup_screen.dart';

class _MemorySessionStore extends SessionStore {
  String? url;
  String? token;

  @override
  Future<String?> readServerUrl() async => url;

  @override
  Future<String?> readToken() async => token;

  @override
  Future<DateTime?> readTokenExpiresAt() async => null;

  @override
  Future<void> writeServerUrl(String value) async => url = value;

  @override
  Future<void> writeToken(String value, {DateTime? expiresAt}) async {
    token = value;
  }

  @override
  Future<void> clearToken() async => token = null;

  @override
  Future<void> clearAll() async {
    url = null;
    token = null;
  }

  @override
  Future<bool> isTokenExpired({DateTime? now}) async => false;
}

void main() {
  testWidgets('demo picker opens Feuerwehr profile without server login', (
    tester,
  ) async {
    final store = _MemorySessionStore();
    await tester.pumpWidget(WachbuchApp(store: store));
    await tester.binding.setLocale('de', '');
    await tester.pumpAndSettle();

    expect(find.byType(ServerSetupScreen), findsOneWidget);
    await tester.tap(find.text('Demo-Modus ausprobieren'));
    await tester.pumpAndSettle();

    expect(find.text('Demo-Modus wählen'), findsOneWidget);
    await tester.tap(find.text('Feuerwehr'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Demo-Modus'), findsWidgets);
    expect(find.textContaining('Feuerwehrwache'), findsWidgets);
    expect(store.url, DemoService.feuerwehr.serverUrl);
    expect(store.token, isNotNull);
  });
}
