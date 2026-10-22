import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Persists verified E2EE key fingerprints, isolated per
/// **(login account, server, colleague)** (R-020).
///
/// The trust decision ("I compared this colleague's fingerprint in person")
/// must outlive the app session *and* must never leak across accounts. Two
/// different logins on the same device and the same server therefore keep
/// separate namespaces, keyed by the authenticated user's immutable identity
/// from `/me/` (`user.id`, falling back to `user.username`) — see [accountKey].
///
/// Storage schema (v2):
/// `{ "<accountKey>": { "<baseUrl>": { "<userId>": "<fingerprint>" } } }`.
///
/// The previous un-scoped schema (`server -> userId -> fp`, no account level)
/// is deliberately **not** migrated: any legacy entry is dropped so a stale
/// verification must be re-established in person (fail closed). An empty
/// [accountKey] means "no authenticated account" and neither reads nor writes
/// anything (fail closed).
///
/// Only fingerprints are stored: no key material, no messages.
class VerifiedKeysStore {
  VerifiedKeysStore({SharedPreferences? prefs, required this.accountKey})
    : _prefs = prefs;

  /// Account-namespaced storage key.
  static const storageKey = 'wachbuch_verified_key_fingerprints_v2';

  /// Legacy, account-leaking storage key. Purged on first load.
  static const legacyStorageKey = 'wachbuch_verified_key_fingerprints';

  final SharedPreferences? _prefs;

  /// Immutable identity of the current login (captured by the caller). Once a
  /// store is built it can never be re-pointed at another account.
  final String accountKey;

  /// `accountKey -> baseUrl -> (userId -> fingerprint)`, refreshed per operation.
  final Map<String, Map<String, Map<String, String>>> _cache = {};
  // Serialize read-modify-write operations across stores in this isolate.
  static Future<void>? _operations;

  Future<T> _serialized<T>(Future<T> Function() operation) async {
    final previous = _operations;
    final done = Completer<void>();
    _operations = done.future;
    if (previous != null) await previous;
    try {
      return await operation();
    } finally {
      if (identical(_operations, done.future)) _operations = null;
      done.complete();
    }
  }

  bool _legacyHandled = false;

  bool get _scoped => accountKey.isNotEmpty;

  Future<SharedPreferences> _prefsInstance() async =>
      _prefs ?? await SharedPreferences.getInstance();

  Future<void> _ensureLoaded() async {
    final prefs = await _prefsInstance();
    _cache.clear();
    if (!_legacyHandled) {
      // Never carry legacy (un-scoped, account-leaking) verifications forward.
      if (prefs.containsKey(legacyStorageKey)) {
        await prefs.remove(legacyStorageKey);
      }
      _legacyHandled = true;
    }
    final raw = prefs.getString(storageKey);
    if (raw != null && raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map) {
          for (final account in decoded.entries) {
            final servers = account.value;
            if (servers is! Map) continue;
            final parsedServers = <String, Map<String, String>>{};
            for (final server in servers.entries) {
              final users = server.value;
              if (users is! Map) continue;
              final parsedUsers = <String, String>{};
              for (final user in users.entries) {
                final fingerprint = user.value;
                if (fingerprint is String) {
                  parsedUsers[user.key.toString()] = fingerprint;
                }
              }
              parsedServers[server.key.toString()] = parsedUsers;
            }
            _cache[account.key.toString()] = parsedServers;
          }
        }
      } catch (_) {
        // Corrupt store: treat as empty rather than failing verification.
        _cache.clear();
      }
    }
  }

  Map<String, String> _accountServer(String baseUrl) =>
      _cache[accountKey]?[baseUrl] ?? const <String, String>{};

  Future<void> _persist() async {
    final prefs = await _prefsInstance();
    if (!await prefs.setString(storageKey, jsonEncode(_cache))) {
      throw StateError('Unable to persist key verification');
    }
  }

  /// Returns the last verified fingerprint for [userId] on [baseUrl] for this
  /// account, or `null` when unknown / no account.
  Future<String?> fingerprintFor(String baseUrl, int userId) async {
    if (!_scoped) return null;
    return _serialized(() async {
      await _ensureLoaded();
      return _accountServer(baseUrl)[userId.toString()];
    });
  }

  /// Returns all verified fingerprints for this account on [baseUrl]
  /// (userId -> fingerprint).
  Future<Map<String, String>> allFor(String baseUrl) async {
    if (!_scoped) return <String, String>{};
    return _serialized(() async {
      await _ensureLoaded();
      return Map<String, String>.from(_accountServer(baseUrl));
    });
  }

  /// Marks a fingerprint as verified for this account. Returns `true` when this
  /// changed a previously stored fingerprint (i.e. the key changed since
  /// verification). Other accounts' entries are preserved on write.
  Future<bool> markVerified(
    String baseUrl,
    int userId,
    String fingerprint,
  ) async {
    if (!_scoped) return false;
    return _serialized(() async {
      await _ensureLoaded();
      final servers = _cache[accountKey] ??= <String, Map<String, String>>{};
      final users = servers[baseUrl] ??= <String, String>{};
      final key = userId.toString();
      final previous = users[key];
      users[key] = fingerprint;
      await _persist();
      return previous != null && previous != fingerprint;
    });
  }

  Future<void> remove(String baseUrl, int userId) async {
    if (!_scoped) return;
    return _serialized(() async {
      await _ensureLoaded();
      _cache[accountKey]?[baseUrl]?.remove(userId.toString());
      await _persist();
    });
  }
}
