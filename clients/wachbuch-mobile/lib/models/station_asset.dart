/// Vehicle / device / key status on a station — see docs/SCHEMA-WACHALLTAG.md.
class StationAsset {
  const StationAsset({
    required this.id,
    required this.label,
    this.kind = 'device',
    this.status = 'ready',
    this.note = '',
  });

  factory StationAsset.fromJson(Map<String, dynamic> json) {
    return StationAsset(
      id: (json['id'] ?? '').toString().trim(),
      label: (json['label'] ?? json['name'] ?? '').toString().trim(),
      kind: _readKind(json['kind']),
      status: _readStatus(json['status']),
      note: (json['note'] ?? '').toString().trim(),
    );
  }

  final String id;
  final String label;
  final String kind;
  final String status;
  final String note;

  bool get isReady => status == 'ready';

  bool get needsAttention =>
      status == 'limited' || status == 'oob' || status == 'workshop';

  Map<String, dynamic> toJson() => {
        'id': id,
        'label': label,
        'kind': kind,
        'status': status,
        'note': note,
      };

  StationAsset copyWith({
    String? id,
    String? label,
    String? kind,
    String? status,
    String? note,
  }) {
    return StationAsset(
      id: id ?? this.id,
      label: label ?? this.label,
      kind: kind ?? this.kind,
      status: status ?? this.status,
      note: note ?? this.note,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is StationAsset &&
          runtimeType == other.runtimeType &&
          id == other.id;

  @override
  int get hashCode => id.hashCode;
}

String _readKind(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  return switch (raw) {
    'vehicle' => 'vehicle',
    'key' => 'key',
    _ => 'device',
  };
}

String _readStatus(Object? value) {
  final raw = value?.toString().trim().toLowerCase() ?? '';
  return switch (raw) {
    'limited' => 'limited',
    'oob' || 'out_of_order' || 'außer_betrieb' => 'oob',
    'workshop' || 'werkstatt' => 'workshop',
    _ => 'ready',
  };
}
