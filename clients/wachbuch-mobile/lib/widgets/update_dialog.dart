import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/services/update_service.dart';

/// Dialog widget for showing update information to users
class UpdateDialog extends StatelessWidget {
  final UpdateInfo updateInfo;
  final UpdateService updateService;
  final bool showIgnoreButton;

  const UpdateDialog({
    super.key,
    required this.updateInfo,
    required this.updateService,
    this.showIgnoreButton = true,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l = AppLocalizations.of(context)!;
    final isForced = updateInfo.forceUpdate;
    return AlertDialog(
      title: Row(
        children: [
          if (isForced)
            Icon(
              Icons.warning_amber_rounded,
              color: theme.colorScheme.error,
              size: 24,
            )
          else
            Icon(
              Icons.system_update_alt,
              color: theme.colorScheme.primary,
              size: 24,
            ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              isForced ? l.updateTitleRequired : l.updateTitleAvailable,
            ),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              l.updateCurrentVersion(updateInfo.currentVersion),
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 4),
            Text(
              l.updateNewVersion(updateInfo.latestVersion),
              style: theme.textTheme.bodyLarge?.copyWith(
                fontWeight: FontWeight.bold,
                fontFamily: 'monospace',
              ),
            ),
            if (updateInfo.releaseDate != null) ...[
              const SizedBox(height: 4),
              Text(
                l.updateReleasedAt(_formatDate(updateInfo.releaseDate!)),
                style: theme.textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 16),

            // Changelog section
            if (updateInfo.changelog.isNotEmpty) ...[
              Text(
                l.updateWhatsNew,
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              ...updateInfo.changelog.map(
                (entry) => _buildChangelogEntry(context, entry),
              ),
            ],

            // Force update warning
            if (isForced) ...[
              const SizedBox(height: 16),
              Text(
                l.updateRequiredNotice,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        if (showIgnoreButton && !isForced)
          TextButton(
            onPressed: () {
              updateService.ignoreUpdate(updateInfo.latestVersion);
              Navigator.of(context).pop();
            },
            child: Text(l.updateLater),
          ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(l.updateClose),
        ),
        if (updateInfo.downloadUrl != null &&
            updateInfo.downloadUrl!.isNotEmpty)
          ElevatedButton(
            onPressed: () {
              Navigator.of(context).pop();
              updateService.openDownloadUrl(updateInfo);
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: theme.colorScheme.onPrimary,
            ),
            child: Text(
              isForced ? l.updateNow : l.updateDownload,
            ),
          ),
      ],
    );
  }

  String _formatDate(DateTime date) {
    final y = date.year.toString().padLeft(4, '0');
    final m = date.month.toString().padLeft(2, '0');
    final d = date.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }

  static Widget buildChangelogEntry(BuildContext context, ChangelogEntry entry) {
    final theme = Theme.of(context);
    final l = AppLocalizations.of(context)!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          l.updateVersionEntry(entry.version),
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        Text(
          entry.date,
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 4),
        Padding(
          padding: const EdgeInsets.only(left: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: entry.changes.map((change) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '• ',
                    style: theme.textTheme.bodyMedium,
                  ),
                  Expanded(
                    child: Text(
                      change,
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
            )).toList(),
          ),
        ),
        const SizedBox(height: 12),
      ],
    );
  }

  Widget _buildChangelogEntry(BuildContext context, ChangelogEntry entry) =>
      buildChangelogEntry(context, entry);
}

/// Blocking dialog shown when an update is mandatory.
class ForcedUpdateDialog extends StatelessWidget {
  final UpdateInfo updateInfo;
  final UpdateService updateService;

  const ForcedUpdateDialog({
    super.key,
    required this.updateInfo,
    required this.updateService,
  });

  bool get _hasValidDownloadUrl {
    final uri = Uri.tryParse(updateInfo.downloadUrl ?? '');
    return uri != null && uri.hasScheme && uri.scheme == 'https';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l = AppLocalizations.of(context)!;
    // A forced update may only block the user while there is actually
    // something to act on. Without a valid HTTPS download URL the dialog would
    // be a dead end (no button, no way to dismiss), so it must remain
    // dismissible. We never invent a fallback URL.
    final hasAction = _hasValidDownloadUrl;
    return PopScope(
      canPop: !hasAction,
      child: AlertDialog(
        title: Row(
          children: [
            Icon(
              Icons.warning_amber_rounded,
              color: theme.colorScheme.error,
              size: 24,
            ),
            const SizedBox(width: 8),
            Flexible(child: Text(l.updateTitleRequired)),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(l.updateForceExplanation),
              const SizedBox(height: 16),
              Text(
                l.updateCurrentVersion(updateInfo.currentVersion),
                style: theme.textTheme.bodySmall,
              ),
              Text(
                l.updateRequiredVersion(updateInfo.latestVersion),
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              if (updateInfo.changelog.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  l.updateWhatsNew,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                ...updateInfo.changelog.map(
                  (entry) => UpdateDialog.buildChangelogEntry(context, entry),
                ),
              ],
            ],
          ),
        ),
        actions: [
          if (_hasValidDownloadUrl)
            ElevatedButton(
              onPressed: () {
                updateService.openDownloadUrl(updateInfo);
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: theme.colorScheme.onPrimary,
              ),
              child: Text(l.updateNow),
            )
          else
            // No usable download target: offer an explicit way out instead of
            // trapping the user in a blocking dialog.
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(l.updateClose),
            ),
        ],
      ),
    );
  }
}
