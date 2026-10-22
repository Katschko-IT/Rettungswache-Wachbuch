import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/defect.dart';
import 'package:wachbuch_mobile/state/defect_state.dart';

class _FakeDefectApi extends WachbuchApi {
  _FakeDefectApi({this.items, this.error, this.onUpdate})
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  List<Defect>? items;
  ApiException? error;
  Defect Function(int id, String status)? onUpdate;

  @override
  Future<List<Defect>> defects() async {
    final err = error;
    if (err != null) throw err;
    return List<Defect>.from(items ?? const []);
  }

  @override
  Future<Defect> updateDefectStatus(int id, String status) async {
    final err = error;
    if (err != null) throw err;
    final handler = onUpdate;
    if (handler != null) return handler(id, status);
    return Defect(id: id, title: 'x', status: status);
  }
}

void main() {
  test('reload populates items and counts', () async {
    final api = _FakeDefectApi(
      items: const [
        Defect(id: 1, title: 'A', status: 'open', priority: 'urgent'),
        Defect(id: 2, title: 'B', status: 'done', priority: 'urgent'),
      ],
    );
    final state = DefectState(api: api);
    var notifications = 0;
    state.addListener(() => notifications++);

    await state.reload();

    expect(state.items.length, 2);
    expect(state.openCount, 1);
    expect(state.urgentCount, 1);
    expect(state.error, isNull);
    expect(notifications, greaterThanOrEqualTo(2));
    state.dispose();
  });

  test('404/501 module missing clears items without crashing', () async {
    final api = _FakeDefectApi(
      error: ApiException(404, 'nicht verfügbar'),
    );
    final state = DefectState(api: api);
    await state.reload();

    expect(state.items, isEmpty);
    expect(state.lastError?.statusCode, 404);
    expect(WachbuchApi.isModuleUnavailable(state.lastError!), isTrue);
    state.dispose();
  });

  test('setStatus replaces the matching item', () async {
    final api = _FakeDefectApi(
      items: const [Defect(id: 1, title: 'A', status: 'open')],
      onUpdate: (id, status) => Defect(id: id, title: 'A', status: status),
    );
    final state = DefectState(api: api);
    await state.reload();

    final ok = await state.setStatus(1, 'waiting');
    expect(ok, isTrue);
    expect(state.items.single.status, 'waiting');
    state.dispose();
  });
}
