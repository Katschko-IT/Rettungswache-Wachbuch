import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/models/chat.dart';

void main() {
  group('ChatFeedItem', () {
    test('parses an encrypted envelope', () {
      final item = ChatFeedItem.fromJson({
        'id': 5,
        'author_id': 2,
        'author_name': 'Mara',
        'is_own': false,
        'is_encrypted': true,
        'ciphertext': 'CT',
        'nonce': 'N',
        'wrap': {'epk': {}, 'wrapped_key': 'iv.d'},
      });
      expect(item.isEncrypted, isTrue);
      expect(item.readable, isTrue);
      final env = item.toEnvelope();
      expect(env['ciphertext'], 'CT');
      expect(env['is_encrypted'], true);
    });

    test('encrypted without a wrap is not readable', () {
      final item = ChatFeedItem.fromJson({
        'id': 6,
        'is_encrypted': true,
        'ciphertext': 'CT',
        'nonce': 'N',
      });
      expect(item.readable, isFalse);
    });

    test('legacy plaintext keeps its body', () {
      final item = ChatFeedItem.fromJson({
        'id': 7,
        'is_encrypted': false,
        'legacy_body': 'Klartext',
      });
      expect(item.isEncrypted, isFalse);
      expect(item.readable, isTrue);
      expect(item.toEnvelope()['legacy_body'], 'Klartext');
    });
  });

  test('ChatMemberKey builds a recipient descriptor', () {
    final key = ChatMemberKey.fromJson({
      'user_id': 3,
      'label': 'Chris',
      'has_keys': true,
      'public_jwk': {'x': 'a', 'y': 'b'},
    });
    final recipient = key.toRecipient();
    expect(recipient['user_id'], 3);
    expect((recipient['public_jwk'] as Map)['x'], 'a');
  });

  test('MailSummary reads nested sender', () {
    final mail = MailSummary.fromJson({
      'id': 9,
      'sender': {'id': 4, 'name': 'Sam'},
      'created_at': '2026-08-11T10:00:00Z',
    });
    expect(mail.senderId, 4);
    expect(mail.senderName, 'Sam');
    expect(mail.createdAt, isNotNull);
  });
}
