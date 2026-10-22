import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/inventory_item.dart';

void main() {
  group('InventoryItem', () {
    test('parses checkout fields and aliases', () {
      final item = InventoryItem.fromJson({
        'id': 'bodycam-7',
        'name': 'Bodycam 7',
        'kind': 'device',
        'checked_out_by': 'demo-mitglied',
        'checked_out_at': '2026-08-09T05:50:00Z',
        'note': '',
      });

      expect(item.label, 'Bodycam 7');
      expect(item.holder, 'demo-mitglied');
      expect(item.isOut, isTrue);
      expect(item.since, isNotNull);
    });

    test('treats empty holder as available', () {
      final item = InventoryItem.fromJson({
        'id': 'key-1',
        'label': 'Zellenschlüssel',
        'kind': 'key',
        'holder': '',
        'since_label': '—',
      });

      expect(item.isOut, isFalse);
      expect(item.holder, isNull);
      expect(item.kind, 'key');
    });

    test('copyWith clearHolder resets checkout', () {
      const item = InventoryItem(
        id: 'a',
        label: 'A',
        holder: 'x',
        sinceLabel: 'heute',
      );
      final cleared = item.copyWith(clearHolder: true);

      expect(cleared.isOut, isFalse);
      expect(cleared.sinceLabel, '');
      expect(cleared == item, isTrue);
    });
  });
}
