import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

class GeoPoint {
  const GeoPoint({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;
}

class SunTimes {
  const SunTimes({required this.sunriseUtc, required this.sunsetUtc});

  final DateTime sunriseUtc;
  final DateTime sunsetUtc;
}

abstract interface class SolarLocationProvider {
  Future<GeoPoint?> getLocation();
}

class DeviceSolarLocationProvider implements SolarLocationProvider {
  @override
  Future<GeoPoint?> getLocation() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return null;

      // Do not prompt here: theme is cosmetic. Fall back to system theme
      // unless the user already granted location (e.g. another feature).
      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever ||
          permission == LocationPermission.unableToDetermine) {
        return null;
      }

      final cached = await Geolocator.getLastKnownPosition();
      final position =
          cached ??
          await Geolocator.getCurrentPosition(
            locationSettings: const LocationSettings(
              accuracy: LocationAccuracy.low,
              timeLimit: Duration(seconds: 10),
            ),
          );
      return GeoPoint(
        latitude: position.latitude,
        longitude: position.longitude,
      );
    } catch (_) {
      return null;
    }
  }
}

class SolarThemeController extends ChangeNotifier {
  SolarThemeController({
    required this.locationProvider,
    DateTime Function()? now,
    this.scheduleTransitions = true,
  }) : _now = now ?? DateTime.now;

  factory SolarThemeController.device() {
    return SolarThemeController(
      locationProvider: DeviceSolarLocationProvider(),
    );
  }

  final SolarLocationProvider locationProvider;
  final DateTime Function() _now;
  final bool scheduleTransitions;

  ThemeMode _mode = ThemeMode.system;
  Timer? _timer;
  bool _disposed = false;

  ThemeMode get mode => _mode;

  Future<void> refresh() async {
    _timer?.cancel();
    final location = await locationProvider.getLocation();
    if (_disposed) return;
    if (location == null) {
      _setMode(ThemeMode.system);
      return;
    }

    final now = _now();
    final date = DateTime.utc(now.year, now.month, now.day);
    final times = calculateSunTimes(date, location);
    if (times == null) {
      _setMode(ThemeMode.system);
      return;
    }

    final nowUtc = now.toUtc();
    final daylight =
        !nowUtc.isBefore(times.sunriseUtc) && nowUtc.isBefore(times.sunsetUtc);
    _setMode(daylight ? ThemeMode.light : ThemeMode.dark);

    if (scheduleTransitions) {
      _scheduleNextRefresh(nowUtc, times, location);
    }
  }

  void _setMode(ThemeMode value) {
    if (_mode == value) return;
    _mode = value;
    notifyListeners();
  }

  void _scheduleNextRefresh(
    DateTime nowUtc,
    SunTimes today,
    GeoPoint location,
  ) {
    DateTime next;
    if (nowUtc.isBefore(today.sunriseUtc)) {
      next = today.sunriseUtc;
    } else if (nowUtc.isBefore(today.sunsetUtc)) {
      next = today.sunsetUtc;
    } else {
      final tomorrow = calculateSunTimes(
        DateTime.utc(
          today.sunriseUtc.year,
          today.sunriseUtc.month,
          today.sunriseUtc.day + 1,
        ),
        location,
      );
      if (tomorrow == null) return;
      next = tomorrow.sunriseUtc;
    }

    final delay = next.difference(nowUtc) + const Duration(seconds: 2);
    if (delay <= Duration.zero) return;
    _timer = Timer(delay, refresh);
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}

SunTimes? calculateSunTimes(DateTime date, GeoPoint location) {
  final sunrise = _calculateSolarEvent(date, location, sunrise: true);
  final sunset = _calculateSolarEvent(date, location, sunrise: false);
  if (sunrise == null || sunset == null) return null;
  return SunTimes(sunriseUtc: sunrise, sunsetUtc: sunset);
}

DateTime? _calculateSolarEvent(
  DateTime date,
  GeoPoint location, {
  required bool sunrise,
}) {
  const zenith = 90.833;
  final day = date.difference(DateTime.utc(date.year, 1, 1)).inDays + 1;
  final longitudeHour = location.longitude / 15;
  final approximateTime = day + ((sunrise ? 6 : 18) - longitudeHour) / 24;

  final meanAnomaly = 0.9856 * approximateTime - 3.289;
  var trueLongitude =
      meanAnomaly +
      1.916 * _sinDegrees(meanAnomaly) +
      0.020 * _sinDegrees(2 * meanAnomaly) +
      282.634;
  trueLongitude = _normalize(trueLongitude, 360);

  var rightAscension = _toDegrees(
    math.atan(0.91764 * math.tan(_toRadians(trueLongitude))),
  );
  rightAscension = _normalize(rightAscension, 360);
  final longitudeQuadrant = (trueLongitude / 90).floor() * 90;
  final ascensionQuadrant = (rightAscension / 90).floor() * 90;
  rightAscension += longitudeQuadrant - ascensionQuadrant;
  rightAscension /= 15;

  final sinDeclination = 0.39782 * _sinDegrees(trueLongitude);
  final cosDeclination = math.cos(math.asin(sinDeclination));
  final cosHourAngle =
      (_cosDegrees(zenith) - sinDeclination * _sinDegrees(location.latitude)) /
      (cosDeclination * _cosDegrees(location.latitude));
  if (cosHourAngle > 1 || cosHourAngle < -1) return null;

  var hourAngle = _toDegrees(math.acos(cosHourAngle));
  if (sunrise) hourAngle = 360 - hourAngle;
  hourAngle /= 15;

  final localMeanTime =
      hourAngle + rightAscension - 0.06571 * approximateTime - 6.622;
  final utcHours = _normalize(localMeanTime - longitudeHour, 24);
  final milliseconds = (utcHours * Duration.millisecondsPerHour).round();
  return DateTime.utc(
    date.year,
    date.month,
    date.day,
  ).add(Duration(milliseconds: milliseconds));
}

double _normalize(double value, double range) {
  return ((value % range) + range) % range;
}

double _toRadians(double degrees) => degrees * math.pi / 180;

double _toDegrees(double radians) => radians * 180 / math.pi;

double _sinDegrees(double degrees) => math.sin(_toRadians(degrees));

double _cosDegrees(double degrees) => math.cos(_toRadians(degrees));
