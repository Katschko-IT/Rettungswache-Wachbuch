import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/ui/handover_filter.dart';

void main() {
  const items = [
    {
      'id': 1,
      'title': 'RTW auffüllen',
      'category': 'vehicle',
      'priority': 'urgent',
      'status': 'open',
    },
    {
      'id': 2,
      'title': 'Medikamentenschrank prüfen',
      'category': 'material',
      'priority': 'important',
      'status': 'in_progress',
    },
    {
      'id': 3,
      'title': 'Tor der Fahrzeughalle',
      'category': 'station',
      'priority': 'normal',
      'status': 'open',
    },
  ];

  late AppLocalizations l10n;

  setUpAll(() async {
    l10n = await AppLocalizations.delegate.load(const Locale('de'));
  });

  test('empty query and filters preserve every handover', () {
    expect(filterHandovers(items, l10n: l10n), items);
  });

  test('search matches title case-insensitively', () {
    final result = filterHandovers(items, l10n: l10n, query: 'rtw');

    expect(result.map((item) => item['id']), [1]);
  });

  test('search also matches the localized category label', () {
    final result = filterHandovers(items, l10n: l10n, query: 'material');

    expect(result.map((item) => item['id']), [2]);
  });

  test('status and priority filters combine with AND', () {
    final result = filterHandovers(
      items,
      l10n: l10n,
      statuses: {'open'},
      priorities: {'normal'},
    );

    expect(result.map((item) => item['id']), [3]);
  });

  test('missing fields do not throw and do not match active filters', () {
    final result = filterHandovers(
      const [
        {'id': 4},
      ],
      l10n: l10n,
      statuses: {'open'},
    );

    expect(result, isEmpty);
  });

  test('server enum values receive German labels', () {
    expect(handoverStatusLabel('in_progress', l10n), 'In Bearbeitung');
    expect(handoverPriorityLabel('urgent', l10n), 'Dringend');
    expect(handoverCategoryLabel('vehicle', l10n), 'Fahrzeugstatus');
  });

  test('unknown enum values get a readable fallback', () {
    expect(handoverStatusLabel('waiting_for_team', l10n), 'Waiting For Team');
    expect(handoverPriorityLabel('', l10n), 'Nicht angegeben');
  });
}
