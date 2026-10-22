import 'package:flutter/foundation.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/defect.dart';

/// Loads and mutates station defects (Mängel).
class DefectState extends ChangeNotifier {
  DefectState({required this.api});

  final WachbuchApi api;

  List<Defect> _items = const [];
  bool _loading = false;
  String? _error;
  ApiException? _lastError;
  bool _disposed = false;

  List<Defect> get items => _items;
  bool get loading => _loading;
  String? get error => _error;
  ApiException? get lastError => _lastError;
  bool get hasData => _items.isNotEmpty;

  int get openCount => _items.where((item) => item.isOpen).length;
  int get urgentCount => _items.where((item) => item.isUrgent).length;

  Future<void> reload() async {
    _loading = true;
    _error = null;
    _lastError = null;
    _notify();
    try {
      _items = await api.defects();
    } on ApiException catch (error) {
      _lastError = error;
      _error = error.message;
      if (WachbuchApi.isModuleUnavailable(error)) {
        _items = const [];
      }
    } catch (error) {
      _error = error.toString();
    } finally {
      _loading = false;
      _notify();
    }
  }

  Future<Defect?> create({
    required String title,
    String description = '',
    String assetRef = '',
    String priority = 'normal',
    String category = 'task',
    DateTime? dueAt,
  }) async {
    _error = null;
    _lastError = null;
    try {
      final created = await api.createDefect(
        title: title,
        description: description,
        assetRef: assetRef,
        priority: priority,
        category: category,
        dueAt: dueAt,
      );
      _items = [created, ..._items];
      _notify();
      return created;
    } on ApiException catch (error) {
      _lastError = error;
      _error = error.message;
      _notify();
      return null;
    } catch (error) {
      _error = error.toString();
      _notify();
      return null;
    }
  }

  Future<bool> setStatus(int id, String status) async {
    _error = null;
    _lastError = null;
    try {
      final updated = await api.updateDefectStatus(id, status);
      _items = [
        for (final item in _items)
          if (item.id == id) updated else item,
      ];
      _notify();
      return true;
    } on ApiException catch (error) {
      _lastError = error;
      _error = error.message;
      _notify();
      return false;
    } catch (error) {
      _error = error.toString();
      _notify();
      return false;
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
