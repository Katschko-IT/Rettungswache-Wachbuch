import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest.dart' as tz_data;
import 'package:timezone/timezone.dart' as tz;
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/crew_notice.dart';

/// Erinnert die Besatzung, wenn die Einwirkzeit einer Desinfektion abläuft.
///
/// Der Server gibt Fahrzeuge nie automatisch frei. Die App fragt die laufenden
/// Sperren der eigenen Fahrzeuge ab und plant zur Sperrzeit eine **lokale**
/// Benachrichtigung – sie erscheint auch bei geschlossener App und ohne Netz.
/// Zusätzlich zeigt sie neue Einträge aus dem Posteingang an, sofern dieselbe
/// Sperre nicht schon lokal erinnert wurde.
class CrewReminderService {
  CrewReminderService({
    required this.api,
    required this.scheduler,
    required this.store,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  final WachbuchApi api;
  final ReminderScheduler scheduler;
  final ReminderStore store;
  final DateTime Function() _clock;
  bool _syncing = false;
  bool _permissionRequested = false;

  /// Plant fällige Erinnerungen und zeigt neue Hinweise. Fehler (offline,
  /// alter Server) lassen bestehende Planungen unverändert.
  Future<void> sync() async {
    if (_syncing) return;
    _syncing = true;
    try {
      if (!_permissionRequested) {
        _permissionRequested = true;
        await scheduler.requestPermission();
      }
      final now = _clock().toUtc();
      final scheduled = await store.readScheduled();

      final List<VehicleLock> locks;
      try {
        locks = await api.vehicleLocks();
      } on ApiException {
        return;
      }
      for (final lock in locks) {
        final at = lock.lockedUntil!;
        if (!at.isAfter(now)) continue;
        if (scheduled[lock.key] != at) {
          await scheduler.schedule(
            id: reminderIdFor(lock.key),
            title: lock.title,
            body: lock.body,
            at: at,
          );
          scheduled[lock.key] = at;
        }
      }
      // Sperren, die vor Ablauf weggefallen sind (z. B. neu desinfiziert oder
      // anders freigegeben), nicht mehr erinnern. Bereits fällige Einträge
      // bleiben stehen, damit eine angezeigte Nachricht sichtbar bleibt.
      final active = locks.map((lock) => lock.key).toSet();
      for (final entry in scheduled.entries.toList()) {
        if (!active.contains(entry.key) && entry.value.isAfter(now)) {
          await scheduler.cancel(reminderIdFor(entry.key));
          scheduled.remove(entry.key);
        }
      }
      await store.writeScheduled(_pruneScheduled(scheduled, now));

      final List<CrewNotice> notices;
      try {
        notices = await api.crewNotices();
      } on ApiException {
        return;
      }
      final shown = await store.readShown();
      for (final notice in notices) {
        if (notice.read || notice.key.isEmpty || shown.contains(notice.key)) {
          continue;
        }
        final localAt = scheduled[notice.key];
        final alreadyRemindedLocally = localAt != null && !localAt.isAfter(now);
        if (!alreadyRemindedLocally) {
          await scheduler.show(
            id: reminderIdFor(notice.key),
            title: notice.title,
            body: notice.body,
          );
        }
        shown.add(notice.key);
      }
      await store.writeShown(shown);
    } catch (error) {
      debugPrint('Erinnerungen konnten nicht synchronisiert werden: $error');
    } finally {
      _syncing = false;
    }
  }

  /// Beim Abmelden oder Serverwechsel: geplante Erinnerungen entfernen.
  Future<void> clear() async {
    final scheduled = await store.readScheduled();
    for (final key in scheduled.keys) {
      await scheduler.cancel(reminderIdFor(key));
    }
    await store.clear();
  }

  Map<String, DateTime> _pruneScheduled(Map<String, DateTime> map, DateTime now) {
    // Einträge, die länger als einen Tag zurückliegen, werden nicht mehr gebraucht.
    final cutoff = now.subtract(const Duration(days: 1));
    return {
      for (final entry in map.entries)
        if (entry.value.isAfter(cutoff)) entry.key: entry.value,
    };
  }
}

/// Stabile, positive 31-Bit-ID je Ereignisschlüssel (FNV-1a).
int reminderIdFor(String key) {
  var hash = 0x811c9dc5;
  for (final unit in key.codeUnits) {
    hash ^= unit;
    hash = (hash * 0x01000193) & 0xffffffff;
  }
  return hash & 0x7fffffff;
}

/// Abstraktion über die Plattform-Benachrichtigungen (für Tests ersetzbar).
abstract class ReminderScheduler {
  Future<void> requestPermission();
  Future<void> schedule({
    required int id,
    required String title,
    required String body,
    required DateTime at,
  });
  Future<void> show({required int id, required String title, required String body});
  Future<void> cancel(int id);
}

/// Merkt sich geplante und bereits angezeigte Erinnerungen über App-Starts hinweg.
class ReminderStore {
  ReminderStore({required this.namespace});

  /// Pro Server und Konto getrennt, damit ein Kontowechsel nichts vermischt.
  final String namespace;

  String get _scheduledKey => 'crew_reminders.$namespace.scheduled';
  String get _shownKey => 'crew_reminders.$namespace.shown';

  Future<Map<String, DateTime>> readScheduled() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_scheduledKey) ?? const [];
    final result = <String, DateTime>{};
    for (final line in raw) {
      final split = line.lastIndexOf('|');
      if (split <= 0) continue;
      final at = DateTime.tryParse(line.substring(split + 1));
      if (at != null) result[line.substring(0, split)] = at.toUtc();
    }
    return result;
  }

