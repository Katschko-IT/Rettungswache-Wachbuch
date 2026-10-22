/// Vertrauen in lokal ausgestellte Serverzertifikate.
///
/// Ein Wachen-Server ohne Internet (z. B. Raspberry Pi mit eigenem WLAN) hat
/// kein Zertifikat einer öffentlichen Zertifizierungsstelle. Der Verbindungs-QR
/// des Servers enthält deshalb den SHA-256-Fingerabdruck seines Zertifikats.
/// Die App vertraut dann genau diesem Zertifikat für genau diesen Host –
/// ohne dass auf dem Handy eine Zertifizierungsstelle installiert wird.
/// Ein anderes (z. B. gefälschtes) Zertifikat wird weiterhin abgelehnt.
library;

import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final _sha256Hex = RegExp(r'^[0-9a-f]{64}$');

class ServerTrust {
  ServerTrust._();

  static const _storageKey = 'server_trust.pins';
  static const _storage = FlutterSecureStorage();
  static final Map<String, String> _pins = {};

  /// Lädt gespeicherte Fingerabdrücke (einmal beim App-Start).
  static Future<void> load() async {
    final raw = await _storage.read(key: _storageKey) ?? '';
    _pins
      ..clear()
      ..addEntries(
        raw.split('\n').where((line) => line.contains('|')).map((line) {
          final split = line.lastIndexOf('|');
          return MapEntry(line.substring(0, split), line.substring(split + 1));
        }).where((entry) => _sha256Hex.hasMatch(entry.value)),
      );
  }

  static String? pinFor(String origin) => _pins[origin];

  static Future<void> remember(String origin, String sha256Hex) async {
    final value = sha256Hex.toLowerCase();
    if (!_sha256Hex.hasMatch(value)) {
      throw ArgumentError('Ungültiger Zertifikats-Fingerabdruck.');
    }
    _pins[origin] = value;
    await _save();
  }

  static Future<void> forget(String origin) async {
    if (_pins.remove(origin) != null) await _save();
  }

  static Future<void> _save() async {
    await _storage.write(
      key: _storageKey,
      value: [for (final entry in _pins.entries) '${entry.key}|${entry.value}'].join('\n'),
    );
  }

  /// HTTP-Client für [origin]; mit hinterlegtem Fingerabdruck wird genau
  /// dieses Zertifikat akzeptiert, sonst gilt die normale Prüfung.
  static http.Client clientFor(String origin) {
    final pin = _pins[origin];
    if (pin == null) return http.Client();
    final host = Uri.parse(origin).host;
    final inner = HttpClient()
      ..badCertificateCallback = (cert, certHost, port) =>
          certificateMatches(cert.der, pin) && certHost == host;
    return IOClient(inner);
  }

  /// Vergleicht den SHA-256 des DER-kodierten Zertifikats mit [pin].
  static bool certificateMatches(List<int> der, String pin) =>
      sha256.convert(der).toString() == pin;

  /// Nur für Tests.
  static void resetForTest() => _pins.clear();
}
