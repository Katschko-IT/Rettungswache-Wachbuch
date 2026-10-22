import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/kaffeekasse.dart';
import 'package:wachbuch_mobile/state/coffee_state.dart';

class _FakeApi extends WachbuchApi {
  _FakeApi(this._result) : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final Object _result;

  @override
  Future<Kaffeekasse> kaffeekasse() async {
    if (_result is Exception) throw _result;
    return _result as Kaffeekasse;
  }
}

void main() {
  test('reload() populates data on success and notifies listeners', () async {
    final api = _FakeApi(Kaffeekasse(balance: '5,00 €', currency: 'EUR'));
    final state = CoffeeState(api: api);

    var notifications = 0;
    state.addListener(() => notifications++);

    expect(state.loading, isFalse);
    expect(state.data, isNull);
    expect(state.error, isNull);

    final future = state.reload();
    expect(state.loading, isTrue);
    await future;

    expect(state.loading, isFalse);
    expect(state.error, isNull);
    expect(state.data?.balance, '5,00 €');
    expect(notifications, greaterThanOrEqualTo(2));
    state.dispose();
  });

  test('reload() stores error message on API failure', () async {
    final api = _FakeApi(ApiException(503, 'Kaffeekasse nicht erreichbar.'));
    final state = CoffeeState(api: api);

    await state.reload();

    expect(state.loading, isFalse);
    expect(state.data, isNull);
    expect(state.error, contains('Kaffeekasse nicht erreichbar'));
    state.dispose();
  });
}
