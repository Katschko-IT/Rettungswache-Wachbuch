import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/services/update_service.dart';
import 'package:wachbuch_mobile/widgets/update_dialog.dart';

import 'test_localization.dart';

http.Client _updateClient({
  String latestVersion = '9.9.9',
  bool forceUpdate = false,
  String? downloadUrl = 'https://example.test/app.apk',
  void Function()? onRequest,
}) =>
    MockClient((req) async {
      onRequest?.call();
      return http.Response(
        jsonEncode({
          'ok': true,
          'has_update': true,
          'current_version': '1.0.0',
          'latest_version': latestVersion,
          'version_code': 99,
          'platform': 'android',
          'changelog': <dynamic>[],
          'download_url': downloadUrl,
          'force_update': forceUpdate,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });

UpdateInfo _forceInfo({String? downloadUrl}) => UpdateInfo(
      hasUpdate: true,
      currentVersion: '1.0.0',
      latestVersion: '9.9.9',
      platform: 'android',
      changelog: const [],
      downloadUrl: downloadUrl,
      forceUpdate: true,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: 'wachbuch',
      packageName: 'de.wachbuch.mobile',
      version: '1.0.0',
      buildNumber: '12',
      buildSignature: '',
    );
    SharedPreferences.setMockInitialValues({});
  });

  group('UpdateService.ignoreUpdate', () {
    test('honours an ignored version reported by the server', () async {
      SharedPreferences.setMockInitialValues({
        'last_update_check':
            DateTime.now().subtract(const Duration(hours: 30)).toIso8601String(),
        'ignored_update_version': '9.9.9',
      });
      final svc = UpdateService(baseUrl: 'https://s', client: _updateClient());
      // The server still offers the ignored version -> suppressed.
      expect(await svc.checkForUpdates(), isNull);
    });

    test('ignoreUpdate() then check suppresses the same version', () async {
      final svc = UpdateService(baseUrl: 'https://s', client: _updateClient());
      await svc.ignoreUpdate('9.9.9');
      // Force the rate-limit gate open so the network path runs.
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        'last_update_check',
        DateTime.now().subtract(const Duration(hours: 30)).toIso8601String(),
      );
      expect(await svc.checkForUpdates(), isNull);
    });

    test('does not suppress a different offered version', () async {
      SharedPreferences.setMockInitialValues({
        'last_update_check':
            DateTime.now().subtract(const Duration(hours: 30)).toIso8601String(),
        'ignored_update_version': '9.9.9',
      });
      final svc = UpdateService(
        baseUrl: 'https://s',
        client: _updateClient(latestVersion: '8.8.8'),
      );
      final info = await svc.checkForUpdates();
      expect(info, isNotNull);
      expect(info!.latestVersion, '8.8.8');
    });
  });

  group('UpdateService.rate limit', () {
    test('within 24h returns null and does not call the server', () async {
      SharedPreferences.setMockInitialValues({
        'last_update_check': DateTime.now().toIso8601String(),
      });
      var calls = 0;
      final svc = UpdateService(
        baseUrl: 'https://s',
        client: _updateClient(onRequest: () => calls++),
      );
      expect(await svc.checkForUpdates(), isNull);
      expect(calls, 0);
    });

    test('after 24h performs the check and returns the info', () async {
      SharedPreferences.setMockInitialValues({
        'last_update_check':
            DateTime.now().subtract(const Duration(hours: 25)).toIso8601String(),
      });
      final svc = UpdateService(baseUrl: 'https://s', client: _updateClient());
      final info = await svc.checkForUpdates();
      expect(info, isNotNull);
      expect(info!.latestVersion, '9.9.9');
      expect(info.hasUpdate, isTrue);
    });
  });

  group('UpdateService.openDownloadUrl', () {
    test('rejects empty and non-https URLs without a fallback', () async {
      final svc = UpdateService(baseUrl: 'https://s', client: _updateClient());
      expect(await svc.openDownloadUrl(_forceInfo(downloadUrl: null)), isFalse);
      expect(await svc.openDownloadUrl(_forceInfo(downloadUrl: '')), isFalse);
      expect(
        await svc.openDownloadUrl(_forceInfo(downloadUrl: 'http://x/app.apk')),
        isFalse,
      );
      expect(
        await svc.openDownloadUrl(
          _forceInfo(downloadUrl: 'javascript:alert(1)'),
        ),
        isFalse,
      );
    });
  });

  group('ForcedUpdateDialog', () {
    Future<void> pumpDialog(WidgetTester tester, UpdateInfo info) async {
      await tester.pumpWidget(localizedApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () => showDialog<void>(
                  context: context,
                  barrierDismissible: false,
                  builder: (_) => ForcedUpdateDialog(
                    updateInfo: info,
                    updateService: UpdateService(baseUrl: 'https://s'),
                  ),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
    }

    testWidgets('offers the update action for a valid https URL', (tester) async {
      await pumpDialog(tester, _forceInfo(downloadUrl: 'https://example.test/app.apk'));
      expect(find.text('Jetzt updaten'), findsOneWidget);
      expect(find.text('Schließen'), findsNothing);
    });

    testWidgets('missing download URL is not a dead end', (tester) async {
      await pumpDialog(tester, _forceInfo(downloadUrl: null));

      // No usable target: the user must still have an explicit way out.
      expect(find.text('Jetzt updaten'), findsNothing);
      expect(find.text('Schließen'), findsOneWidget);

      final popScope = tester.widget<PopScope>(find.descendant(
        of: find.byType(ForcedUpdateDialog),
        matching: find.byType(PopScope),
      ));
      expect(popScope.canPop, isTrue);
    });

    testWidgets('non-https download URL is not a dead end', (tester) async {
      await pumpDialog(tester, _forceInfo(downloadUrl: 'http://insecure.test/app.apk'));

      expect(find.text('Jetzt updaten'), findsNothing);
      expect(find.text('Schließen'), findsOneWidget);

      // Tapping the escape hatch dismisses the dialog.
      await tester.tap(find.text('Schließen'));
      await tester.pumpAndSettle();
      expect(find.byType(ForcedUpdateDialog), findsNothing);
    });
  });
}
