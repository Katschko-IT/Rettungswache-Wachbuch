import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/theme/design_tokens.dart';

/// Yellow band shown while the offline demo profile is active.
class DemoBanner extends StatelessWidget {
  const DemoBanner({
    super.key,
    required this.visible,
    required this.label,
    this.serviceLabel,
  });

  final bool visible;
  final String label;
  final String? serviceLabel;

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    final text = serviceLabel == null || serviceLabel!.isEmpty
        ? label
        : '$label · $serviceLabel';
    return Material(
      color: WachbuchTokens.warning.withValues(alpha: 0.92),
      child: Semantics(
        liveRegion: true,
        label: text,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [
              const Icon(Icons.science_outlined, color: WachbuchTokens.brandDeep),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  text,
                  style: const TextStyle(
                    color: WachbuchTokens.brandDeep,
                    fontWeight: FontWeight.w600,
                    fontSize: WachbuchTokens.textBody,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
