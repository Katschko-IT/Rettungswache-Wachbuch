import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/api/api_cache.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/api/server_address.dart';
import 'package:wachbuch_mobile/api/server_links.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/demo/demo_api.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/screens/home_shell.dart';
import 'package:wachbuch_mobile/screens/login_screen.dart';
import 'package:wachbuch_mobile/screens/server_setup_screen.dart';
import 'package:wachbuch_mobile/services/update_service.dart';
import 'package:wachbuch_mobile/theme/app_theme.dart';
import 'package:wachbuch_mobile/theme/solar_theme.dart';
import 'package:wachbuch_mobile/theme/high_contrast_theme.dart';
import 'package:wachbuch_mobile/widgets/update_dialog.dart';
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Initialize session store
  final store = SessionStore();
  
  // Initialize server links
  final links = AppLinksServerLinkSource();
  
  // Initialize theme controller
  final themeController = SolarThemeController.device();
  
  // Set preferred orientations
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);
  
  runApp(
    WachbuchApp(
      store: store,
      linkSource: links,
      themeController: themeController,
    ),
  );
}

enum _BootPhase { booting, setupServer, login, home }

class WachbuchApp extends StatefulWidget {
  const WachbuchApp({
    super.key,
    required this.store,
    this.linkSource = const NoopServerLinkSource(),
    this.themeController,
  });

  final SessionStore store;
  final ServerLinkSource linkSource;
  final SolarThemeController? themeController;

  @override
  State<WachbuchApp> createState() => _WachbuchAppState();
}

class _WachbuchAppState extends State<WachbuchApp> with WidgetsBindingObserver {
  final _navigatorKey = GlobalKey<NavigatorState>();
  _BootPhase _phase = _BootPhase.booting;
  String? _serverUrl;
  WachbuchApi? _api;
  StreamSubscription<Uri>? _linkSubscription;
  ThemeMode _themeMode = ThemeMode.system;
  String? _sessionNotice;

  @override
  void initState() {
    super.initState();
    final themeController = widget.themeController;
    if (themeController != null) {
      _themeMode = themeController.mode;
      themeController.addListener(_handleThemeChange);
      WidgetsBinding.instance.addObserver(this);
      unawaited(themeController.refresh());
    }
    _bootstrap();
  }

  void _handleThemeChange() {
    if (!mounted) return;
    setState(() {
      _themeMode = widget.themeController?.mode ?? ThemeMode.system;
    });
  }

