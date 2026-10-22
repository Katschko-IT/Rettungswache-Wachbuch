/// Station defect / Mangel — see docs/SCHEMA-WACHALLTAG.md.
class Defect {
  const Defect({
    required this.id,
    required this.title,
    this.description = '',
    this.assetRef = '',
    this.priority = 'normal',
    this.status = 'open',
    this.owner = '',
    this.dueAt,
    this.dueLabel = '',
    this.category = 'task',
  });

  factory Defect.fromJson(Map<String, dynamic> json) {
    return Defect(
      id: _readInt(json['id']),
      title: (json['title'] ?? '').toString().trim(),
      description: (json['description'] ?? '').toString().trim(),
      assetRef: (json['asset_ref'] ?? json['assetRef'] ?? '').toString().trim(),
      priority: _readPriority(json['priority']),
      status: _readStatus(json['status']),
      owner: (json['owner'] ?? '').toString().trim(),
      dueAt: _readDate(json['due_at'] ?? json['dueAt']),
      dueLabel: (json['due_label'] ?? json['due'] ?? json['dueLabel'] ?? '')
          .toString()
          .trim(),
      category: _readCategory(json['category']),
    );
  }

  final int id;
  final String title;
  final String description;
  final String assetRef;
  final String priority;
  final String status;
  final String owner;
  final DateTime? dueAt;
  final String dueLabel;
  final String category;

  bool get isOpen => status != 'done';

  bool get isUrgent => priority == 'urgent' && isOpen;

  String get dueDisplay {
    if (dueLabel.isNotEmpty) return dueLabel;
    final due = dueAt;
    if (due == null) return '';
    return due.toLocal().toIso8601String();
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'description': description,
        'asset_ref': assetRef,
        'priority': priority,
        'status': status,
        'owner': owner,
        if (dueAt != null) 'due_at': dueAt!.toUtc().toIso8601String(),
        if (dueLabel.isNotEmpty) 'due_label': dueLabel,
        'category': category,
      };

  Defect copyWith({
    int? id,
    String? title,
    String? description,
    String? assetRef,
    String? priority,
    String? status,
    String? owner,
    DateTime? dueAt,
    String? dueLabel,
    String? category,
  }) {
    return Defect(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      assetRef: assetRef ?? this.assetRef,
      priority: priority ?? this.priority,
      status: status ?? this.status,
      owner: owner ?? this.owner,
      dueAt: dueAt ?? this.dueAt,
      dueLabel: dueLabel ?? this.dueLabel,
      category: category ?? this.category,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Defect && runtimeType == other.runtimeType && id == other.id;

  @override
  int get hashCode => id.hashCode;
}

String _readPriority(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  return switch (raw) {
    'urgent' || 'high' => 'urgent',
    'important' || 'medium' => 'important',
    _ => 'normal',
  };
}

String _readStatus(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  return switch (raw) {
    'in_progress' || 'active' => 'in_progress',
    'waiting' || 'blocked' => 'waiting',
    'done' || 'closed' => 'done',
    _ => 'open',
  };
}

String _readCategory(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  const allowed = {
    'vehicle',
    'material',
    'safety',
    'facility',
    'key',
    'device',
    'task',
  };
  return allowed.contains(raw) ? raw : 'task';
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
