/// Parse and normalize Wachbuch server addresses from typed input or QR payloads.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:wachbuch_mobile/api/client.dart';

const _wachbuchSchemes = {'wachbuch', 'wachbuch-internal'};
const _linkKeys = {'url', 'pin', 'pair'};
final _pinPattern = RegExp(r'^sha256/([0-9a-f]{64})$');

/// Inhalt eines Verbindungs-QR-Codes oder Wachbuch-Links.
class ServerLink {
  const ServerLink({required this.url, this.certSha256, this.pairingCode});

  /// Server-Origin, z. B. `https://10.42.0.1`.
  final String url;

  /// SHA-256 des lokalen Serverzertifikats (Raspberry Pi ohne öffentliches
  /// Zertifikat), sonst `null`.
  final String? certSha256;

  /// Einmaliger Kopplungscode vom Wachenterminal (120 s gültig), sonst `null`.
  final String? pairingCode;
}

/// Extracts a Wachbuch server origin from typed text or QR content.
///
/// Accepted forms (Google Play / Nextcloud-style self-host setup):
/// - `https://wache.example.org`
/// - `wache.example.org` (https assumed)
/// - `https://wache.example.org/anmelden/` (path stripped to origin)
/// - JSON: `{"url":"https://…"}` or `{"server":"https://…"}`
/// - `wachbuch://connect?url=https%3A%2F%2F…`
/// - `wachbuch-internal://connect?url=https%3A%2F%2F…`
String parseServerAddress(String raw, {bool allowInsecure = kDebugMode}) =>
    parseServerLink(raw, allowInsecure: allowInsecure).url;

/// Wie [parseServerAddress], liefert zusätzlich Zertifikats-Fingerabdruck
/// (`pin=sha256/<hex>`) und Kopplungscode (`pair=…`) aus Wachbuch-Links.
ServerLink parseServerLink(String raw, {bool allowInsecure = kDebugMode}) {
  String? certSha256;
  String? pairingCode;
  var value = raw.trim();
  if (value.isEmpty) {
    throw ArgumentError('Adresse fehlt.');
  }

  if (value.startsWith('{')) {
    try {
      final decoded = jsonDecode(value);
      if (decoded is! Map) {
        throw ArgumentError('Ungültiger QR-Code.');
      }
      final url = decoded['url'] ?? decoded['server'] ?? decoded['baseUrl'];
      if (url is! String || url.trim().isEmpty) {
        throw ArgumentError('Server-Adresse fehlt im QR-Code.');
      }
      value = url.trim();
    } on FormatException {
      throw ArgumentError('Ungültiger QR-Code.');
    }
  }

  final candidate = Uri.tryParse(value);
  if (candidate == null) {
    throw ArgumentError('Ungültige Server-Adresse.');
  }
  if (candidate.scheme.isNotEmpty &&
      candidate.scheme != 'http' &&
      candidate.scheme != 'https' &&
      !_wachbuchSchemes.contains(candidate.scheme)) {
    throw ArgumentError('Nur HTTP- oder HTTPS-Adressen werden unterstützt.');
  }

  if (_wachbuchSchemes.contains(candidate.scheme)) {
    if (candidate.host != 'connect' || candidate.path.isNotEmpty) {
      throw ArgumentError('Ungültiger Wachbuch-Link.');
    }
    final params = candidate.queryParametersAll;
    if (params.keys.any((key) => !_linkKeys.contains(key)) ||
        params['url']?.length != 1 ||
        params.values.any((values) => values.length != 1)) {
      throw ArgumentError('Ungültiger Wachbuch-Link.');
    }
    final pin = candidate.queryParameters['pin'];
    if (pin != null) {
      final match = _pinPattern.firstMatch(pin.toLowerCase());
      if (match == null) {
        throw ArgumentError('Ungültiger Zertifikats-Fingerabdruck im Wachbuch-Link.');
      }
      certSha256 = match.group(1);
    }
    final pair = candidate.queryParameters['pair'];
    if (pair != null) {
      if (!RegExp(r'^[A-Za-z0-9_-]{16,64}$').hasMatch(pair)) {
        throw ArgumentError('Ungültiger Kopplungscode im Wachbuch-Link.');
      }
      pairingCode = pair;
    }
    final url = candidate.queryParameters['url'];
    if (url == null || url.trim().isEmpty) {
      throw ArgumentError('Server-Adresse fehlt im Wachbuch-Link.');
    }
    value = url.trim();
  }

  try {
    final normalized = normalizeServerUrl(value);
    final uri = Uri.parse(normalized);
    if ((uri.scheme != 'http' && uri.scheme != 'https') || uri.host.isEmpty) {
      throw ArgumentError('Ungültige Server-Adresse.');
    }
    if (uri.userInfo.isNotEmpty) {
      throw ArgumentError('Anmeldedaten dürfen nicht Teil der Server-Adresse sein.');
    }
    if (uri.scheme == 'http' && !allowInsecure) {
      throw ArgumentError('Für diese App ist eine HTTPS-Adresse erforderlich.');
    }
    final port = uri.hasPort ? ':${uri.port}' : '';
    return ServerLink(
      url: '${uri.scheme}://${uri.host}$port',
      certSha256: certSha256,
      pairingCode: pairingCode,
    );
  } on FormatException {
    throw ArgumentError('Ungültige Server-Adresse.');
  }
}
