class Checklist {
  const Checklist({
    required this.id,
    required this.title,
    this.items = const [],
    this.completed = false,
    this.completedAt,
    this.completedBy = '',
    this.description = '',
    this.interval = '',
    this.dueNext,
    this.overdue = false,
  });

  /// Server (`GET /api/v1/checklisten/`) liefert `items` als Liste von
  /// Texten sowie `last_completed_at`/`last_completed_by`; ob die Liste im
  /// aktuellen Turnus erledigt ist, wird daraus und aus `interval` abgeleitet.
  factory Checklist.fromJson(Map<String, dynamic> json) {
    final dueNext = _readDate(json['due_next'] ?? json['dueNext']);
    final overdueFlag = json['overdue'] == true || json['is_overdue'] == true;
    final interval = _readInterval(json['interval']);
    final completedAt = _readDate(json['completed_at']) ??
        _readDate(json['last_completed_at']) ??
        _readDate((json['completion'] is Map
                ? (json['completion'] as Map)['created_at']
                : null));
    final overdue = overdueFlag || _isPastDue(dueNext);
    return Checklist(
      id: _readInt(json['id']),
      title: (json['title'] ?? json['name'] ?? '').toString().trim(),
      description: (json['description'] ?? '').toString().trim(),
      items: _readItems(json['items'] ?? json['tasks'] ?? const []),
      completed: json['completed'] == true ||
          json['is_completed'] == true ||
          (!overdue && _completedInCurrentCycle(completedAt, interval)),
      completedAt: completedAt,
      completedBy: (json['last_completed_by'] ?? '').toString().trim(),
      interval: interval,
      dueNext: dueNext,
      overdue: overdue,
    );
  }

  final int id;
  final String title;
  final String description;
  final List<ChecklistItem> items;
  final bool completed;
  final DateTime? completedAt;
  /// Anzeigename der Person, die zuletzt abgeschlossen hat (falls bekannt).
  final String completedBy;
  /// `daily` | `weekly` | `monthly` | empty when not recurring.
  final String interval;
  final DateTime? dueNext;
  final bool overdue;

  int get checkedCount => items.where((item) => item.checked).length;

  bool get allChecked => items.isNotEmpty && items.every((item) => item.checked);

  bool get isRecurring => interval.isNotEmpty;

  bool get isDueToday {
    if (completed) return false;
    if (overdue) return true;
    final due = dueNext;
    if (due == null) return false;
    final now = DateTime.now();
    return due.year == now.year && due.month == now.month && due.day == now.day;
  }

  Checklist copyWith({
    int? id,
    String? title,
    String? description,
    List<ChecklistItem>? items,
    bool? completed,
    DateTime? completedAt,
    String? completedBy,
    String? interval,
    DateTime? dueNext,
    bool? overdue,
  }) {
    return Checklist(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      items: items ?? this.items,
      completed: completed ?? this.completed,
      completedAt: completedAt ?? this.completedAt,
      completedBy: completedBy ?? this.completedBy,
      interval: interval ?? this.interval,
      dueNext: dueNext ?? this.dueNext,
      overdue: overdue ?? this.overdue,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Checklist && runtimeType == other.runtimeType && id == other.id;

  @override
  int get hashCode => id.hashCode;
}

class ChecklistItem {
  const ChecklistItem({
    required this.id,
    required this.label,
    this.checked = false,
    this.note = '',
  });

  factory ChecklistItem.fromJson(Map<String, dynamic> json) {
    return ChecklistItem(
      id: _readInt(json['id']),
      label: (json['label'] ?? json['title'] ?? json['text'] ?? '').toString().trim(),
      checked: json['checked'] == true || json['done'] == true,
      note: (json['note'] ?? '').toString().trim(),
    );
  }

  final int id;
  final String label;
  final bool checked;
  final String note;
}

List<ChecklistItem> _readItems(Object? value) {
  if (value is! List) return const [];
  final items = <ChecklistItem>[];
  for (final (index, item) in value.indexed) {
    if (item is Map) {
      items.add(ChecklistItem.fromJson(Map<String, dynamic>.from(item)));
    } else if (item is String && item.trim().isNotEmpty) {
      // Server liefert Prüfpunkte als reine Texte.
      items.add(ChecklistItem(id: index + 1, label: item.trim()));
    }
  }
  return List.unmodifiable(items);
}

/// Erledigt, wenn der letzte Abschluss in den laufenden Turnus fällt
/// (ohne Turnus: heute).
bool _completedInCurrentCycle(DateTime? completedAt, String interval) {
  if (completedAt == null) return false;
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final done = DateTime(completedAt.year, completedAt.month, completedAt.day);
  return switch (interval) {
    'weekly' => today.difference(done).inDays < 7,
    'monthly' => done.year == today.year && done.month == today.month,
    _ => done == today,
  };
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}

bool _isPastDue(DateTime? due) {
  if (due == null) return false;
  final today = DateTime.now();
  final dueDay = DateTime(due.year, due.month, due.day);
  final todayDay = DateTime(today.year, today.month, today.day);
  return dueDay.isBefore(todayDay);
}

String _readInterval(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  return switch (raw) {
    'daily' || 'weekly' || 'monthly' => raw,
    _ => '',
  };
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
