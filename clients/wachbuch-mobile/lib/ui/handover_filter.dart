import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';

String handoverStatusLabel(Object? value, AppLocalizations l10n) =>
    _enumLabel(value, {
      'open': l10n.handoverStatusOpen,
      'in_progress': l10n.handoverStatusInProgress,
      'done': l10n.handoverStatusDone,
    }, l10n.handoverEnumUnknown);

String handoverPriorityLabel(Object? value, AppLocalizations l10n) =>
    _enumLabel(value, {
      'normal': l10n.handoverPriorityNormal,
      'important': l10n.handoverPriorityImportant,
      'urgent': l10n.handoverPriorityUrgent,
    }, l10n.handoverEnumUnknown);

String handoverCategoryLabel(Object? value, AppLocalizations l10n) =>
    _enumLabel(value, {
      'station': l10n.handoverCategoryStation,
      'vehicle': l10n.handoverCategoryVehicle,
      'material': l10n.handoverCategoryMaterial,
      'task': l10n.handoverCategoryTask,
      'safety': l10n.handoverCategorySafety,
    }, l10n.handoverEnumUnknown);

List<Map<String, dynamic>> filterHandovers(
  List<Map<String, dynamic>> items, {
  AppLocalizations? l10n,
  String query = '',
  Set<String> statuses = const {},
  Set<String> priorities = const {},
}) {
  final normalizedQuery = query.trim().toLowerCase();

  return items
      .where((item) {
        final status = _raw(item['status']);
        final priority = _raw(item['priority']);
        if (statuses.isNotEmpty && !statuses.contains(status)) {
          return false;
        }
        if (priorities.isNotEmpty && !priorities.contains(priority)) {
          return false;
        }
        if (normalizedQuery.isEmpty) {
          return true;
        }

        final searchable = [
          _raw(item['title']),
          _raw(item['category']),
          if (l10n != null)
            handoverCategoryLabel(item['category'], l10n).toLowerCase(),
          if (l10n != null)
            handoverStatusLabel(item['status'], l10n).toLowerCase(),
          if (l10n != null)
            handoverPriorityLabel(item['priority'], l10n).toLowerCase(),
        ].join(' ');
        return searchable.contains(normalizedQuery);
      })
      .toList(growable: false);
}

String _raw(Object? value) => value?.toString().trim().toLowerCase() ?? '';

String _enumLabel(Object? value, Map<String, String> labels, String unknownLabel) {
  final raw = _raw(value);
  if (raw.isEmpty) {
    return unknownLabel;
  }
  final known = labels[raw];
  if (known != null) {
    return known;
  }
  return raw
      .split(RegExp(r'[_\s-]+'))
      .where((part) => part.isNotEmpty)
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}
