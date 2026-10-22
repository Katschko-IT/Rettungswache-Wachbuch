import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/api/server_links.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/main.dart';
import 'package:wachbuch_mobile/screens/login_screen.dart';
import 'package:wachbuch_mobile/screens/server_setup_screen.dart';
import 'package:wachbuch_mobile/theme/solar_theme.dart';

import 'test_localization.dart';

class _MemorySessionStore extends SessionStore {
  _MemorySessionStore({this.url});

  String? url;
  String? token;
  DateTime? expiresAt;

  @override
  Future<String?> readServerUrl() async => url;

  @override
  Future<String?> readToken() async => token;

  @override
  Future<DateTime?> readTokenExpiresAt() async => expiresAt;

  @override
  Future<void> writeServerUrl(String value) async => url = value;

  @override
  Future<void> writeToken(String value, {DateTime? expiresAt}) async {
    token = value;
    this.expiresAt = expiresAt;
  }

  @override
  Future<void> clearToken() async {
    token = null;
    expiresAt = null;
  }

  @override
  Future<void> clearAll() async {
    url = null;
    token = null;
    expiresAt = null;
  }

  @override
  Future<bool> isTokenExpired({DateTime? now}) async {
    final expiry = expiresAt;
    if (expiry == null) return false;
    return !expiry.isAfter(now ?? DateTime.now());
  }
}

class _ClosableApi extends WachbuchApi {
  _ClosableApi() : super(baseUrl: 'https://wache.example.org');

  bool closed = false;

  @override
  Future<Map<String, dynamic>> discover() async => {
    'ok': true,
    'api_version': 'v1',
    'endpoints': {'token': '/api/v1/token/'},
  };

  @override
  Future<AuthToken> obtainToken({
    required String username,
    required String password,
    String label = 'Mobile App',
  }) async => const AuthToken(value: 'wb_test');

  @override
  void close() {
    closed = true;
    super.close();
  }
}

class _FakeLinkSource implements ServerLinkSource {
  _FakeLinkSource({this.initialLink});

  final Uri? initialLink;
  final controller = StreamController<Uri>.broadcast();

  @override
  Future<Uri?> getInitialLink() async => initialLink;

  @override
  Stream<Uri> get uriLinkStream => controller.stream;
}

class _ThemeLocation implements SolarLocationProvider {
  @override
  Future<GeoPoint?> getLocation() async {
    return const GeoPoint(latitude: 52.1, longitude: 8.1);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets('fresh install opens server setup', (tester) async {
    await tester.pumpWidget(WachbuchApp(store: _MemorySessionStore()));
    await tester.binding.setLocale('de', '');
    await tester.pumpAndSettle();

    expect(find.byType(ServerSetupScreen), findsOneWidget);
    expect(find.text('Server-Adresse Ihrer Wache'), findsOneWidget);
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.theme?.useMaterial3, isTrue);
    expect(app.darkTheme?.useMaterial3, isTrue);
  });

