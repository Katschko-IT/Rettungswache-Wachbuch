import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/defect.dart';

void main() {
  group('Defect', () {
    test('parses contract fields and ISO due date', () {
      final defect = Defect.fromJson({
        'id': 7,
        'title': 'Defi-Akku schwach',
        'description': 'RTW-1 Reservegerät',
        'asset_ref': 'RTW-1',
        'priority': 'urgent',
        'status': 'in_progress',
        'owner': 'demo-schicht',
        'due_at': '2026-08-12T12:00:00Z',
        'category': 'material',
      });

      expect(defect.id, 7);
      expect(defect.title, 'Defi-Akku schwach');
      expect(defect.assetRef, 'RTW-1');
      expect(defect.priority, 'urgent');
      expect(defect.status, 'in_progress');
      expect(defect.owner, 'demo-schicht');
      expect(defect.dueAt, isNotNull);
      expect(defect.category, 'material');
      expect(defect.isOpen, isTrue);
      expect(defect.isUrgent, isTrue);
    });

    test('accepts camelCase aliases and status/priority synonyms', () {
      final defect = Defect.fromJson({
        'id': '3',
        'title': 'Licht',
        'assetRef': 'HLF-20',
        'priority': 'high',
        'status': 'blocked',
        'due': 'heute 14:00',
        'dueLabel': 'ignored-when-due-set',
        'category': 'unknown-cat',
      });

      expect(defect.id, 3);
      expect(defect.assetRef, 'HLF-20');
      expect(defect.priority, 'urgent');
      expect(defect.status, 'waiting');
      expect(defect.dueLabel, 'heute 14:00');
      expect(defect.category, 'task');
    });

    test('is defensive about missing and garbage fields', () {
      final defect = Defect.fromJson({});

      expect(defect.id, 0);
      expect(defect.title, '');
      expect(defect.priority, 'normal');
      expect(defect.status, 'open');
      expect(defect.dueAt, isNull);
      expect(defect.isUrgent, isFalse);
    });

    test('toJson round-trips contract keys', () {
      final original = Defect.fromJson({
        'id': 1,
        'title': 'A',
        'status': 'waiting',
        'priority': 'important',
        'due_label': 'morgen',
      });
      final again = Defect.fromJson(original.toJson());

      expect(again.id, original.id);
      expect(again.status, 'waiting');
      expect(again.priority, 'important');
      expect(again.dueLabel, 'morgen');
    });

    test('copyWith and id-based equality', () {
      const a = Defect(id: 1, title: 'A');
      final b = a.copyWith(status: 'done', title: 'B');

      expect(a == b, isTrue);
      expect(a.hashCode, b.hashCode);
      expect(b.status, 'done');
      expect(b.title, 'B');
      expect(b.isOpen, isFalse);
    });
  });
}
