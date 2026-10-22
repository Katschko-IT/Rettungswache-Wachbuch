import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/pinboard_note.dart';

void main() {
  group('PinboardNote.fromJson', () {
    test('parses full payload', () {
      final note = PinboardNote.fromJson({
        'id': 7,
        'title': '  Titel  ',
        'body': '  Text  ',
        'category': 'important',
        'is_pinned': true,
        'author': {'display_name': 'Mara'},
        'updated_at': '2026-08-11T10:00:00Z',
      });
      expect(note.id, 7);
      expect(note.title, 'Titel');
      expect(note.body, 'Text');
      expect(note.category, 'important');
      expect(note.isPinned, isTrue);
      expect(note.authorName, 'Mara');
      expect(note.updatedAt, isNotNull);
    });

    test('applies defaults for a minimal payload', () {
      final note = PinboardNote.fromJson({'title': 'Nur Titel'});
      expect(note.id, 0);
      expect(note.category, 'info');
      expect(note.isPinned, isFalse);
      expect(note.authorName, '');
      expect(note.updatedAt, isNull);
    });

    test('reads author from a plain string', () {
      final note = PinboardNote.fromJson({'title': 'x', 'author': 'Chris'});
      expect(note.authorName, 'Chris');
    });
  });
}