  Future<void> writeScheduled(Map<String, DateTime> map) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_scheduledKey, [
      for (final entry in map.entries) '${entry.key}|${entry.value.toUtc().toIso8601String()}',
    ]);
  }

  Future<Set<String>> readShown() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_shownKey) ?? const []).toSet();
  }

  Future<void> writeShown(Set<String> keys) async {
    final prefs = await SharedPreferences.getInstance();
    final list = keys.toList();
    // Nur die jüngsten Einträge behalten.
    await prefs.setStringList(_shownKey, list.length > 200 ? list.sublist(list.length - 200) : list);
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_scheduledKey);
    await prefs.remove(_shownKey);
  }
}

/// Lokale Benachrichtigungen über `flutter_local_notifications`.
///
/// Android plant „inexact while idle“: ohne Sonderberechtigung für exakte
/// Wecker, dafür kann das System die Anzeige um wenige Minuten verschieben.
class LocalNotificationScheduler implements ReminderScheduler {
  LocalNotificationScheduler({FlutterLocalNotificationsPlugin? plugin})
      : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  Future<bool>? _ready;

  static const _details = NotificationDetails(
    android: AndroidNotificationDetails(
      'vehicle_release',
      'Fahrzeugfreigabe',
      channelDescription: 'Erinnerung, wenn die Einwirkzeit einer Desinfektion abgelaufen ist.',
      importance: Importance.high,
      priority: Priority.high,
    ),
    iOS: DarwinNotificationDetails(presentAlert: true, presentSound: true),
  );

  Future<bool> _ensureReady() {
    return _ready ??= () async {
      try {
        tz_data.initializeTimeZones();
        await _plugin.initialize(
          settings: const InitializationSettings(
            android: AndroidInitializationSettings('@mipmap/ic_launcher'),
            iOS: DarwinInitializationSettings(
              requestAlertPermission: false,
              requestBadgePermission: false,
              requestSoundPermission: false,
            ),
          ),
        );
        return true;
      } on MissingPluginException {
        return false; // Tests oder nicht unterstützte Plattform
      } on PlatformException {
        return false;
      }
    }();
  }

  @override
  Future<void> requestPermission() async {
    if (!await _ensureReady()) return;
    await _guard(() async {
      await _plugin
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
      await _plugin
          .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()
          ?.requestPermissions(alert: true, sound: true);
    });
  }

  @override
  Future<void> schedule({
    required int id,
    required String title,
    required String body,
    required DateTime at,
  }) async {
    if (!await _ensureReady()) return;
    await _guard(() => _plugin.zonedSchedule(
          id: id,
          title: title,
          body: body,
          scheduledDate: tz.TZDateTime.from(at.toUtc(), tz.UTC),
          notificationDetails: _details,
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        ));
  }

  @override
  Future<void> show({required int id, required String title, required String body}) async {
    if (!await _ensureReady()) return;
    await _guard(() => _plugin.show(id: id, title: title, body: body, notificationDetails: _details));
  }

  @override
  Future<void> cancel(int id) async {
    if (!await _ensureReady()) return;
    await _guard(() => _plugin.cancel(id: id));
  }

  Future<void> _guard(Future<void> Function() action) async {
    try {
      await action();
    } on PlatformException catch (error) {
      debugPrint('Benachrichtigung nicht möglich: ${error.message}');
    }
  }
}
