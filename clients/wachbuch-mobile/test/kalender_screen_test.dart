import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/kalender_entry.dart';
import 'package:wachbuch_mobile/screens/kalender_screen.dart';

import 'test_localization.dart';

class _KalenderApi extends WachbuchApi {
  _KalenderApi(this.entries)
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final List<KalenderEntry> entries;

  @override
  Future<List<KalenderEntry>> kalender() async => entries;
}

class _ErrorApi extends WachbuchApi {
  _ErrorApi()
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  @override
  Future<List<KalenderEntry>> kalender() async =>
      throw ApiException(503, 'Kalender nicht erreichbar.');
}

void main() {
  testWidgets('renders app bar and upcoming entries', (tester) async {
    await tester.pumpWidget(
      localizedApp(
        home: KalenderScreen(
          api: _KalenderApi([
            KalenderEntry(
              id: 1,
              title: 'RTW-Dienst',
              description: 'Frühschicht',
              startsAt: DateTime.parse('2026-08-03T06:00:00Z'),
              endsAt: DateTime.parse('2026-08-03T14:00:00Z'),
              location: 'Wache Nord',
            ),
            KalenderEntry(
              id: 2,
              title: 'Übung',
              allDay: true,
              startsAt: DateTime.parse('2026-08-05T00:00:00Z'),
            ),
          ]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Kalender'), findsOneWidget);
    expect(find.text('RTW-Dienst'), findsOneWidget);
    expect(find.text('Frühschicht'), findsOneWidget);
    expect(find.text('Wache Nord'), findsOneWidget);
    expect(find.text('Übung'), findsOneWidget);
  });

  testWidgets('shows an empty state when no entries exist', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: KalenderScreen(api: _KalenderApi(const []))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Keine anstehenden Termine.'), findsOneWidget);
  });

  testWidgets('shows an error banner on API failure', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: KalenderScreen(api: _ErrorApi())),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('nicht erreichbar'), findsOneWidget);
  });
}
