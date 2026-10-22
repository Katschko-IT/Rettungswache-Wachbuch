import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/theme/design_tokens.dart';

Future<DemoService?> showDemoPickerSheet(BuildContext context) {
  return showModalBottomSheet<DemoService>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (context) => const DemoPickerSheet(),
  );
}

class DemoPickerSheet extends StatelessWidget {
  const DemoPickerSheet({super.key});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          24,
          8,
          24,
          24 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                l.setupDemoTitle,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                l.setupDemoSubtitle,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              ),
              const SizedBox(height: 20),
              _DemoOption(
                icon: Icons.medical_services_outlined,
                title: l.setupDemoRettungsdienst,
                subtitle: l.setupDemoRettungsdienstHint,
                accent: WachbuchTokens.brandAccent,
                onTap: () =>
                    Navigator.of(context).pop(DemoService.rettungsdienst),
              ),
              const SizedBox(height: 12),
              _DemoOption(
                icon: Icons.local_fire_department_outlined,
                title: l.setupDemoFeuerwehr,
                subtitle: l.setupDemoFeuerwehrHint,
                accent: WachbuchTokens.urgent,
                onTap: () => Navigator.of(context).pop(DemoService.feuerwehr),
              ),
              const SizedBox(height: 12),
              _DemoOption(
                icon: Icons.home_work_outlined,
                title: l.setupDemoFfw,
                subtitle: l.setupDemoFfwHint,
                accent: WachbuchTokens.important,
                onTap: () => Navigator.of(context).pop(DemoService.ffw),
              ),
              const SizedBox(height: 12),
              _DemoOption(
                icon: Icons.local_police_outlined,
                title: l.setupDemoPolizei,
                subtitle: l.setupDemoPolizeiHint,
                accent: WachbuchTokens.brandDeep,
                onTap: () => Navigator.of(context).pop(DemoService.polizei),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DemoOption extends StatelessWidget {
  const _DemoOption({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.accent,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Color accent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: accent.withValues(alpha: 0.08),
      borderRadius: BorderRadius.circular(WachbuchTokens.radiusLg),
      child: InkWell(
        borderRadius: BorderRadius.circular(WachbuchTokens.radiusLg),
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: WachbuchTokens.touchTarget),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(icon, color: accent, size: 32),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        subtitle,
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: Theme.of(context).colorScheme.onSurfaceVariant,
                            ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.chevron_right,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
