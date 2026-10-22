import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/ui/priority_badge.dart';

void main() {
  group('PriorityBadge', () {
    Widget wrap(Widget child, {Locale locale = const Locale('de')}) {
      return MaterialApp(
        locale: locale,
        supportedLocales: const [Locale('de'), Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Scaffold(body: Center(child: child)),
      );
    }

    testWidgets('renders urgent label and dot in German', (tester) async {
      await tester.pumpWidget(wrap(const PriorityBadge(priority: 'urgent')));
      expect(find.text('Dringend'), findsOneWidget);
      expect(find.byType(Container), findsWidgets);
    });

    testWidgets('renders important label in German', (tester) async {
      await tester.pumpWidget(wrap(const PriorityBadge(priority: 'important')));
      expect(find.text('Wichtig'), findsOneWidget);
    });

    testWidgets('renders English defaults for English locale', (tester) async {
      await tester.pumpWidget(
        wrap(
          const PriorityBadge(priority: 'urgent'),
          locale: const Locale('en'),
        ),
      );
      expect(find.text('Urgent'), findsOneWidget);
      expect(find.text('Dringend'), findsNothing);
    });

    testWidgets('renders custom label when provided', (tester) async {
      await tester.pumpWidget(
        wrap(const PriorityBadge(priority: 'urgent', label: 'ASAP')),
      );
      expect(find.text('ASAP'), findsOneWidget);
    });

    testWidgets('compact mode has smaller text', (tester) async {
      await tester.pumpWidget(
        wrap(const PriorityBadge(priority: 'normal', compact: true)),
      );
      final text = tester.widget<Text>(find.text('Normal'));
      expect(text.style?.fontSize, lessThanOrEqualTo(12));
    });
  });
}
