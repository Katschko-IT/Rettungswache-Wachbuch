import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/theme/app_theme.dart';
import 'package:wachbuch_mobile/ui/demo_banner.dart';

void main() {
  testWidgets('DemoBanner is hidden when visible=false', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildWachbuchTheme(Brightness.light),
        home: const Scaffold(
          body: DemoBanner(visible: false, label: 'Demo-Modus'),
        ),
      ),
    );

    expect(find.textContaining('Demo-Modus'), findsNothing);
  });

  testWidgets('DemoBanner shows service label', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildWachbuchTheme(Brightness.light),
        home: const Scaffold(
          body: DemoBanner(
            visible: true,
            label: 'Demo-Modus',
            serviceLabel: 'Feuerwehr',
          ),
        ),
      ),
    );

    expect(find.text('Demo-Modus · Feuerwehr'), findsOneWidget);
    expect(find.byIcon(Icons.science_outlined), findsOneWidget);
  });
}
