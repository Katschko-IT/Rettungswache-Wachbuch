import 'package:flutter/material.dart';

import '../theme/design_tokens.dart';

class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.status,
    this.label,
  });

  final String status;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final accent = WachbuchTokens.statusColor(status);
    final foreground = Theme.of(context).colorScheme.onSurface;
    final locale = Localizations.localeOf(context).languageCode;
    final text = label ?? _defaultLabel(status, locale);

    return Semantics(
      label: text,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: WachbuchTokens.spaceMd,
          vertical: 6,
        ),
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.12),
          border: Border.all(color: accent.withValues(alpha: 0.65)),
          borderRadius: BorderRadius.circular(WachbuchTokens.radiusMd),
        ),
        constraints: const BoxConstraints(minHeight: 36),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
            ),
            const SizedBox(width: WachbuchTokens.spaceSm),
            Text(
              text,
              style: TextStyle(
                color: foreground,
                fontSize: WachbuchTokens.textBody,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _defaultLabel(String s, String locale) {
    final en = locale == 'en';
    return switch (s) {
      'open' || 'new' => en ? 'Open' : 'Offen',
      'in_progress' || 'active' => en ? 'In progress' : 'In Arbeit',
      'waiting' || 'blocked' => en ? 'Waiting' : 'Wartend',
      'done' || 'closed' => en ? 'Done' : 'Erledigt',
      _ => en ? 'Unknown' : 'Unbekannt',
    };
  }
}
