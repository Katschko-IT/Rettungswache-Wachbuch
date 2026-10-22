import 'package:flutter/material.dart';

import '../theme/design_tokens.dart';

class PriorityBadge extends StatelessWidget {
  const PriorityBadge({
    super.key,
    required this.priority,
    this.compact = false,
    this.label,
  });

  final String priority;
  final bool compact;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final accent = WachbuchTokens.priorityColor(priority);
    final foreground = Theme.of(context).colorScheme.onSurface;
    final locale = Localizations.localeOf(context).languageCode;
    final text = label ?? _defaultLabel(priority, locale);

    return Semantics(
      label: text,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? WachbuchTokens.spaceSm : WachbuchTokens.spaceMd,
          vertical: compact ? WachbuchTokens.spaceXs : 6,
        ),
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.12),
          border: Border.all(color: accent.withValues(alpha: 0.72), width: 1.5),
          borderRadius: BorderRadius.circular(WachbuchTokens.radiusSm),
        ),
        constraints: BoxConstraints(minHeight: compact ? 28 : 36),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: compact ? 7 : 9,
              height: compact ? 7 : 9,
              decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
            ),
            SizedBox(
              width: compact
                  ? WachbuchTokens.spaceXs
                  : WachbuchTokens.spaceSm,
            ),
            Text(
              text,
              style: TextStyle(
                color: foreground,
                fontSize: compact
                    ? WachbuchTokens.textCaption
                    : WachbuchTokens.textBody,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _defaultLabel(String p, String locale) {
    final en = locale == 'en';
    return switch (p) {
      'urgent' || 'high' => en ? 'Urgent' : 'Dringend',
      'important' || 'medium' => en ? 'Important' : 'Wichtig',
      'done' || 'low' => en ? 'Done' : 'Erledigt',
      _ => en ? 'Normal' : 'Normal',
    };
  }
}
