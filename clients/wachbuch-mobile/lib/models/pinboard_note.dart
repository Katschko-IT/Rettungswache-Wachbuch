/// Read model for a station pinboard note (`/api/v1/pinnwand/`).
class PinboardNote {
  const PinboardNote({
    required this.id,
    required this.title,
    required this.body,
    required this.category,
    this.isPinned = false,
    this.authorName = '',
    this.updatedAt,
  });

  factory PinboardNote.fromJson(Map<String, dynamic> json) {
    return PinboardNote(
      id: _readInt(json['id']),
      title: (json['title'] ?? '').toString().trim(),
      body: (json['body'] ?? '').toString().trim(),
      category: (json['category'] ?? 'info').toString(),
      isPinned: json['is_pinned'] == true,
      authorName: _readAuthor(json['author']),
      updatedAt: _readDate(json['updated_at'] ?? json['created_at']),
    );
  }

  final int id;
  final String title;
  final String body;
  final String category;
  final bool isPinned;
  final String authorName;
  final DateTime? updatedAt;
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

String _readAuthor(Object? value) {
  if (value is Map) {
    return (value['display_name'] ?? value['username'] ?? '').toString().trim();
  }
  return value?.toString().trim() ?? '';
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}