  Future<void> _checkForUpdates() async {
    try {
      final updateService = UpdateService(baseUrl: _serverUrl ?? '');
      final updateInfo = await updateService.checkForUpdates();
      
      if (updateInfo != null && updateInfo.hasUpdate) {
        // If this is a forced update, show blocking dialog
        if (updateInfo.forceUpdate) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              showDialog(
                context: _navigatorKey.currentContext!,
                barrierDismissible: false,
                builder: (context) => ForcedUpdateDialog(
                  updateInfo: updateInfo,
                  updateService: updateService,
                ),
              );
            }
          });
        } else {
          // For non-forced updates, show dialog after app loads
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              showDialog(
                context: _navigatorKey.currentContext!,
                builder: (context) => UpdateDialog(
                  updateInfo: updateInfo,
                  updateService: updateService,
                ),
              );
            }
          });
        }
      }
    } catch (e) {
      debugPrint('Failed to check for updates: $e');
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      final controller = widget.themeController;
      if (controller != null) unawaited(controller.refresh());
    }
  }

  Future<void> _bootstrap() async {
    var url = await widget.store.readServerUrl();
    var token = await widget.store.readToken();

    if (url != null && url.isNotEmpty) {
      try {
        url = parseServerAddress(url, allowInsecure: kDebugMode);
        await widget.store.writeServerUrl(url);
      } on ArgumentError {
        await widget.store.clearAll();
        url = null;
        token = null;
      }
    }

    if (token != null && await widget.store.isTokenExpired()) {
      // Expired credentials must not retain their offline station snapshots.
      if (url != null && url.isNotEmpty) {
        await _clearCacheForSession(url, token);
      }
      await widget.store.clearToken();
      token = null;
      _sessionNotice = 'Ihre Anmeldung ist abgelaufen. Bitte erneut anmelden.';
    }

    final initialLink = await widget.linkSource.getInitialLink();
    if (initialLink != null) {
      final linkedUrl = _parseLink(initialLink);
      if (linkedUrl != null && linkedUrl != url) {
        // During bootstrap `_api` does not exist yet, so clear the persisted
        // session cache directly before replacing a previously stored server.
        if (url != null && url.isNotEmpty && token != null && token.isNotEmpty) {
          await _clearCacheForSession(url, token);
        }
        await widget.store.clearAll();
        await widget.store.writeServerUrl(linkedUrl);
        url = linkedUrl;
        token = null;
      }
      // A cold-start link to the already configured server is a no-op: it must
      // not revoke the current token or discard its offline snapshots.
    }

    if (!mounted) return;
    setState(() {
      _serverUrl = url;
      if (url != null && url.isNotEmpty && token != null && token.isNotEmpty) {
        _api = createWachbuchApi(url, token: token);
        _phase = _BootPhase.home;
      } else if (url != null &&
          url.isNotEmpty &&
          DemoService.isDemoUrl(url)) {
        // Resume demo without forcing a login form.
        final service = DemoService.fromServerUrl(url)!;
        _api = DemoWachbuchApi(profile: demoProfileFor(service));
        _phase = _BootPhase.home;
      } else if (url != null && url.isNotEmpty) {
        _phase = _BootPhase.login;
      } else {
        _phase = _BootPhase.setupServer;
      }
    });

    _linkSubscription = widget.linkSource.uriLinkStream.listen(
      _handleServerLink,
      onError: (_) {},
    );
    if (_serverUrl != null && _serverUrl!.isNotEmpty && !DemoService.isDemoUrl(_serverUrl!)) {
      _checkForUpdates();
    }
  }

  String? _parseLink(Uri link) {
    try {
      return parseServerAddress(link.toString(), allowInsecure: kDebugMode);
    } on ArgumentError {
      return null;
    }
  }

  Future<void> _clearCacheForSession(String baseUrl, String token) async {
    if (DemoService.isDemoUrl(baseUrl) || token.isEmpty) return;
    try {
      await SecureApiCache.forSession(baseUrl: baseUrl, token: token).clear();
    } catch (_) {
      // Logout/server changes must still complete if secure-storage cleanup
      // encounters an OS/keychain failure. The token is removed regardless.
    }
  }

  Future<void> _clearCurrentApiCache() async {
    final api = _api;
    final token = api?.token;
    if (api == null || token == null || token.isEmpty) return;
    await _clearCacheForSession(api.baseUrl, token);
  }

  Future<bool> _applyServerLink(
    String url, {
    required bool confirmIfNeeded,
  }) async {
    if (confirmIfNeeded) {
      final nav = _navigatorKey.currentContext;
      if (nav == null) return false;
      final confirmed = await showDialog<bool>(
        context: nav,
        builder: (context) => AlertDialog(
          title: const Text('Server wechseln?'),
          content: Text(
            'Ein Link möchte die App auf\n$url\numstellen. '
            'Die aktuelle Anmeldung wird dabei beendet.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Abbrechen'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Wechseln'),
            ),
          ],
        ),
      );
      if (confirmed != true) return false;
    }
    await _clearCurrentApiCache();
    await widget.store.clearAll();
    await widget.store.writeServerUrl(url);
    return true;
  }

  Future<void> _handleServerLink(Uri link) async {
    final url = _parseLink(link);
    if (url == null) return;
    if (_serverUrl == url && _phase == _BootPhase.home) {
      return;
    }
    final needsConfirm =
        _phase == _BootPhase.home &&
        _serverUrl != null &&
        _serverUrl != url;
    final applied = await _applyServerLink(
      url,
      confirmIfNeeded: needsConfirm,
    );
    if (!applied || !mounted) return;
    setState(() {
      _api = null;
      _serverUrl = url;
      _phase = _BootPhase.login;
      _sessionNotice = null;
    });
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    final themeController = widget.themeController;
    if (themeController != null) {
      WidgetsBinding.instance.removeObserver(this);
      themeController.removeListener(_handleThemeChange);
      themeController.dispose();
    }
    super.dispose();
  }

  Future<void> _onServerReady(String url) async {
    if (DemoService.isDemoUrl(url)) {
      final service = DemoService.fromServerUrl(url)!;
      await _onDemoReady(service);
      return;
    }
    await widget.store.writeServerUrl(url);
    if (!mounted) return;
    setState(() {
      _serverUrl = url;
      _phase = _BootPhase.login;
    });
  }

  Future<void> _onDemoReady(DemoService service) async {
    final profile = demoProfileFor(service);
    final token = '$demoTokenPrefix${service.id}';
    await widget.store.writeServerUrl(service.serverUrl);
    await widget.store.writeToken(
      token,
      expiresAt: DateTime.now().add(const Duration(days: 7)),
    );
    if (!mounted) return;
    setState(() {
      _serverUrl = service.serverUrl;
      _api = DemoWachbuchApi(profile: profile, token: token);
      _phase = _BootPhase.home;
      _sessionNotice = null;
    });
  }

  Future<void> _onLoggedIn(
    String url,
    String token, {
    DateTime? expiresAt,
  }) async {
    await widget.store.writeServerUrl(url);
    await widget.store.writeToken(token, expiresAt: expiresAt);
    if (!mounted) return;
    setState(() {
      _serverUrl = url;
      _api = createWachbuchApi(url, token: token);
      _phase = _BootPhase.home;
      _sessionNotice = null;
    });
  }

  Future<void> _revokeCurrentTokenBestEffort() async {
    final api = _api;
    if (api == null) return;
    try {
      await api.revokeCurrentToken();
    } catch (_) {
      // Local logout must succeed even if the server is unreachable.
    }
  }

  Future<void> _logout({String? notice}) async {
    await _revokeCurrentTokenBestEffort();
    await _clearCurrentApiCache();
    await widget.store.clearToken();
    if (!mounted) return;
    setState(() {
      _api = null;
      _sessionNotice = notice;
      _phase = _serverUrl == null || _serverUrl!.isEmpty
          ? _BootPhase.setupServer
          : _BootPhase.login;
    });
  }

  Future<void> _changeServer() async {
    await _revokeCurrentTokenBestEffort();
    await _clearCurrentApiCache();
    await widget.store.clearAll();
    if (!mounted) return;
    setState(() {
      _api = null;
      _serverUrl = null;
      _sessionNotice = null;
      _phase = _BootPhase.setupServer;
    });
  }

  @override
  Widget build(BuildContext context) {
    Widget home;
    switch (_phase) {
      case _BootPhase.booting:
        home = const Scaffold(body: Center(child: CircularProgressIndicator()));
      case _BootPhase.setupServer:
        home = ServerSetupScreen(
          store: widget.store,
          onServerReady: _onServerReady,
          onDemoReady: _onDemoReady,
        );
      case _BootPhase.login:
        home = LoginScreen(
          store: widget.store,
          serverUrl: _serverUrl!,
          notice: _sessionNotice,
          onLoggedIn: _onLoggedIn,
          onChangeServer: _changeServer,
        );
      case _BootPhase.home:
        home = HomeShell(
          api: _api!,
          onLogout: () => _logout(
            notice: 'Sitzung beendet. Bitte erneut anmelden.',
          ),
          onChangeServer: _changeServer,
        );
    }

    return MaterialApp(
      title: 'Wachbuch',
      navigatorKey: _navigatorKey,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildWachbuchTheme(Brightness.light),
      darkTheme: buildWachbuchTheme(Brightness.dark),
      highContrastTheme: HighContrastTheme.light(),
      highContrastDarkTheme: HighContrastTheme.dark(),
      themeMode: _themeMode,
      home: home,
    );
  }
}
