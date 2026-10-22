import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/ui/status_chip.dart';

void main() {
  group('StatusChip', () {
    Widget wrap(Widget child, {Locale locale = const Locale('de')}) {
      return MaterialApp(
        locale: locale,
        supportedLocales: const [Locale('de'), Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Scaffold(body: Center(child: child)),
      );
    }

    testWidgets('renders open status in German', (tester) async {
      await tester.pumpWidget(wrap(const StatusChip(status: 'open')));
      expect(find.text('Offen'), findsOneWidget);
    });

    testWidgets('renders in_progress status in German', (tester) async {
      await tester.pumpWidget(wrap(const StatusChip(status: 'in_progress')));
      expect(find.text('In Arbeit'), findsOneWidget);
    });

    testWidgets('renders done status in German', (tester) async {
      await tester.pumpWidget(wrap(const StatusChip(status: 'done')));
      expect(find.text('Erledigt'), findsOneWidget);
    });

    testWidgets('renders English defaults for English locale', (tester) async {
      await tester.pumpWidget(
        wrap(const StatusChip(status: 'open'), locale: const Locale('en')),
      );
      expect(find.text('Open'), findsOneWidget);
      expect(find.text('Offen'), findsNothing);
    });

    testWidgets('renders custom label', (tester) async {
      await tester.pumpWidget(
        wrap(const StatusChip(status: 'open', label: 'Custom')),
      );
      expect(find.text('Custom'), findsOneWidget);
    });
  });
}
