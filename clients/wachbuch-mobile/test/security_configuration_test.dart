import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('secure storage migration is explicitly crash-safe and staged at v10', () async {
    final pubspec = await File('pubspec.yaml').readAsString();
    final storage = await File(
      'lib/security/secure_storage.dart',
    ).readAsString();
    final manifest = await File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsString();
    final migrationDoc = await File(
      'docs/SECURE-STORAGE-MIGRATION-1.0.md',
    ).readAsString();

    expect(pubspec, contains('flutter_secure_storage: ^10.3.1'));
    expect(pubspec, isNot(contains('flutter_secure_storage: ^11')));
    expect(storage, contains('migrateOnAlgorithmChange: true'));
    expect(storage, contains('migrateWithBackup: true'));
    expect(manifest, contains('android:allowBackup="false"'));
    expect(migrationDoc, contains('9.2.4'));
    expect(migrationDoc, contains('10.3.1'));
    expect(migrationDoc, contains('1.0.0+12'));
  });

  test('all production secure storage entry points use the canonical factory', () async {
    final sessionStore = await File('lib/auth/session_store.dart').readAsString();
    final apiCache = await File('lib/api/api_cache.dart').readAsString();

    expect(sessionStore, contains('createWachbuchSecureStorage()'));
    expect(apiCache, contains('createWachbuchSecureStorage()'));
    expect(sessionStore, isNot(contains('?? const FlutterSecureStorage()')));
    expect(apiCache, isNot(contains('?? const FlutterSecureStorage()')));
  });
}
