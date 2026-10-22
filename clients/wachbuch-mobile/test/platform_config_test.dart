import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Android registers isolated Wachbuch connect URI schemes', () async {
    final manifest = await File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsString();
    final gradle = await File('android/app/build.gradle.kts').readAsString();
    final lint = await File('android/app/lint.xml').readAsString();

    expect(manifest, contains('android.intent.action.VIEW'));
    expect(manifest, contains('android.intent.category.BROWSABLE'));
    expect(manifest, contains('android:scheme="\${appScheme}"'));
    expect(manifest, contains('android:host="connect"'));
    expect(manifest, contains('android.permission.ACCESS_COARSE_LOCATION'));
    expect(manifest, contains('android.permission.CAMERA'));
    expect(manifest, isNot(contains('android.permission.POST_NOTIFICATIONS')));
    expect(manifest, isNot(contains('android.permission.RECORD_AUDIO')));
    expect(manifest, isNot(contains('android.permission.ACCESS_FINE_LOCATION')));
    expect(manifest, isNot(contains('android.permission.ACCESS_BACKGROUND_LOCATION')));
    expect(manifest, contains('android:allowBackup="false"'));
    expect(manifest, contains('android:usesCleartextTraffic="false"'));
    expect(
      manifest,
      contains('android:dataExtractionRules="@xml/data_extraction_rules"'),
    );

    expect(gradle, contains('applicationId = "de.wachbuch.mobile"'));
    expect(
      gradle,
      contains('manifestPlaceholders["appScheme"] = "wachbuch"'),
    );
    expect(
      gradle,
      contains('manifestPlaceholders["appScheme"] = "wachbuch-internal"'),
    );
    expect(gradle, contains('applicationIdSuffix = ".internal"'));
    expect(
      gradle,
      contains('manifestPlaceholders["appLabel"] = "Wachbuch Internal"'),
    );
    expect(gradle, contains('warningsAsErrors = true'));
    expect(gradle, contains('REQUIRE_RELEASE_SIGNING'));

    expect(lint, contains('NotificationPermission'));
    expect(
      lint,
      contains(
        r'com\.baseflow\.geolocator\.location\.BackgroundNotification',
      ),
    );
  });

  test('iOS registers production identity and privacy usage descriptions', () async {
    final plist = await File('ios/Runner/Info.plist').readAsString();
    final project = await File(
      'ios/Runner.xcodeproj/project.pbxproj',
    ).readAsString();

    expect(plist, contains('<key>CFBundleURLTypes</key>'));
    expect(plist, contains('<string>wachbuch</string>'));
    expect(plist, contains('<key>NSCameraUsageDescription</key>'));
    expect(plist, contains('Mängelfotos'));
    expect(plist, contains('<key>NSPhotoLibraryUsageDescription</key>'));
    expect(plist, contains('<key>NSLocationWhenInUseUsageDescription</key>'));
    expect(plist, contains('Sonnenaufgang und Sonnenuntergang'));
    expect(plist, contains('<key>ITSAppUsesNonExemptEncryption</key>'));
    expect(
      project,
      contains('PRODUCT_BUNDLE_IDENTIFIER = de.wachbuch.wachbuchMobile;'),
    );
  });

  test('store release 1.0 version and policy files stay aligned', () async {
    final pubspec = await File('pubspec.yaml').readAsString();
    final androidRelease = await File(
      '.github/workflows/android-release.yml',
    ).readAsString();
    final testflight = await File(
      '.github/workflows/testflight.yml',
    ).readAsString();
    final iosCi = await File('.github/workflows/ios.yml').readAsString();

    expect(pubspec, contains('version: 1.0.0+12'));
    expect(pubspec, contains('sdk: ^3.12.0'));
    expect(androidRelease, contains('default: 1.0.0'));
    expect(androidRelease, contains('default: "12"'));
    expect(androidRelease, contains('target_sdk'));
    expect(androidRelease, contains('-ge 36'));
    expect(androidRelease, contains('Store releases must be built from main'));
    expect(androidRelease, contains('git diff --exit-code -- pubspec.lock'));

    expect(testflight, contains('default: 1.0.0'));
    expect(testflight, contains('default: "12"'));
    expect(testflight, contains('Xcode 26 or later'));
    expect(testflight, contains('iOS 26 SDK or later'));
    expect(testflight, contains('xcrun altool --validate-app'));
    expect(testflight, contains('-workspace ios/Runner.xcworkspace'));
    expect(testflight, contains('git diff --exit-code -- pubspec.lock'));
    expect(testflight, contains('de.wachbuch.wachbuchMobile'));
    expect(iosCi, contains('Xcode 26 or later'));

    for (final path in [
      'docs/PRIVACY-POLICY.md',
      'docs/SUPPORT.md',
      'docs/STORE-METADATA.md',
      'docs/STORE-RELEASE-1.0.md',
      'docs/SECURE-STORAGE-MIGRATION-1.0.md',
    ]) {
      expect(await File(path).exists(), isTrue, reason: '$path must exist');
    }
  });
}
