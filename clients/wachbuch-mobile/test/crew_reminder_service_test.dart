import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/services/crew_reminder_service.dart';

class FakeScheduler implements ReminderScheduler {
  final scheduled = <int, DateTime>{};
  final shown = <int, String>{};
  final cancelled = <int>[];
  var permissionRequests = 0;

  @override
  Future<void> requestPermission() async => permissionRequests++;

  @override
  Future<void> schedule({
    required int id,
    required String title,
    required String body,
    required DateTime at,
  }) async =>
      scheduled[id] = at;

  @override
  Future<void> show({required int id, required String title, required String body}) async =>
      shown[id] = title;

  @override
  Future<void> cancel(int id) async {
    cancelled.add(id);
    scheduled.remove(id);
  }
}

/// Antwortformen von core/api/notifications.py im Server-Repository.
class FakeServer {
  List<Map<String, dynamic>> locks = [];
  List<Map<String, dynamic>> notices = [];
  int statusForLocks = 200;

  http.Client get client => MockClient((request) async {
        if (request.url.path == '/api/v1/fahrzeuge/sperren/') {
          if (statusForLocks != 200) return http.Response('{}', statusForLocks);
          return http.Response(jsonEncode({'ok': true, 'results': locks}), 200);
        }
        if (request.url.path == '/api/v1/benachrichtigungen/') {
          return http.Response(
            jsonEncode({'ok': true, 'unread_count': notices.length, 'results': notices}),
            200,
          );
        }
        return http.Response('{}', 404);
      });
}

void main() {
  final now = DateTime.utc(2026, 10, 22, 18, 0);
  late FakeServer server;
  late FakeScheduler scheduler;

  CrewReminderService service() => CrewReminderService(
        api: WachbuchApi(baseUrl: 'https://wache.test', token: 'wb_x', client: server.client),
        scheduler: scheduler,
        store: ReminderStore(namespace: 'test'),
        clock: () => now,
      );

  Map<String, dynamic> lock(String key, DateTime until) => {
        'vehicle_id': 2,
        'call_sign': 'RTW 2',
        'locked_until': until.toIso8601String(),
        'key': key,
        'title': 'RTW 2: Einwirkzeit abgelaufen',
        'body': 'Bitte Fahrzeug prüfen und den Status selbst freigeben.',
      };

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    server = FakeServer();
    scheduler = FakeScheduler();
  });

  test('schedules a local reminder at the end of the contact time', () async {
    final until = now.add(const Duration(minutes: 12));
    server.locks = [lock('vehicle_ready:2:a', until)];
    await service().sync();

    expect(scheduler.scheduled[reminderIdFor('vehicle_ready:2:a')], until);
    expect(scheduler.permissionRequests, 1);
    expect(scheduler.shown, isEmpty);
  });

  test('cancels a pending reminder when the lock disappears early', () async {
    server.locks = [lock('vehicle_ready:2:a', now.add(const Duration(minutes: 12)))];
    await service().sync();
    server.locks = [];
    await service().sync();

    expect(scheduler.cancelled, [reminderIdFor('vehicle_ready:2:a')]);
  });

  test('shows a server notice once if it was not reminded locally', () async {
    server.notices = [
      {'id': 7, 'key': 'vehicle_ready:2:b', 'title': 'RTW 2: Einwirkzeit abgelaufen', 'body': 'x', 'read': false},
    ];
    await service().sync();
    await service().sync();

    expect(scheduler.shown.length, 1);
    expect(scheduler.shown.values.single, contains('RTW 2'));
  });

  test('does not repeat a notice that the local reminder already showed', () async {
    // Erster Lauf vor Ablauf: Erinnerung geplant.
    final until = now.subtract(const Duration(minutes: 1));
    final store = ReminderStore(namespace: 'test');
    await store.writeScheduled({'vehicle_ready:2:c': until});
    server.notices = [
      {'id': 8, 'key': 'vehicle_ready:2:c', 'title': 'RTW 2', 'body': 'x', 'read': false},
    ];
    await service().sync();

    expect(scheduler.shown, isEmpty);
  });

  test('older servers without the endpoint are handled quietly', () async {
    server.statusForLocks = 404;
    await service().sync();

    expect(scheduler.scheduled, isEmpty);
    expect(scheduler.shown, isEmpty);
  });

  test('clear removes all planned reminders', () async {
    server.locks = [lock('vehicle_ready:2:d', now.add(const Duration(minutes: 5)))];
    final reminders = service();
    await reminders.sync();
    await reminders.clear();

    expect(scheduler.scheduled, isEmpty);
    expect(await ReminderStore(namespace: 'test').readScheduled(), isEmpty);
  });

  test('reminder ids are stable and positive', () {
    expect(reminderIdFor('vehicle_ready:2:a'), reminderIdFor('vehicle_ready:2:a'));
    expect(reminderIdFor('vehicle_ready:2:a'), isNot(reminderIdFor('vehicle_ready:3:a')));
    expect(reminderIdFor('x') >= 0, isTrue);
  });
}
