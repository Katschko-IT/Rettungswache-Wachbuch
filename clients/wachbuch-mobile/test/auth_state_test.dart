import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/state/auth_state.dart';

class _FakeApi extends WachbuchApi {
  _FakeApi(this._result)
    : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final Object _result;

  @override
  Future<Map<String, dynamic>> me() async {
    if (_result is Exception) throw _result;
    return Map<String, dynamic>.from(_result as Map);
  }
}

Map<String, dynamic> _mePayload({String stationName = 'Rettungswache Test'}) {
  return {
    'user': {'username': 'michael'},
    'membership': {
      'role_label': 'Schichtleitung',
      'station': {
        'name': stationName,
        'modules': {'coffee': true, 'calendar': false},
      },
    },
  };
}

void main() {
  test('reload() populates me and notifies listeners', () async {
    final api = _FakeApi(_mePayload());
    final state = AuthState(api: api);

    var notifications = 0;
    state.addListener(() => notifications++);

    expect(state.loading, isFalse);
    expect(state.me, isNull);

    final future = state.reload();
    expect(state.loading, isTrue);
    await future;

    expect(state.loading, isFalse);
    expect(state.error, isNull);
    expect(state.me?['user']['username'], 'michael');
    expect(notifications, greaterThanOrEqualTo(2));
    state.dispose();
  });

  test('reload() stores error message and status on API failure', () async {
    final api = _FakeApi(ApiException(401, 'Token ungültig'));
    final state = AuthState(api: api);

    await state.reload();

    expect(state.loading, isFalse);
    expect(state.me, isNull);
    expect(state.error, contains('Token ungültig'));
    expect(state.lastError?.statusCode, 401);
    state.dispose();
  });

  test('stationName, roleLabel and modules resolve from membership', () async {
    final api = _FakeApi(_mePayload(stationName: 'Wache Nord'));
    final state = AuthState(api: api);
    await state.reload();

    expect(state.stationName('Wachbuch'), 'Wache Nord');
    expect(state.roleLabel, 'Schichtleitung');
    expect(state.modules['coffee'], isTrue);
    expect(state.username, 'michael');
    expect(state.hasData, isTrue);
    state.dispose();
  });

  test('username falls back to top-level me.username', () async {
    final api = _FakeApi(<String, dynamic>{
      'username': 'demo-schicht',
      'membership': {
        'role_label': 'Schichtleitung',
        'station': {'name': 'RW', 'modules': {}},
      },
    });
    final state = AuthState(api: api);
    await state.reload();
    expect(state.username, 'demo-schicht');
    state.dispose();
  });

  test('stationName falls back when membership is absent', () async {
    final api = _FakeApi(<String, dynamic>{
      'user': {'username': 'x'},
    });
    final state = AuthState(api: api);
    await state.reload();

    expect(state.stationName('Wachbuch'), 'Wachbuch');
    expect(state.roleLabel, '');
    expect(state.modules, isEmpty);
    state.dispose();
  });

  group('account identity (login-user isolation)', () {
    test('userId/accountKey prefer the stable numeric id', () async {
      final api = _FakeApi({
        'user': {'id': 42, 'username': 'michael'},
      });
      final state = AuthState(api: api);
      await state.reload();

      expect(state.userId, 42);
      expect(state.accountKey, '42');
      state.dispose();
    });

    test('accountKey falls back to the username when the id is absent',
        () async {
      final api = _FakeApi({
        'user': {'username': 'michael'},
      });
      final state = AuthState(api: api);
      await state.reload();

      expect(state.userId, isNull);
      expect(state.accountKey, 'michael');
      state.dispose();
    });

    test('accountKey is null when unknown -> callers fail closed', () async {
      final api = _FakeApi(const <String, dynamic>{});
      final state = AuthState(api: api);
      await state.reload();

      expect(state.accountKey, isNull);
      state.dispose();
    });

    test('a captured caller keeps its identity across a reload', () async {
      final api = _MutableFakeApi({
        'user': {'id': 7, 'username': 'a'},
      });
      final state = AuthState(api: api);
      await state.reload();

      // The caller captures the current-login identity for local state.
      final captured = state.accountKey;
      expect(captured, '7');

      // The same app reloads after a logout + different login.
      api.payload = {
        'user': {'id': 8, 'username': 'b'},
      };
      await state.reload();

      expect(state.accountKey, '8');
      // The captured snapshot is unchanged (immutable identity).
      expect(captured, '7');
      state.dispose();
    });
  });
}

class _MutableFakeApi extends WachbuchApi {
  _MutableFakeApi(this.payload)
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  Map<String, dynamic> payload;

  @override
  Future<Map<String, dynamic>> me() async => payload;
}
