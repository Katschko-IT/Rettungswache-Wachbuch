import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

class ConnectivityService extends ChangeNotifier {
  ConnectivityService({Connectivity? connectivity})
      : _connectivity = connectivity ?? Connectivity();

  final Connectivity _connectivity;
  StreamSubscription<List<ConnectivityResult>>? _subscription;
  bool _isOnline = true;
  bool _disposed = false;

  bool get isOnline => _isOnline;
  bool get isOffline => !_isOnline;

  void start() {
    _subscription = _connectivity.onConnectivityChanged.listen(_onChanged);
    _connectivity.checkConnectivity().then(_onChanged);
  }

  void _onChanged(List<ConnectivityResult> results) {
    final online = !results.contains(ConnectivityResult.none);
    if (online != _isOnline) {
      _isOnline = online;
      if (!_disposed) notifyListeners();
    }
  }

  Future<bool> checkNow() async {
    final results = await _connectivity.checkConnectivity();
    _onChanged(results);
    return _isOnline;
  }

  @override
  void dispose() {
    _disposed = true;
    _subscription?.cancel();
    super.dispose();
  }
}
