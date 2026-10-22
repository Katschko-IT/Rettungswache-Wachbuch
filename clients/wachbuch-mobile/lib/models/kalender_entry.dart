class KalenderEntry {
  const KalenderEntry({
    required this.id,
    required this.title,
    this.description = '',
    this.startsAt,
    this.endsAt,
    this.allDay = false,
    this.location = '',
  });

  factory KalenderEntry.fromJson(Map<String, dynamic> json) {
    return KalenderEntry(
      id: _readInt(json['id']),
      title: (json['title'] ?? '').toString().trim(),
      description: (json['description'] ?? json['summary'] ?? '').toString().trim(),
      startsAt: _readDate(json['starts_at'] ?? json['start']),
      endsAt: _readDate(json['ends_at'] ?? json['end']),
      allDay: json['all_day'] == true || json['allday'] == true,
      location: (json['location'] ?? '').toString().trim(),
    );
  }

  final int id;
  final String title;
  final String description;
  final DateTime? startsAt;
  final DateTime? endsAt;
  final bool allDay;
  final String location;

  KalenderEntry copyWith({
    int? id,
    String? title,
    String? description,
    DateTime? startsAt,
    DateTime? endsAt,
    bool? allDay,
    String? location,
  }) {
    return KalenderEntry(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      startsAt: startsAt ?? this.startsAt,
      endsAt: endsAt ?? this.endsAt,
      allDay: allDay ?? this.allDay,
      location: location ?? this.location,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is KalenderEntry && runtimeType == other.runtimeType && id == other.id;

  @override
  int get hashCode => id.hashCode;
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  final parsed = DateTime.tryParse(value.toString());
  return parsed?.toLocal();
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
