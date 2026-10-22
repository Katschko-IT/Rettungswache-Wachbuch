import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/demo/demo_api.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';

void main() {
  test('DemoService maps dedicated local hosts', () {
    expect(
      DemoService.fromServerUrl('https://demo-feuerwehr.wachbuch.local'),
      DemoService.feuerwehr,
    );
    expect(DemoService.isDemoUrl('https://wache.example.org'), isFalse);
  });

  test('createWachbuchApi routes demo hosts to DemoWachbuchApi', () {
    final api = createWachbuchApi(DemoService.polizei.serverUrl);
    expect(api, isA<DemoWachbuchApi>());
  });

  test('DemoWachbuchApi serves profile handovers and modules offline', () async {
    final api = DemoWachbuchApi(profile: demoProfileFor(DemoService.rettungsdienst));

    final discovery = await api.discover();
    expect(discovery['demo'], isTrue);

    final me = await api.me();
    final station = (me['membership'] as Map)['station'] as Map;
    expect(station['name'], 'Rettungswache Musterstadt');
    expect((station['modules'] as Map)['calendar'], isTrue);

    final handovers = await api.handovers();
    expect(handovers, isNotEmpty);
    expect(handovers.first['title'], contains('[Demo]'));

    final detail = await api.handoverDetail(handovers.first['id'] as int);
    expect(detail['id'], handovers.first['id']);

    final kalender = await api.kalender();
    expect(kalender, isNotEmpty);

    final coffee = await api.kaffeekasse();
    expect(coffee.balance, isNotEmpty);

    final lists = await api.checklisten();
    expect(lists, isNotEmpty);
    final completed = await api.checklisteAbschluss(lists.first.id);
    expect(completed.completed, isTrue);
  });

  test('Feuerwehr and Polizei profiles use distinct stations', () {
    final fw = demoProfileFor(DemoService.feuerwehr);
    final pol = demoProfileFor(DemoService.polizei);
    expect(fw.stationName, contains('Feuerwehr'));
    expect(pol.stationName, contains('Polizei'));
    expect(fw.handovers.first['title'], isNot(equals(pol.handovers.first['title'])));
  });

  test('FFW profile and defect/asset/ack APIs work offline', () async {
    final api = DemoWachbuchApi(profile: demoProfileFor(DemoService.ffw));

    expect(DemoService.fromServerUrl(DemoService.ffw.serverUrl), DemoService.ffw);

    final me = await api.me();
    final modules =
        ((me['membership'] as Map)['station'] as Map)['modules'] as Map;
    expect(modules['defects'], isTrue);
    expect(modules['assets'], isTrue);

    final defects = await api.defects();
    expect(defects, isNotEmpty);
    final updated = await api.updateDefectStatus(defects.first.id, 'blocked');
    expect(updated.status, 'waiting');

    final assets = await api.assets();
    expect(assets, isNotEmpty);

    final handoverId = (await api.handovers()).first['id'] as int;
    final ack = await api.acknowledgeHandover(handoverId);
    expect(ack.by, demoProfileFor(DemoService.ffw).username);
    final again = await api.acknowledgeHandover(handoverId);
    expect(again.at, ack.at);
    expect((await api.handoverAcks(handoverId)).length, 1);

    final inventory = await api.inventory();
    expect(inventory, isNotEmpty);
    final available = inventory.firstWhere((item) => !item.isOut);
    final checkedOut = await api.inventoryCheckout(available.id);
    expect(checkedOut.isOut, isTrue);
    final checkedIn = await api.inventoryCheckin(available.id);
    expect(checkedIn.isOut, isFalse);
  });
}
