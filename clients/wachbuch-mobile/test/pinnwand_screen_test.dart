import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/pinboard_note.dart';
import 'package:wachbuch_mobile/screens/pinnwand_screen.dart';

import 'test_localization.dart';

class _FakePinboardApi extends WachbuchApi {
  _FakePinboardApi(this._notes)
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final List<PinboardNote> _notes;
  int createCalls = 0;

  @override
  Future<List<PinboardNote>> pinboard() async => _notes;

  @override
  Future<PinboardNote> createPinboardNote({
    required String title,
    required String body,
    String category = 'info',
  }) async {
    createCalls++;
    final note = PinboardNote(
      id: 99,
      title: title,
      body: body,
      category: category,
    );
    _notes.insert(0, note);
    return note;
  }
}

class _ErrorPinboardApi extends WachbuchApi {
  _ErrorPinboardApi()
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  @override
  Future<List<PinboardNote>> pinboard() async =>
      throw ApiException(503, 'Pinnwand nicht erreichbar.');
}

void main() {
  testWidgets('renders notes with title, body and pinned marker',
      (tester) async {
    await tester.pumpWidget(
      localizedApp(
        home: PinnwandScreen(
          api: _FakePinboardApi([
            PinboardNote(
              id: 1,
              title: 'Teamabend',
              body: 'Freitag 19 Uhr',
              category: 'event',
              isPinned: true,
              authorName: 'Alex',
            ),
          ]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Pinnwand'), findsWidgets);
    expect(find.text('Teamabend'), findsOneWidget);
    expect(find.text('Freitag 19 Uhr'), findsOneWidget);
    expect(find.text('Angepinnt'), findsOneWidget);
  });

  testWidgets('shows empty state when there are no notes', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: PinnwandScreen(api: _FakePinboardApi([]))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Noch keine Aushänge an der Pinnwand.'), findsOneWidget);
  });

  testWidgets('shows an error banner on API failure', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: PinnwandScreen(api: _ErrorPinboardApi())),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('nicht erreichbar'), findsOneWidget);
  });

  testWidgets('create sheet posts a new note', (tester) async {
    final api = _FakePinboardApi([]);
    await tester.pumpWidget(localizedApp(home: PinnwandScreen(api: api)));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Aushang anlegen'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField).first, 'Neuer Aushang');
    await tester.enterText(find.byType(TextField).last, 'Inhalt');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();

    expect(api.createCalls, 1);
    expect(find.text('Neuer Aushang'), findsOneWidget);
  });
}
