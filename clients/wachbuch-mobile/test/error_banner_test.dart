import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/theme/app_theme.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';

import 'test_localization.dart';

void main() {
  testWidgets('error banner is readable and announced as a live region', (
    tester,
  ) async {
    await tester.pumpWidget(
      localizedApp(
        theme: buildWachbuchTheme(Brightness.light),
        home: const Scaffold(
          body: ErrorBanner(message: 'Verbindung fehlgeschlagen'),
        ),
      ),
    );

    expect(find.text('Verbindung fehlgeschlagen'), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    final semantics = tester.getSemantics(find.byType(ErrorBanner));
    expect(semantics.flagsCollection.isLiveRegion, isTrue);
    await expectLater(tester, meetsGuideline(textContrastGuideline));
  });
}
