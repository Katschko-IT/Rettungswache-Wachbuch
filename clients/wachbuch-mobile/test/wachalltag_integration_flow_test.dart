import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/defect.dart';
import 'package:wachbuch_mobile/models/handover_ack.dart';
import 'package:wachbuch_mobile/screens/home_shell.dart';

import 'test_localization.dart';

class _IntegrationApi extends WachbuchApi {
  _IntegrationApi()
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  String? createdTitle;
  String? createdDescription;
  String? createdPriority;

  @override
  Future<Map<String, dynamic>> me() async => {
        'user': {'username': 'michael'},
        'membership': {
          'role_label': 'Schichtleitung',
          'station': {
            'name': 'Rettungswache Test',
            'modules': {
              'defects': true,
              'reports': true,
              'assets': false,
              'inventory': false,
            },
          },
        },
      };

  @override
  Future<List<Map<String, dynamic>>> handovers() async => [
        {
          'id': 1,
          'title': 'Defi-Akku prüfen',
          'details': 'Kapazität nach Einsatz kontrollieren.',
          'priority': 'urgent',
          'status': 'open',
          'category': 'material',
        },
      ];

  @override
  Future<Map<String, dynamic>> handoverDetail(int id) async => {
        'id': id,
        'title': 'Defi-Akku prüfen',
        'details': 'Kapazität nach Einsatz kontrollieren.',
        'priority': 'urgent',
        'status': 'open',
        'category': 'material',
      };

  @override
  Future<List<HandoverAck>> handoverAcks(int id) async => const [];

  @override
  Future<Defect> createDefect({
    required String title,
    String description = '',
    String assetRef = '',
    String priority = 'normal',
    String category = 'task',
    String? owner,
    DateTime? dueAt,
  }) async {
    createdTitle = title;
    createdDescription = description;
    createdPriority = priority;
    return Defect(
      id: 99,
      title: title,
      description: description,
      priority: priority,
      category: category,
    );
  }
}

void main() {
  testWidgets('reports are reachable and handover can become a real defect', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _IntegrationApi();
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

    expect(find.byKey(const Key('module-tile-reports')), findsOneWidget);

    await tester.tap(find.text('Übergaben'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Defi-Akku prüfen'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('handover-to-defect')), findsOneWidget);
    await tester.tap(find.byKey(const Key('handover-to-defect')));
    await tester.pumpAndSettle();

    expect(api.createdTitle, 'Defi-Akku prüfen');
    expect(api.createdDescription, 'Kapazität nach Einsatz kontrollieren.');
    expect(api.createdPriority, 'urgent');
  });
}
