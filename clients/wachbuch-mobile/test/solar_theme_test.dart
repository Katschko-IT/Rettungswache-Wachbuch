import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/theme/solar_theme.dart';

class _FakeLocationProvider implements SolarLocationProvider {
  _FakeLocationProvider(this.point);

  final GeoPoint? point;

  @override
  Future<GeoPoint?> getLocation() async => point;
}

void main() {
  const badLaer = GeoPoint(latitude: 52.1, longitude: 8.1);

  test('summer sun times for Bad Laer are plausible', () {
    final times = calculateSunTimes(DateTime.utc(2026, 6, 21), badLaer);

    expect(times, isNotNull);
    expect(times!.sunriseUtc.hour, inInclusiveRange(2, 5));
    expect(times.sunsetUtc.hour, inInclusiveRange(19, 22));
    expect(times.sunriseUtc.isBefore(times.sunsetUtc), isTrue);
  });

  test('winter sun times for Bad Laer are plausible', () {
    final times = calculateSunTimes(DateTime.utc(2026, 12, 21), badLaer);

    expect(times, isNotNull);
    expect(times!.sunriseUtc.hour, inInclusiveRange(7, 9));
    expect(times.sunsetUtc.hour, inInclusiveRange(15, 17));
  });

  test('controller selects light theme during local daylight', () async {
    final controller = SolarThemeController(
      locationProvider: _FakeLocationProvider(badLaer),
      now: () => DateTime.utc(2026, 6, 21, 12),
      scheduleTransitions: false,
    );

    await controller.refresh();

    expect(controller.mode, ThemeMode.light);
    controller.dispose();
  });

  test('controller selects dark theme during local night', () async {
    final controller = SolarThemeController(
      locationProvider: _FakeLocationProvider(badLaer),
      now: () => DateTime.utc(2026, 6, 21, 0),
      scheduleTransitions: false,
    );

    await controller.refresh();

    expect(controller.mode, ThemeMode.dark);
    controller.dispose();
  });

  test('controller falls back to system theme without location', () async {
    final controller = SolarThemeController(
      locationProvider: _FakeLocationProvider(null),
      scheduleTransitions: false,
    );

    await controller.refresh();

    expect(controller.mode, ThemeMode.system);
    controller.dispose();
  });
}
