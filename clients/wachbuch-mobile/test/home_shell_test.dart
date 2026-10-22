import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/screens/home_shell.dart';

import 'test_localization.dart';

void _usePhone(WidgetTester tester) {
  tester.view.physicalSize = const Size(400, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
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

class _ImmediateApi extends WachbuchApi {
  _ImmediateApi()
    : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  bool closed = false;

  @override
  Future<Map<String, dynamic>> me() async => _mePayload();

  @override
  Future<List<Map<String, dynamic>>> handovers() async => [
    {
      'title': 'RTW auffüllen',
      'priority': 'urgent',
      'status': 'open',
      'category': 'task',
    },
  ];

  @override
  void close() {
    closed = true;
    super.close();
  }
}

class _PolishedApi extends _ImmediateApi {
  int detailCalls = 0;

  @override
  Future<List<Map<String, dynamic>>> handovers() async => [
    {
      'id': 1,
      'title': 'RTW auffüllen',
      'priority': 'urgent',
      'status': 'open',
      'category': 'vehicle',
      'updated_at': '2026-08-02T10:30:00+00:00',
    },
    {
      'id': 2,
      'title': 'Medikamentenschrank prüfen',
      'priority': 'important',
      'status': 'in_progress',
      'category': 'material',
      'updated_at': '2026-08-02T09:00:00+00:00',
    },
    {
      'id': 3,
      'title': 'Tor der Fahrzeughalle',
      'priority': 'normal',
      'status': 'open',
      'category': 'station',
      'updated_at': '2026-08-01T18:00:00+00:00',
    },
  ];

  @override
  Future<Map<String, dynamic>> handoverDetail(int id) async {
    detailCalls += 1;
    return {
      'id': id,
      'title': 'RTW auffüllen',
      'details': 'Fach 3 kontrollieren und Verbrauchsmaterial ergänzen.',
      'priority': 'urgent',
      'status': 'open',
      'category': 'vehicle',
      'author': {'display_name': 'Michael'},
      'version': 2,
      'created_at': '2026-08-01T08:00:00+00:00',
      'updated_at': '2026-08-02T10:30:00+00:00',
    };
  }
}

class _FilterReloadApi extends _ImmediateApi {
  int handoverCalls = 0;

  @override
  Future<List<Map<String, dynamic>>> handovers() async {
    handoverCalls += 1;
    if (handoverCalls == 1) {
      return [
        {
          'id': 1,
          'title': 'Dringende Übergabe',
          'priority': 'urgent',
          'status': 'open',
          'category': 'task',
        },
      ];
    }
    return [
      {
        'id': 2,
        'title': 'Neue normale Übergabe',
        'priority': 'normal',
        'status': 'in_progress',
        'category': 'station',
      },
    ];
  }
}

class _MalformedApi extends _ImmediateApi {
  @override
  Future<List<Map<String, dynamic>>> handovers() async => [
    {
      'id': 7,
      'title': 123,
      'priority': 'normal',
      'status': 'open',
      'category': 'task',
    },
  ];

  @override
  Future<Map<String, dynamic>> handoverDetail(int id) async => {
    'id': id,
    'title': 123,
    'details': 'Defensive Datenanzeige',
    'author': 'unerwarteter API-Wert',
  };
}

class _ControlledApi extends WachbuchApi {
  _ControlledApi(this.meResult)
    : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final Completer<Map<String, dynamic>> meResult;

  @override
  Future<Map<String, dynamic>> me() => meResult.future;

  @override
  Future<List<Map<String, dynamic>>> handovers() async => [];
}

class _ReloadApi extends WachbuchApi {
  _ReloadApi({this.stationName = 'Rettungswache Test'})
    : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final String stationName;
  final secondMe = Completer<Map<String, dynamic>>();
  int calls = 0;

  @override
  Future<Map<String, dynamic>> me() {
    calls += 1;
    if (calls == 1) {
      return Future.value(_mePayload(stationName: stationName));
    }
    return secondMe.future;
  }

  @override
  Future<List<Map<String, dynamic>>> handovers() async => [];
}

void main() {
  testWidgets('renders station, handovers and account data', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _ImmediateApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Rettungswache Test'), findsWidgets);
    expect(find.text('1 offen'), findsOneWidget);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);

    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();
    expect(find.text('RTW auffüllen'), findsOneWidget);

    await tester.tap(find.text('Konto'));
    await tester.pumpAndSettle();
    expect(find.text('michael'), findsOneWidget);
    expect(find.text('https://wache.example.org'), findsOneWidget);
  });

  testWidgets('overview summarizes status and urgent priorities', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('2 offen'), findsOneWidget);
    expect(find.text('1 in Bearbeitung'), findsOneWidget);
    expect(find.text('1 dringend'), findsOneWidget);
  });

  testWidgets('handover search filters live and reports result count', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('handover-search')),
      'medikament',
    );
    await tester.pump();

    expect(find.text('Medikamentenschrank prüfen'), findsOneWidget);
    expect(find.text('RTW auffüllen'), findsNothing);
    expect(find.text('1 von 3 Übergaben'), findsOneWidget);
  });

  testWidgets('priority filter and search combine with AND', (tester) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('priority-filter-urgent')));
    await tester.pump();
    expect(find.text('RTW auffüllen'), findsOneWidget);
    expect(find.text('Medikamentenschrank prüfen'), findsNothing);

    await tester.enterText(
      find.byKey(const Key('handover-search')),
      'Medikament',
    );
    await tester.pump();
    expect(find.text('Keine Übergaben für diese Filter.'), findsOneWidget);
  });

  testWidgets('handover cards use localized chips and open real details', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();

    expect(find.text('Fahrzeugstatus'), findsOneWidget);
    expect(find.text('Dringend'), findsWidgets);
    expect(find.text('Offen'), findsWidgets);

    await tester.tap(find.text('RTW auffüllen'));
    await tester.pumpAndSettle();

    expect(
      find.text('Fach 3 kontrollieren und Verbrauchsmaterial ergänzen.'),
      findsOneWidget,
    );
    expect(find.text('Michael'), findsOneWidget);
    expect(find.text('Version 2'), findsOneWidget);
  });

  testWidgets('detail endpoint is called once when sheet rebuilds', (
    tester,
  ) async {
    _usePhone(tester);
    final api = _PolishedApi();
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: api,
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('RTW auffüllen'));
    await tester.pumpAndSettle();
    expect(api.detailCalls, 1);

    tester.view.physicalSize = const Size(420, 800);
    await tester.pumpAndSettle();

    expect(api.detailCalls, 1);
  });

  testWidgets('active filter remains visible and removable after reload', (
    tester,
  ) async {
    _usePhone(tester);
    final api = _FilterReloadApi();
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: api,
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('priority-filter-urgent')));
    await tester.pump();

    await tester.tap(find.byTooltip('Aktualisieren'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('priority-filter-urgent')), findsOneWidget);
    expect(find.text('Keine Übergaben für diese Filter.'), findsOneWidget);
    await tester.tap(find.byKey(const Key('priority-filter-urgent')));
    await tester.pump();
    expect(find.text('Neue normale Übergabe'), findsOneWidget);
  });

  testWidgets('malformed optional API fields do not crash cards or details', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _MalformedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();
    expect(find.text('123'), findsOneWidget);

    await tester.tap(find.text('123'));
    await tester.pumpAndSettle();

    expect(find.text('Defensive Datenanzeige'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('handover cards support 200 percent text scaling', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(2)),
          child: child!,
        ),
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();

    expect(find.text('RTW auffüllen'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('tablet layout uses Material NavigationRail', (tester) async {
    tester.view.physicalSize = const Size(900, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _ImmediateApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('late API errors do not call setState after dispose', (
    tester,
  ) async {
    final response = Completer<Map<String, dynamic>>();
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _ControlledApi(response),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pump();

    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    response.completeError(ApiException(503, 'Server nicht erreichbar.'));
    await tester.pump();

    expect(tester.takeException(), isNull);
  });

  testWidgets('disposing HomeShell closes its API client', (tester) async {
    final api = _ImmediateApi();
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: api,
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));

    expect(api.closed, isTrue);
  });

  testWidgets('account actions are disabled during reload', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = _ReloadApi();

    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: api,
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Konto'));
    await tester.pumpAndSettle();

    await tester.tap(
      find.widgetWithText(OutlinedButton, 'Profil aktualisieren'),
    );
    await tester.pump();

    final refresh = tester.widget<OutlinedButton>(
      find.widgetWithText(OutlinedButton, 'Profil aktualisieren'),
    );
    final logout = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Abmelden'),
    );
    final changeServer = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Anderen Server einrichten'),
    );
    expect(refresh.onPressed, isNull);
    expect(logout.onPressed, isNull);
    expect(changeServer.onPressed, isNull);

    api.secondMe.complete(_mePayload());
    await tester.pumpAndSettle();
  });

  testWidgets('station named Wachbuch keeps content visible during reload', (
    tester,
  ) async {
    final api = _ReloadApi(stationName: 'Wachbuch');
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: api,
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Aktive Übergaben'), findsOneWidget);

    await tester.tap(find.byTooltip('Aktualisieren'));
    await tester.pump();

    expect(find.text('Aktive Übergaben'), findsOneWidget);

    api.secondMe.complete(_mePayload(stationName: 'Wachbuch'));
    await tester.pumpAndSettle();
  });

  testWidgets('overview presents key figures as scannable dashboard cards', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('overview-stat-open')), findsOneWidget);
    expect(find.byKey(const Key('overview-stat-progress')), findsOneWidget);
    expect(find.byKey(const Key('overview-stat-urgent')), findsOneWidget);
  });

  testWidgets('overview metrics wrap on narrow screens with large text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      localizedApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(2)),
          child: child!,
        ),
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    final open = tester.getTopLeft(find.byKey(const Key('overview-stat-open')));
    final urgent = tester.getTopLeft(
      find.byKey(const Key('overview-stat-urgent')),
    );
    expect(urgent.dy, greaterThan(open.dy));
    expect(tester.takeException(), isNull);
  });

  testWidgets('long station name is protected by an ellipsis in the app bar', (
    tester,
  ) async {
    _usePhone(tester);
    const name = 'Rettungswache Rheda-Wiedenbrück Nord mit sehr langem Namen';
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _ReloadApi(stationName: name),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    final title = tester.widget<Text>(
      find.descendant(of: find.byType(AppBar), matching: find.text(name)),
    );
    expect(title.maxLines, 1);
    expect(title.overflow, TextOverflow.ellipsis);
  });

  testWidgets('status labels use at least 14sp for field readability', (
    tester,
  ) async {
    _usePhone(tester);
    await tester.pumpWidget(
      localizedApp(
        home: HomeShell(
          api: _PolishedApi(),
          onLogout: () async {},
          onChangeServer: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();

    final urgent = tester.widgetList<Text>(find.text('Dringend')).last;
    expect(urgent.style?.fontSize, greaterThanOrEqualTo(14));
  });

  testWidgets(
    'station modules are rendered as information, not disabled filters',
    (tester) async {
      _usePhone(tester);
      await tester.pumpWidget(
        localizedApp(
          home: HomeShell(
            api: _ImmediateApi(),
            onLogout: () async {},
            onChangeServer: () async {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(Chip), findsNWidgets(2));
      expect(find.text('Kaffeekasse'), findsWidgets);
      expect(find.text('Kalender'), findsOneWidget);
      expect(find.byType(FilterChip), findsNothing);
    },
  );
}
