import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/demo/demo_api.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';

void main() {
  group('DemoWachbuchApi production parity', () {
    late DemoWachbuchApi api;
    late int defectId;

    setUp(() async {
      api = DemoWachbuchApi(
        profile: demoProfileFor(DemoService.rettungsdienst),
      );
      final defects = await api.defects();
      expect(defects, isNotEmpty);
      defectId = defects.first.id;
    });

    test('rejects a fake JPEG just like the real server', () async {
      await expectLater(
        api.uploadDefectAttachment(
          defectId,
          filename: 'fake.jpg',
          contentType: 'image/jpeg',
          bytes: Uint8List.fromList([1, 2, 3, 4]),
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'statusCode', 415),
        ),
      );
    });

    test('enforces eight-photo quota per defect', () async {
      final jpeg = Uint8List.fromList([0xff, 0xd8, 0xff, 0x00]);
      for (var index = 0; index < 8; index++) {
        await api.uploadDefectAttachment(
          defectId,
          filename: 'photo-$index.jpg',
          contentType: 'image/jpeg',
          bytes: jpeg,
        );
      }

      await expectLater(
        api.uploadDefectAttachment(
          defectId,
          filename: 'photo-9.jpg',
          contentType: 'image/jpeg',
          bytes: jpeg,
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'statusCode', 409),
        ),
      );
      expect((await api.defectAttachments(defectId)).length, 8);
    });

    test('copyWithToken preserves completed checklist state', () async {
      final checklists = await api.checklisten();
      expect(checklists, isNotEmpty);
      final id = checklists.first.id;
      await api.checklisteAbschluss(id);

      final copied = api.copyWithToken('wb_demo_replacement');
      final copiedChecklist = (await copied.checklisten())
          .firstWhere((item) => item.id == id);
      expect(copiedChecklist.completed, isTrue);
    });
  });
}
