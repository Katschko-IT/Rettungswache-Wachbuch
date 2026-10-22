import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/security/secure_storage.dart';

/// Persists server URL (prefs) and API token (secure storage).
class SessionStore {
  SessionStore({FlutterSecureStorage? secureStorage})
    : _secure = secureStorage ?? createWachbuchSecureStorage();

  static const _urlKey = 'wachbuch_server_url';
  static const _tokenKey = 'wachbuch_api_token';
  static const _expiresKey = 'wachbuch_api_token_expires_at';

  final FlutterSecureStorage _secure;

  Future<String?> readServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_urlKey);
  }

  Future<void> writeServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_urlKey, url);
  }

  Future<String?> readToken() => _secure.read(key: _tokenKey);

  Future<DateTime?> readTokenExpiresAt() async {
    final raw = await _secure.read(key: _expiresKey);
    if (raw == null || raw.isEmpty) return null;
    return DateTime.tryParse(raw)?.toLocal();
  }

  Future<void> writeToken(String token, {DateTime? expiresAt}) async {
    await _secure.write(key: _tokenKey, value: token);
    if (expiresAt != null) {
      await _secure.write(key: _expiresKey, value: expiresAt.toUtc().toIso8601String());
    } else {
      await _secure.delete(key: _expiresKey);
    }
  }

  Future<void> clearToken() async {
    await _secure.delete(key: _tokenKey);
    await _secure.delete(key: _expiresKey);
  }

  Future<void> clearAll() async {
    await clearToken();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_urlKey);
  }

  /// Returns true when a stored expiry exists and is in the past.
  Future<bool> isTokenExpired({DateTime? now}) async {
    final expiresAt = await readTokenExpiresAt();
    if (expiresAt == null) return false;
    return !(expiresAt.isAfter(now ?? DateTime.now()));
  }
}
