/// Key / pool device checkout — see docs/SCHEMA-WACHALLTAG.md (Phase G).
class InventoryItem {
  const InventoryItem({
    required this.id,
    required this.label,
    this.kind = 'device',
    this.holder,
    this.since,
    this.sinceLabel = '',
    this.note = '',
  });

  factory InventoryItem.fromJson(Map<String, dynamic> json) {
    return InventoryItem(
      id: (json['id'] ?? '').toString().trim(),
      label: (json['label'] ?? json['name'] ?? '').toString().trim(),
      kind: _readKind(json['kind']),
      holder: _readOptionalString(json['holder'] ?? json['checked_out_by']),
      since: _readDate(json['since'] ?? json['checked_out_at']),
      sinceLabel: (json['since_label'] ?? json['since_display'] ?? '')
          .toString()
          .trim(),
      note: (json['note'] ?? '').toString().trim(),
    );
  }

  final String id;
  final String label;
  final String kind;
  final String? holder;
  final DateTime? since;
  final String sinceLabel;
  final String note;

  bool get isOut => holder != null && holder!.isNotEmpty;

  String get sinceDisplay {
    if (sinceLabel.isNotEmpty) return sinceLabel;
    final value = since;
    if (value == null) return '';
    return value.toLocal().toIso8601String();
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'label': label,
        'kind': kind,
        if (holder != null) 'holder': holder,
        if (since != null) 'since': since!.toUtc().toIso8601String(),
        if (sinceLabel.isNotEmpty) 'since_label': sinceLabel,
        if (note.isNotEmpty) 'note': note,
      };

  InventoryItem copyWith({
    String? id,
    String? label,
    String? kind,
    String? holder,
    DateTime? since,
    String? sinceLabel,
    String? note,
    bool clearHolder = false,
  }) {
    return InventoryItem(
      id: id ?? this.id,
      label: label ?? this.label,
      kind: kind ?? this.kind,
      holder: clearHolder ? null : (holder ?? this.holder),
      since: clearHolder ? null : (since ?? this.since),
      sinceLabel: clearHolder ? '' : (sinceLabel ?? this.sinceLabel),
      note: note ?? this.note,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is InventoryItem &&
          runtimeType == other.runtimeType &&
          id == other.id;

  @override
  int get hashCode => id.hashCode;
}

String _readKind(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  return switch (raw) {
    'key' => 'key',
    'vehicle' => 'vehicle',
    _ => 'device',
  };
}

String? _readOptionalString(Object? value) {
  if (value == null) return null;
  final text = value.toString().trim();
  return text.isEmpty ? null : text;
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}
