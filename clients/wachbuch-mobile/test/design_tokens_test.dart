import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/theme/design_tokens.dart';

void main() {
  group('WachbuchTokens', () {
    test('priority colors are distinct and non-transparent', () {
      expect(WachbuchTokens.urgent, equals(const Color(0xFFDC2626)));
      expect(WachbuchTokens.important, equals(const Color(0xFFF59E0B)));
      expect(WachbuchTokens.normal, equals(const Color(0xFF2563EB)));
      expect(WachbuchTokens.done, equals(const Color(0xFF16A34A)));
    });

    test('priorityColor maps all aliases', () {
      expect(WachbuchTokens.priorityColor('urgent'), equals(WachbuchTokens.urgent));
      expect(WachbuchTokens.priorityColor('high'), equals(WachbuchTokens.urgent));
      expect(WachbuchTokens.priorityColor('important'), equals(WachbuchTokens.important));
      expect(WachbuchTokens.priorityColor('done'), equals(WachbuchTokens.done));
      expect(WachbuchTokens.priorityColor('unknown'), equals(WachbuchTokens.normal));
    });

    test('statusColor maps all aliases', () {
      expect(WachbuchTokens.statusColor('open'), equals(WachbuchTokens.statusOpen));
      expect(WachbuchTokens.statusColor('in_progress'), equals(WachbuchTokens.statusInProgress));
      expect(WachbuchTokens.statusColor('done'), equals(WachbuchTokens.statusDone));
    });

    test('touch target is at least 48dp', () {
      expect(WachbuchTokens.touchTarget, greaterThanOrEqualTo(48));
    });

    test('body text is at least 14sp', () {
      expect(WachbuchTokens.textBody, greaterThanOrEqualTo(14));
    });

    test('spacing tokens are positive', () {
      expect(WachbuchTokens.spaceXs, greaterThan(0));
      expect(WachbuchTokens.space2Xl, greaterThan(WachbuchTokens.spaceXl));
    });
  });
}