  testWidgets('saved server without token opens login', (tester) async {
    await tester.pumpWidget(
      WachbuchApp(store: _MemorySessionStore(url: 'https://wache.example.org')),
    );
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.text('https://wache.example.org'), findsOneWidget);
  });

  testWidgets('login validates required credentials before network access', (
    tester,
  ) async {
    await tester.pumpWidget(
      localizedApp(
        home: LoginScreen(
          store: _MemorySessionStore(),
          serverUrl: 'https://wache.example.org',
          onLoggedIn: (_, _, {DateTime? expiresAt}) async {},
          onChangeServer: () async {},
        ),
      ),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Anmelden'));
    await tester.pump();

    expect(find.text('Benutzername erforderlich'), findsOneWidget);
    expect(find.text('Passwort erforderlich'), findsOneWidget);
  });

  testWidgets('server setup rejects unsupported URL schemes locally', (
    tester,
  ) async {
    await tester.pumpWidget(
      localizedApp(
        home: ServerSetupScreen(
          store: _MemorySessionStore(),
          onServerReady: (_) async {},
        ),
      ),
    );

    await tester.enterText(
      find.byType(TextFormField),
      'ftp://wache.example.org',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Bestätigen'));
    await tester.pump();

    expect(find.text('Ungültige Adresse'), findsOneWidget);
  });

  testWidgets('login closes its temporary API client', (tester) async {
    final api = _ClosableApi();
    var loggedIn = false;
    await tester.pumpWidget(
      localizedApp(
        home: LoginScreen(
          store: _MemorySessionStore(),
          serverUrl: 'https://wache.example.org',
          apiFactory: (_) => api,
          onLoggedIn: (_, _, {DateTime? expiresAt}) async => loggedIn = true,
          onChangeServer: () async {},
        ),
      ),
    );

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Benutzername'),
      'michael',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Passwort'),
      'secret',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Anmelden'));
    await tester.pumpAndSettle();

    expect(loggedIn, isTrue);
    expect(api.closed, isTrue);
  });

  testWidgets('server discovery closes its temporary API client', (
    tester,
  ) async {
    final api = _ClosableApi();
    String? selectedUrl;
    await tester.pumpWidget(
      localizedApp(
        home: ServerSetupScreen(
          store: _MemorySessionStore(),
          apiFactory: (_) => api,
          onServerReady: (url) async => selectedUrl = url,
        ),
      ),
    );

    await tester.enterText(
      find.byType(TextFormField),
      'https://wache.example.org',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Bestätigen'));
    await tester.pumpAndSettle();

    expect(selectedUrl, 'https://wache.example.org');
    expect(api.closed, isTrue);
  });

  testWidgets('initial Wachbuch link selects server and clears old token', (
    tester,
  ) async {
    final store = _MemorySessionStore(url: 'https://alt.example.org')
      ..token = 'wb_old';
    final links = _FakeLinkSource(
      initialLink: Uri.parse(
        'wachbuch://connect?url=https%3A%2F%2Fneu.example.org',
      ),
    );
    addTearDown(links.controller.close);

    await tester.pumpWidget(WachbuchApp(store: store, linkSource: links));
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.text('https://neu.example.org'), findsOneWidget);
    expect(store.url, 'https://neu.example.org');
    expect(store.token, isNull);
  });

  testWidgets('runtime Wachbuch link switches to the linked server', (
    tester,
  ) async {
    final store = _MemorySessionStore(url: 'https://alt.example.org');
    final links = _FakeLinkSource();
    addTearDown(links.controller.close);

    await tester.pumpWidget(WachbuchApp(store: store, linkSource: links));
    await tester.pumpAndSettle();
    expect(find.text('https://alt.example.org'), findsOneWidget);

    links.controller.add(
      Uri.parse('wachbuch://connect?url=https%3A%2F%2Fneu.example.org'),
    );
    await tester.pumpAndSettle();

    expect(find.text('https://neu.example.org'), findsOneWidget);
    expect(store.url, 'https://neu.example.org');
  });

  testWidgets('solar controller updates MaterialApp at day and night', (
    tester,
  ) async {
    var now = DateTime.utc(2026, 6, 21, 12);
    final controller = SolarThemeController(
      locationProvider: _ThemeLocation(),
      now: () => now,
      scheduleTransitions: false,
    );

    await tester.pumpWidget(
      WachbuchApp(store: _MemorySessionStore(), themeController: controller),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
      ThemeMode.light,
    );

    now = DateTime.utc(2026, 6, 21);
    await controller.refresh();
    await tester.pump();

    expect(
      tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
      ThemeMode.dark,
    );
  });

  testWidgets('MaterialApp wires high contrast emergency themes', (tester) async {
    await tester.pumpWidget(WachbuchApp(store: _MemorySessionStore()));
    await tester.pumpAndSettle();

    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.highContrastTheme?.colorScheme.primary, const Color(0xFF000000));
    expect(
      app.highContrastDarkTheme?.colorScheme.primary,
      const Color(0xFFFFFFFF),
    );
  });
}
