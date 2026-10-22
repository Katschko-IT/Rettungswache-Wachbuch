import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/theme/app_theme.dart';
import 'package:wachbuch_mobile/ui/offline_banner.dart';

void main() {
  testWidgets('OfflineBanner is hidden when visible=false', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildWachbuchTheme(Brightness.light),
        home: const Scaffold(
          body: OfflineBanner(visible: false, onRetry: _noop),
        ),
      ),
    );

    expect(find.text('Keine Verbindung'), findsNothing);
    expect(find.text('Erneut'), findsNothing);
    expect(find.byIcon(Icons.signal_wifi_off), findsNothing);
  });

  testWidgets('OfflineBanner is visible when visible=true', (tester) async {
    var taps = 0;

    await tester.pumpWidget(
      MaterialApp(
        theme: buildWachbuchTheme(Brightness.light),
        home: Scaffold(
          body: OfflineBanner(
            visible: true,
            onRetry: () => taps++,
          ),
        ),
      ),
    );

    expect(find.text('Keine Verbindung'), findsOneWidget);
    expect(find.byIcon(Icons.signal_wifi_off), findsOneWidget);
    await tester.tap(find.text('Erneut'));
    await tester.pump();
    expect(taps, 1);
  });
}

void _noop() {}
