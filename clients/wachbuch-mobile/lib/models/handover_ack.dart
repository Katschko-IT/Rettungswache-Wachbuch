/// Acknowledgement that a handover was read/accepted.
/// See docs/SCHEMA-WACHALLTAG.md.
class HandoverAck {
  const HandoverAck({
    required this.handoverId,
    required this.by,
    required this.at,
  });

  factory HandoverAck.fromJson(Map<String, dynamic> json) {
    return HandoverAck(
      handoverId: _readInt(json['handover_id'] ?? json['handoverId']),
      by: (json['by'] ?? json['user'] ?? '').toString().trim(),
      at: _readDate(json['at'] ?? json['created_at']) ?? DateTime.now(),
    );
  }

  final int handoverId;
  final String by;
  final DateTime at;

  Map<String, dynamic> toJson() => {
        'handover_id': handoverId,
        'by': by,
        'at': at.toUtc().toIso8601String(),
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is HandoverAck &&
          runtimeType == other.runtimeType &&
          handoverId == other.handoverId &&
          by == other.by &&
          at == other.at;

  @override
  int get hashCode => Object.hash(handoverId, by, at);
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
