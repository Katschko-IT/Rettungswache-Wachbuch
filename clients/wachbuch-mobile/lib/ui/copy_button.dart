import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class CopyIconButton extends StatelessWidget {
  const CopyIconButton({
    super.key,
    required this.text,
    this.label,
    this.iconSize = 20,
  });

  final String text;
  final String? label;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: Icon(Icons.copy_outlined, size: iconSize),
      iconSize: iconSize,
      tooltip: label ?? 'Kopieren',
      constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
      onPressed: () async {
        await Clipboard.setData(ClipboardData(text: text));
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(label != null ? '$label kopiert' : 'In Zwischenablage kopiert'),
              duration: const Duration(seconds: 2),
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      },
    );
  }
}
