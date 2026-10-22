class DefectAttachment {
  const DefectAttachment({
    required this.id,
    required this.defectId,
    required this.filename,
    required this.contentType,
    required this.size,
    this.createdAt,
    this.uploadedBy = '',
    this.downloadUrl = '',
  });

  factory DefectAttachment.fromJson(Map<String, dynamic> json) {
    return DefectAttachment(
      id: _readInt(json['id']),
      defectId: _readInt(json['defect_id'] ?? json['defectId']),
      filename: (json['filename'] ?? '').toString(),
      contentType: (json['content_type'] ?? json['contentType'] ?? '').toString(),
      size: _readInt(json['size']),
      createdAt: _readDate(json['created_at'] ?? json['createdAt']),
      uploadedBy: (json['uploaded_by'] ?? json['uploadedBy'] ?? '').toString(),
      downloadUrl: (json['download_url'] ?? json['downloadUrl'] ?? '').toString(),
    );
  }

  final int id;
  final int defectId;
  final String filename;
  final String contentType;
  final int size;
  final DateTime? createdAt;
  final String uploadedBy;
  final String downloadUrl;

  String get sizeLabel {
    if (size >= 1024 * 1024) {
      return '${(size / (1024 * 1024)).toStringAsFixed(1)} MiB';
    }
    if (size >= 1024) return '${(size / 1024).round()} KiB';
    return '$size B';
  }
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}
