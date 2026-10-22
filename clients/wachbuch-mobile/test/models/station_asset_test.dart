import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/station_asset.dart';

void main() {
  group('StationAsset', () {
    test('parses kind and status enums', () {
      final asset = StationAsset.fromJson({
        'id': 'hlf-20',
        'label': 'HLF 20',
        'kind': 'vehicle',
        'status': 'limited',
        'note': 'Atemschutz',
      });

      expect(asset.id, 'hlf-20');
      expect(asset.label, 'HLF 20');
      expect(asset.kind, 'vehicle');
      expect(asset.status, 'limited');
      expect(asset.needsAttention, isTrue);
      expect(asset.isReady, isFalse);
    });

    test('accepts aliases for label and out-of-order status', () {
      final asset = StationAsset.fromJson({
        'id': 'key-1',
        'name': 'Zellenschlüssel',
        'kind': 'key',
        'status': 'außer_betrieb',
      });

      expect(asset.label, 'Zellenschlüssel');
      expect(asset.kind, 'key');
      expect(asset.status, 'oob');
    });

    test('defaults unknown kind/status defensively', () {
      final asset = StationAsset.fromJson({'id': 'x'});

      expect(asset.label, '');
      expect(asset.kind, 'device');
      expect(asset.status, 'ready');
      expect(asset.isReady, isTrue);
    });

    test('equality is id-based', () {
      const a = StationAsset(id: 'a', label: 'One');
      final b = a.copyWith(label: 'Two', status: 'workshop');

      expect(a == b, isTrue);
      expect(b.status, 'workshop');
    });
  });
}
