/// Read models for E2EE messaging (`/api/v1/chat/*`, `/api/v1/post/*`).
///
/// The client never trusts the server with plaintext: message bodies stay as
/// ciphertext envelopes here and are only decrypted locally via `crypto/e2ee`.
library;

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}

class ChatMemberKey {
  const ChatMemberKey({
    required this.userId,
    required this.label,
    required this.hasKeys,
    this.publicJwk,
    this.fingerprint,
  });

  factory ChatMemberKey.fromJson(Map<String, dynamic> json) {
    final jwk = json['public_jwk'];
    return ChatMemberKey(
      userId: _readInt(json['user_id']),
      label: (json['label'] ?? '').toString(),
      hasKeys: json['has_keys'] == true,
      publicJwk: jwk is Map ? Map<String, dynamic>.from(jwk) : null,
      fingerprint: json['fingerprint'] is String &&
              (json['fingerprint'] as String).isNotEmpty
          ? json['fingerprint'] as String
          : null,
    );
  }

  final int userId;
  final String label;
  final bool hasKeys;
  final Map<String, dynamic>? publicJwk;
  final String? fingerprint;

  /// Recipient descriptor consumed by `E2ee.encryptForRecipients`.
  Map<String, dynamic> toRecipient() => {'user_id': userId, 'public_jwk': publicJwk};
}

class ChatFeedItem {
  const ChatFeedItem({
    required this.id,
    required this.authorId,
    required this.authorName,
    required this.isOwn,
    required this.isEncrypted,
    this.createdAt,
    this.ciphertext,
    this.nonce,
    this.wrap,
    this.legacyBody,
  });

  factory ChatFeedItem.fromJson(Map<String, dynamic> json) {
    final wrap = json['wrap'];
    return ChatFeedItem(
      id: _readInt(json['id']),
      authorId: json['author_id'] == null ? null : _readInt(json['author_id']),
      authorName: (json['author_name'] ?? '').toString(),
      isOwn: json['is_own'] == true,
      isEncrypted: json['is_encrypted'] != false,
      createdAt: _readDate(json['created_at']),
      ciphertext: json['ciphertext']?.toString(),
      nonce: json['nonce']?.toString(),
      wrap: wrap is Map ? Map<String, dynamic>.from(wrap) : null,
      legacyBody: json['legacy_body']?.toString(),
    );
  }

  final int id;
  final int? authorId;
  final String authorName;
  final bool isOwn;
  final bool isEncrypted;
  final DateTime? createdAt;
  final String? ciphertext;
  final String? nonce;
  final Map<String, dynamic>? wrap;
  final String? legacyBody;

  /// Envelope map consumed by `E2ee.decryptEnvelope`.
  Map<String, dynamic> toEnvelope() => {
        'is_encrypted': isEncrypted,
        'ciphertext': ciphertext,
        'nonce': nonce,
        'wrap': wrap,
        'legacy_body': legacyBody,
      };

  /// True when the viewer has a key wrap and can decrypt the message.
  bool get readable => !isEncrypted || wrap != null;
}

class ChatConversation {
  const ChatConversation({
    required this.id,
    required this.otherId,
    required this.otherName,
    this.updatedAt,
  });

  factory ChatConversation.fromJson(Map<String, dynamic> json) => ChatConversation(
        id: _readInt(json['id']),
        otherId: _readInt(json['other_id']),
        otherName: (json['other_name'] ?? '').toString(),
        updatedAt: _readDate(json['updated_at']),
      );

  final int id;
  final int otherId;
  final String otherName;
  final DateTime? updatedAt;
}

class PrivateHome {
  const PrivateHome({required this.conversations, required this.colleagues});
  final List<ChatConversation> conversations;
  final List<ChatMemberKey> colleagues;
}

class PrivateThreadData {
  const PrivateThreadData({
    required this.otherId,
    required this.otherName,
    required this.peerKeys,
    required this.messages,
  });
  final int otherId;
  final String otherName;
  final List<ChatMemberKey> peerKeys;
  final List<ChatFeedItem> messages;
}

class MailSummary {
  const MailSummary({
    required this.id,
    required this.senderId,
    required this.senderName,
    this.createdAt,
  });

  factory MailSummary.fromJson(Map<String, dynamic> json) {
    final sender = json['sender'];
    final senderMap = sender is Map ? Map<String, dynamic>.from(sender) : const {};
    return MailSummary(
      id: _readInt(json['id']),
      senderId: _readInt(senderMap['id']),
      senderName: (senderMap['name'] ?? '').toString(),
      createdAt: _readDate(json['created_at']),
    );
  }

  final int id;
  final int senderId;
  final String senderName;
  final DateTime? createdAt;
}

class MailInboxData {
  const MailInboxData({
    required this.received,
    required this.sent,
    required this.colleagues,
  });
  final List<MailSummary> received;
  final List<MailSummary> sent;
  final List<ChatMemberKey> colleagues;
}

class MailRecipientStatus {
  const MailRecipientStatus({required this.id, required this.name, required this.read});

  factory MailRecipientStatus.fromJson(Map<String, dynamic> json) => MailRecipientStatus(
        id: _readInt(json['id']),
        name: (json['name'] ?? '').toString(),
        read: json['read'] == true,
      );

  final int id;
  final String name;
  final bool read;
}

class MailDetailData {
  const MailDetailData({required this.envelope, required this.recipients});
  final ChatFeedItem envelope;
  final List<MailRecipientStatus> recipients;
}

class ChatGroupSummary {
  const ChatGroupSummary({
    required this.id,
    required this.name,
    required this.memberCount,
    this.updatedAt,
  });

  factory ChatGroupSummary.fromJson(Map<String, dynamic> json) => ChatGroupSummary(
        id: _readInt(json['id']),
        name: (json['name'] ?? '').toString(),
        memberCount: _readInt(json['member_count']),
        updatedAt: _readDate(json['updated_at']),
      );

  final int id;
  final String name;
  final int memberCount;
  final DateTime? updatedAt;
}

class GroupThreadData {
  const GroupThreadData({
    required this.id,
    required this.name,
    required this.isManager,
    required this.members,
    required this.messages,
  });

  final int id;
  final String name;
  final bool isManager;
  final List<ChatMemberKey> members;
  final List<ChatFeedItem> messages;
}
