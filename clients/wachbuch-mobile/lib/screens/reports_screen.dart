import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/report_stats.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key, required this.api});

  final WachbuchApi api;

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  WachalltagReport? _report;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final report = await widget.api.reportStats();
      if (!mounted) return;
      setState(() {
        _report = report;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final maxW = AppLayout.contentMaxWidth(MediaQuery.sizeOf(context).width);
    return Scaffold(
      appBar: AppBar(title: Text(l.reportsTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxW),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  l.reportsHint,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
                const SizedBox(height: 16),
                if (_error != null) ...[
                  ErrorBanner(message: _error!),
                  const SizedBox(height: 16),
                ],
                if (_loading && _report == null)
                  const Padding(
                    padding: EdgeInsets.all(40),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else if (_report != null) ...[
                  _Metrics(report: _report!),
                  const SizedBox(height: 24),
                  Text(
                    l.reportsByOwner,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  if (_report!.defectsByOwner.isEmpty)
                    Text(l.defectsEmpty)
                  else
                    ..._report!.defectsByOwner.map(
                      (row) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.person_outline),
                        title: Text(row.owner.isEmpty ? l.reportsNoOwner : row.owner),
                        trailing: Text(
                          '${row.count}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  Material(
                    color: Theme.of(context).colorScheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.privacy_tip_outlined,
                            color: Theme.of(context).colorScheme.onSecondaryContainer,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              l.reportsPrivacyHint,
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.onSecondaryContainer,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Metrics extends StatelessWidget {
  const _Metrics({required this.report});

  final WachalltagReport report;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final rows = <(IconData, String, String)>[
      (Icons.report_problem_outlined, l.reportsOpenDefects, '${report.openDefects}'),
      (Icons.event_busy_outlined, l.reportsOverdueDefects, '${report.overdueDefects}'),
      (Icons.checklist_outlined, l.reportsOverdueChecks, '${report.overdueChecks}'),
      (Icons.directions_car_outlined, l.reportsAssetReady, '${report.assetReadyPercent}%'),
      (Icons.key_outlined, l.reportsInventoryOut, '${report.inventoryOut}'),
      (Icons.mark_email_unread_outlined, l.reportsUnacked, '${report.unacknowledgedActiveHandovers}'),
      (Icons.history_outlined, l.reportsOldestOpen, '${report.oldestOpenDays} ${l.reportsDays}'),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 720
            ? 3
            : constraints.maxWidth >= 430
                ? 2
                : 1;
        final width = (constraints.maxWidth - 8 * (columns - 1)) / columns;
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final row in rows)
              SizedBox(
                width: width,
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: [
                        Icon(row.$1, color: Theme.of(context).colorScheme.primary),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                row.$3,
                                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                      fontWeight: FontWeight.w800,
                                    ),
                              ),
                              Text(row.$2),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}
