import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/checkliste.dart';
import 'package:wachbuch_mobile/screens/checklisten_screen.dart';

import 'test_localization.dart';

class _ChecklistenApi extends WachbuchApi {
  _ChecklistenApi(this.lists) : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final List<Checklist> lists;
  int abschlussCalls = 0;

  @override
  Future<List<Checklist>> checklisten() async => lists;

  @override
  Future<Checklist> checklisteAbschluss(int id) async {
    abschlussCalls += 1;
    return Checklist(
      id: id,
      title: lists.firstWhere((l) => l.id == id, orElse: () => lists.first).title,
      completed: true,
      completedAt: DateTime.parse('2026-08-02T20:00:00Z'),
      items: const [
        ChecklistItem(id: 1, label: 'RTW prüfen', checked: true),
        ChecklistItem(id: 2, label: 'Material', checked: true),
      ],
    );
  }
}

class _ErrorApi extends WachbuchApi {
  _ErrorApi() : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  @override
  Future<List<Checklist>> checklisten() async =>
      throw ApiException(503, 'Checklisten nicht erreichbar.');
}

void main() {
  testWidgets('renders checklists with items and completion button', (tester) async {
    await tester.pumpWidget(
      localizedApp(
        home: ChecklistenScreen(
          api: _ChecklistenApi([
            Checklist(
              id: 1,
              title: 'Tagescheckliste',
              description: 'Morgens',
              items: const [
                ChecklistItem(id: 1, label: 'RTW prüfen', checked: true),
                ChecklistItem(id: 2, label: 'Material', checked: false),
              ],
            ),
          ]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Checklisten'), findsOneWidget);
    expect(find.text('Tagescheckliste'), findsOneWidget);
    expect(find.text('Morgens'), findsOneWidget);
    expect(find.text('RTW prüfen'), findsOneWidget);
    expect(find.text('Material'), findsOneWidget);
    expect(find.text('Checkliste abschließen'), findsOneWidget);
    expect(find.text('1/2'), findsOneWidget);
  });

  testWidgets('completing a checklist calls the abschluss endpoint', (tester) async {
    final api = _ChecklistenApi([
      Checklist(
        id: 1,
        title: 'Tagescheckliste',
        items: const [
          ChecklistItem(id: 1, label: 'RTW prüfen', checked: true),
          ChecklistItem(id: 2, label: 'Material', checked: false),
        ],
      ),
    ]);

    await tester.pumpWidget(
      localizedApp(home: ChecklistenScreen(api: api)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Checkliste abschließen'));
    await tester.pumpAndSettle();

    expect(api.abschlussCalls, 1);
    expect(find.textContaining('Abgeschlossen'), findsOneWidget);
    expect(find.text('Checkliste abschließen'), findsNothing);
  });

  testWidgets('shows an empty state when no checklists exist', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: ChecklistenScreen(api: _ChecklistenApi(const []))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Keine Checklisten verfügbar.'), findsOneWidget);
  });

  testWidgets('shows an error banner on API failure', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: ChecklistenScreen(api: _ErrorApi())),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('nicht erreichbar'), findsOneWidget);
  });

  testWidgets('reverts optimistic completion when the endpoint fails', (tester) async {
    final api = _FailingAbschlussApi([
      Checklist(
        id: 1,
        title: 'Tagescheckliste',
        items: const [
          ChecklistItem(id: 1, label: 'RTW prüfen', checked: false),
        ],
      ),
    ]);

    await tester.pumpWidget(
      localizedApp(home: ChecklistenScreen(api: api)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Checkliste abschließen'));
    await tester.pumpAndSettle();

    expect(find.text('Checkliste abschließen'), findsOneWidget);
    expect(find.textContaining('fehlgeschlagen'), findsOneWidget);
  });
}

class _FailingAbschlussApi extends WachbuchApi {
  _FailingAbschlussApi(this.lists)
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final List<Checklist> lists;

  @override
  Future<List<Checklist>> checklisten() async => lists;

  @override
  Future<Checklist> checklisteAbschluss(int id) async =>
      throw ApiException(500, 'Abschluss fehlgeschlagen.');
}
