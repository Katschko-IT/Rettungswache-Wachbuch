import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/kalender_entry.dart';

void main() {
  group('KalenderEntry', () {
    test('parses starts_at / ends_at and trims the title', () {
      final entry = KalenderEntry.fromJson({
        'id': 7,
        'title': '  RTW-Dienst  ',
        'description': 'Frühschicht',
        'starts_at': '2026-08-03T06:00:00+00:00',
        'ends_at': '2026-08-03T14:00:00+00:00',
        'all_day': false,
        'location': 'Wache Nord',
      });

      expect(entry.id, 7);
      expect(entry.title, 'RTW-Dienst');
      expect(entry.description, 'Frühschicht');
      expect(entry.startsAt, isNotNull);
      expect(entry.endsAt, isNotNull);
      expect(entry.allDay, isFalse);
      expect(entry.location, 'Wache Nord');
    });

    test('accepts start/end aliases and all-day flag', () {
      final entry = KalenderEntry.fromJson({
        'id': '12',
        'title': 'Dienstsicherung',
        'start': '2026-08-04',
        'end': '2026-08-04',
        'all_day': true,
      });

      expect(entry.id, 12);
      expect(entry.allDay, isTrue);
      expect(entry.startsAt, isNotNull);
    });

    test('is defensive about missing fields', () {
      final entry = KalenderEntry.fromJson({'id': 1});

      expect(entry.title, '');
      expect(entry.description, '');
      expect(entry.startsAt, isNull);
      expect(entry.endsAt, isNull);
      expect(entry.allDay, isFalse);
      expect(entry.location, '');
    });

    test('copyWith preserves unchanged fields', () {
      final original = KalenderEntry.fromJson({
        'id': 1,
        'title': 'Alt',
        'starts_at': '2026-08-03T08:00:00+00:00',
      });
      final updated = original.copyWith(title: 'Neu');

      expect(updated.title, 'Neu');
      expect(updated.id, 1);
      expect(updated.startsAt, original.startsAt);
    });

    test('equality is id-based', () {
      final a = KalenderEntry.fromJson({'id': 1, 'title': 'A'});
      final b = KalenderEntry.fromJson({'id': 1, 'title': 'B'});
      final c = KalenderEntry.fromJson({'id': 2, 'title': 'A'});

      expect(a == b, isTrue);
      expect(a == c, isFalse);
      expect(a.hashCode, b.hashCode);
    });
  });
}
