import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('stores server URL separately from secure API token', () async {
    const secure = FlutterSecureStorage();
    final store = SessionStore(secureStorage: secure);

    await store.writeServerUrl('https://wache.example.org');
    await store.writeToken('wb_secret');

    expect(await store.readServerUrl(), 'https://wache.example.org');
    expect(await store.readToken(), 'wb_secret');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('wachbuch_server_url'), 'https://wache.example.org');
    expect(prefs.getString('wachbuch_api_token'), isNull);
  });

  test('clearToken preserves the configured server', () async {
    final store = SessionStore();
    await store.writeServerUrl('https://wache.example.org');
    await store.writeToken('wb_secret');

    await store.clearToken();

    expect(await store.readToken(), isNull);
    expect(await store.readServerUrl(), 'https://wache.example.org');
  });

  test('clearAll removes server and token', () async {
    final store = SessionStore();
    await store.writeServerUrl('https://wache.example.org');
    await store.writeToken('wb_secret');

    await store.clearAll();

    expect(await store.readToken(), isNull);
    expect(await store.readServerUrl(), isNull);
  });

  test('token expiry is detected from stored timestamp', () async {
    final store = SessionStore();
    await store.writeToken(
      'wb_secret',
      expiresAt: DateTime.now().subtract(const Duration(minutes: 1)),
    );

    expect(await store.isTokenExpired(), isTrue);
    expect(await store.readTokenExpiresAt(), isNotNull);
  });
}
