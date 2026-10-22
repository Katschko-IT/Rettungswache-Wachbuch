import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/services/connectivity_service.dart';

class _FakeConnectivity implements Connectivity {
  final StreamController<List<ConnectivityResult>> _controller =
      StreamController<List<ConnectivityResult>>.broadcast();

  void emit(List<ConnectivityResult> result) {
    _controller.add(result);
  }

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => _controller.stream;

  @override
  Future<List<ConnectivityResult>> checkConnectivity() async {
    return [ConnectivityResult.wifi];
  }

  void dispose() {
    _controller.close();
  }
}

void main() {
  group('ConnectivityService', () {
    test('starts as online by default', () {
      final service = ConnectivityService();
      expect(service.isOnline, isTrue);
      expect(service.isOffline, isFalse);
      service.dispose();
    });

    test('notifies on offline transition', () async {
      final fake = _FakeConnectivity();
      final service = ConnectivityService(connectivity: fake);
      final notifications = <bool>[];
      service.addListener(() => notifications.add(service.isOnline));

      service.start();
      await Future.delayed(Duration.zero);

      fake.emit([ConnectivityResult.none]);
      await Future.delayed(Duration.zero);

      expect(service.isOnline, isFalse);
      expect(notifications, contains(false));

      service.dispose();
      fake.dispose();
    });

    test('notifies on online recovery', () async {
      final fake = _FakeConnectivity();
      final service = ConnectivityService(connectivity: fake);

      service.start();
      await Future.delayed(Duration.zero);

      fake.emit([ConnectivityResult.none]);
      await Future.delayed(Duration.zero);
      expect(service.isOnline, isFalse);

      fake.emit([ConnectivityResult.wifi]);
      await Future.delayed(Duration.zero);
      expect(service.isOnline, isTrue);

      service.dispose();
      fake.dispose();
    });

    test('does not notify when state stays the same', () async {
      final fake = _FakeConnectivity();
      final service = ConnectivityService(connectivity: fake);
      var notificationCount = 0;
      service.addListener(() => notificationCount++);

      service.start();
      await Future.delayed(Duration.zero);
      final initialCount = notificationCount;

      fake.emit([ConnectivityResult.wifi]);
      await Future.delayed(Duration.zero);

      expect(notificationCount, equals(initialCount));

      service.dispose();
      fake.dispose();
    });

    test('dispose cancels subscription', () async {
      final fake = _FakeConnectivity();
      final service = ConnectivityService(connectivity: fake);

      service.start();
      service.dispose();

      fake.emit([ConnectivityResult.none]);
      await Future.delayed(Duration.zero);

      expect(service.isOnline, isTrue);

      fake.dispose();
    });
  });
}
