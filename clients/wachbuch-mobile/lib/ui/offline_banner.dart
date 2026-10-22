import 'package:flutter/material.dart';

/// Visible only when the app detects a connectivity loss so the user can
/// trigger a manual retry without leaving the current screen.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({
    super.key,
    required this.visible,
    required this.onRetry,
  });

  final bool visible;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    return Material(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            const Icon(Icons.signal_wifi_off),
            const SizedBox(width: 12),
            const Expanded(child: Text('Keine Verbindung')),
            TextButton(onPressed: onRetry, child: const Text('Erneut')),
          ],
        ),
      ),
    );
  }
}
