import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/api_cache.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('session namespaces isolate equal cache keys', () async {
    const storage = FlutterSecureStorage();
    final first = SecureApiCache.forSession(
      baseUrl: 'https://wache-a.example.org',
      token: 'wb_a',
      storage: storage,
    );
    final second = SecureApiCache.forSession(
      baseUrl: 'https://wache-b.example.org',
      token: 'wb_b',
      storage: storage,
    );

    await first.writeJson('me', {'station': 'A'});
    await second.writeJson('me', {'station': 'B'});

    expect((await first.readJson('me'))?['station'], 'A');
    expect((await second.readJson('me'))?['station'], 'B');
  });

  test('clear removes persisted namespace keys even in a fresh instance', () async {
    const storage = FlutterSecureStorage();
    final writer = SecureApiCache.forSession(
      baseUrl: 'https://wache.example.org',
      token: 'wb_same_token',
      storage: storage,
    );
    await writer.writeJson('me', {'station': 'Wache'});
    await writer.writeJson('defects', {'results': [1, 2]});

    // Simulate an app restart: the new cache instance has no in-memory key set.
    final afterRestart = SecureApiCache.forSession(
      baseUrl: 'https://wache.example.org',
      token: 'wb_same_token',
      storage: storage,
    );
    expect(await afterRestart.readJson('me'), isNotNull);

    await afterRestart.clear();

    expect(await afterRestart.readJson('me'), isNull);
    expect(await afterRestart.readJson('defects'), isNull);
  });

  test('clearing one session does not delete another session cache', () async {
    const storage = FlutterSecureStorage();
    final first = SecureApiCache.forSession(
      baseUrl: 'https://wache.example.org',
      token: 'wb_first',
      storage: storage,
    );
    final second = SecureApiCache.forSession(
      baseUrl: 'https://wache.example.org',
      token: 'wb_second',
      storage: storage,
    );
    await first.writeJson('me', {'session': 'first'});
    await second.writeJson('me', {'session': 'second'});

    await first.clear();

    expect(await first.readJson('me'), isNull);
    expect((await second.readJson('me'))?['session'], 'second');
  });
}
