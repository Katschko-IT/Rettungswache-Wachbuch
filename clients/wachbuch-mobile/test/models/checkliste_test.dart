import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/checkliste.dart';

void main() {
  group('server payload (core/api checklists_api)', () {
    test('reads string items and last completion', () {
      final now = DateTime.now().toUtc();
      final list = Checklist.fromJson({
        'id': 4,
        'title': 'Fahrzeugcheck',
        'description': 'Morgens',
        'items': ['Reifen', 'Licht', ''],
        'last_completed_at': now.toIso8601String(),
        'last_completed_by': 'Sandra',
        'interval': '',
        'due_next': null,
        'overdue': false,
      });

      expect(list.items.map((item) => item.label), ['Reifen', 'Licht']);
      expect(list.completedAt, isNotNull);
      expect(list.completedBy, 'Sandra');
      expect(list.completed, isTrue);
    });

    test('older completion of a daily list is not completed today', () {
      final list = Checklist.fromJson({
        'id': 5,
        'title': 'Desinfektion',
        'items': ['Trage'],
        'last_completed_at': DateTime.now()
            .subtract(const Duration(days: 2))
            .toUtc()
            .toIso8601String(),
        'interval': 'daily',
      });

      expect(list.completed, isFalse);
    });

    test('overdue schedule is never shown as completed', () {
      final list = Checklist.fromJson({
        'id': 6,
        'title': 'Wochencheck',
        'items': ['Funk'],
        'last_completed_at': DateTime.now().toUtc().toIso8601String(),
        'interval': 'weekly',
        'due_next': DateTime.now()
            .subtract(const Duration(days: 1))
            .toUtc()
            .toIso8601String(),
        'overdue': true,
      });

      expect(list.overdue, isTrue);
      expect(list.completed, isFalse);
    });
  });

  group('Checklist', () {
    test('parses items, completion flag and completion object', () {
      final list = Checklist.fromJson({
        'id': 1,
        'title': 'Tagescheckliste',
        'description': 'Morgens erledigen',
        'items': [
          {'id': 1, 'label': 'RTW prüfen', 'checked': true},
          {'id': 2, 'title': 'Material auffüllen', 'done': false},
          {'id': 3, 'text': 'Torräume', 'checked': false},
        ],
        'completion': {'created_at': '2026-08-02T07:00:00+00:00'},
      });

      expect(list.id, 1);
      expect(list.title, 'Tagescheckliste');
      expect(list.description, 'Morgens erledigen');
      expect(list.items.length, 3);
      expect(list.items[0].label, 'RTW prüfen');
      expect(list.items[0].checked, isTrue);
      expect(list.items[1].label, 'Material auffüllen');
      expect(list.items[1].checked, isFalse);
      expect(list.checkedCount, 1);
      expect(list.allChecked, isFalse);
      expect(list.completedAt, isNotNull);
    });

    test('marks completed via completed flag', () {
      final list = Checklist.fromJson({
        'id': 2,
        'title': 'Wochenbogen',
        'completed': true,
        'completed_at': '2026-08-01T12:00:00+00:00',
        'items': [
          {'id': 1, 'label': 'A', 'checked': true},
          {'id': 2, 'label': 'B', 'checked': true},
        ],
      });

      expect(list.completed, isTrue);
      expect(list.allChecked, isTrue);
      expect(list.checkedCount, 2);
    });

    test('is defensive about missing items and completion', () {
      final list = Checklist.fromJson({'id': 9, 'title': 'Leer'});

      expect(list.items, isEmpty);
      expect(list.allChecked, isFalse);
      expect(list.completed, isFalse);
      expect(list.completedAt, isNull);
    });

    test('does not crash when completion is not an object', () {
      final list = Checklist.fromJson({
        'id': 3,
        'title': 'X',
        'completion': 'unerwartet',
      });

      expect(list.completedAt, isNull);
    });

    test('copyWith overrides completion and items', () {
      final original = Checklist.fromJson({
        'id': 1,
        'title': 'A',
        'items': [
          {'id': 1, 'label': 'x', 'checked': false},
        ],
      });
      final updated = original.copyWith(
        completed: true,
        items: const [
          ChecklistItem(id: 1, label: 'x', checked: true),
        ],
      );

      expect(updated.completed, isTrue);
      expect(updated.items.first.checked, isTrue);
      expect(updated.allChecked, isTrue);
      expect(updated.title, 'A');
    });

    test('equality is id-based', () {
      final a = Checklist.fromJson({'id': 1, 'title': 'A'});
      final b = Checklist.fromJson({'id': 1, 'title': 'B', 'completed': true});

      expect(a == b, isTrue);
      expect(a.hashCode, b.hashCode);
    });

    test('parses recurring interval, due_next and overdue', () {
      final due = Checklist.fromJson({
        'id': 4,
        'title': 'Wachabschluss',
        'interval': 'daily',
        'due_next': DateTime.now().toUtc().toIso8601String(),
        'overdue': false,
        'items': [
          {'id': 1, 'label': 'x', 'checked': false},
        ],
      });
      expect(due.interval, 'daily');
      expect(due.isRecurring, isTrue);
      expect(due.isDueToday, isTrue);

      final overdue = Checklist.fromJson({
        'id': 5,
        'title': 'Wochenheck',
        'interval': 'weekly',
        'due_next': '2020-01-01T00:00:00Z',
      });
      expect(overdue.overdue, isTrue);
      expect(overdue.interval, 'weekly');
    });
  });

  group('ChecklistItem', () {
    test('parses label aliases and checked states', () {
      final fromTitle =
          ChecklistItem.fromJson({'id': 1, 'title': 'T', 'done': true});
      final fromText =
          ChecklistItem.fromJson({'id': 2, 'text': 'T2', 'checked': true});

      expect(fromTitle.label, 'T');
      expect(fromTitle.checked, isTrue);
      expect(fromText.label, 'T2');
      expect(fromText.checked, isTrue);
    });

    test('falls back to defaults for empty payloads', () {
      final item = ChecklistItem.fromJson({'id': 5});

      expect(item.label, '');
      expect(item.checked, isFalse);
      expect(item.note, '');
    });
  });
}
