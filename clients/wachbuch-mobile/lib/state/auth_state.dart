import 'package:flutter/foundation.dart';
import 'package:wachbuch_mobile/api/client.dart';

class AuthState extends ChangeNotifier {
  AuthState({required this.api});

  final WachbuchApi api;

  Map<String, dynamic>? _me;
  bool _loading = false;
  String? _error;
  ApiException? _lastError;
  bool _disposed = false;

  Map<String, dynamic>? get me => _me;
  bool get loading => _loading;
  String? get error => _error;
  ApiException? get lastError => _lastError;
  bool get hasData => _me != null;

  String stationName(String fallback) {
    final station = (_me?['membership'] as Map?)?['station'] as Map?;
    return (station?['name'] as String?) ?? fallback;
  }

  String get roleLabel {
    final membership = _me?['membership'] as Map?;
    return (membership?['role_label'] as String?) ?? '';
  }

  Map<String, dynamic> get modules {
    final station = (_me?['membership'] as Map?)?['station'] as Map?;
    final modules = station?['modules'];
    if (modules is Map<String, dynamic>) {
      return modules;
    }
    if (modules is Map) {
      return Map<String, dynamic>.from(modules);
    }
    return {};
  }

  /// Username from `/me/` (`user.username` or top-level `username`).
  String? get username {
    final nested = (_me?['user'] as Map?)?['username']?.toString().trim();
    if (nested != null && nested.isNotEmpty) return nested;
    final top = _me?['username']?.toString().trim();
    if (top != null && top.isNotEmpty) return top;
    return null;
  }

  /// Stable server user id from `/me/` (`user.id`). Immutable per login.
  int? get userId {
    final raw = (_me?['user'] as Map?)?['id'];
    if (raw is int) return raw;
    return int.tryParse(raw?.toString() ?? '');
  }

  /// Immutable local identity of the authenticated user, used to namespace
  /// per-account local state (e.g. verified key fingerprints). Prefers the
  /// stable numeric id, falls back to the username; `null` when unknown so
  /// callers fail closed instead of writing under a shared namespace.
  String? get accountKey {
    final id = userId;
    if (id != null) return id.toString();
    final name = username;
    if (name != null && name.isNotEmpty) return name;
    return null;
  }

  Future<void> reload() async {
    _loading = true;
    _error = null;
    _lastError = null;
    _notify();
    try {
      _me = await api.me();
    } on ApiException catch (error) {
      _lastError = error;
      _error = error.message;
    } catch (error) {
      _error = error.toString();
    } finally {
      _loading = false;
      _notify();
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
