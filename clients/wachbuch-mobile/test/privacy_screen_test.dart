import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/screens/privacy_screen.dart';

import 'test_localization.dart';

void main() {
  testWidgets('privacy policy renders German store copy and public link', (
    tester,
  ) async {
    await tester.pumpWidget(localizedApp(home: const PrivacyScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Datenschutz'), findsOneWidget);
    expect(find.textContaining('keine zentrale Wachbuch-Cloud'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.byKey(const Key('open-privacy-policy')),
      300,
    );
    expect(find.byKey(const Key('open-privacy-policy')), findsOneWidget);
    expect(find.textContaining('PRIVACY-POLICY.md'), findsOneWidget);
  });

  testWidgets('privacy policy renders English store copy and public link', (
    tester,
  ) async {
    await tester.pumpWidget(
      localizedApp(
        locale: const Locale('en'),
        home: const PrivacyScreen(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Privacy'), findsOneWidget);
    expect(find.textContaining('open-source client'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.byKey(const Key('open-privacy-policy')),
      300,
    );
    expect(find.byKey(const Key('open-privacy-policy')), findsOneWidget);
    expect(find.text('Open privacy policy'), findsOneWidget);
  });
}
