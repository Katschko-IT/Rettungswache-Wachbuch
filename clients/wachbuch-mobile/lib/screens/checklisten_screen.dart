import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/checkliste.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

class ChecklistenScreen extends StatefulWidget {
  const ChecklistenScreen({super.key, required this.api});

  final WachbuchApi api;

  @override
  State<ChecklistenScreen> createState() => _ChecklistenScreenState();
}

class _ChecklistenScreenState extends State<ChecklistenScreen> {
  List<Checklist> _lists = const [];
  bool _loading = true;
  String? _error;
  final Set<int> _busy = {};
  int _reloadGeneration = 0;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    final generation = ++_reloadGeneration;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final lists = await widget.api.checklisten();
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _lists = lists;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    } catch (error) {
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _complete(Checklist list) async {
    if (_busy.contains(list.id)) return;
    setState(() {
      _busy.add(list.id);
      _error = null;
    });
    final optimistic = list.copyWith(
      completed: true,
      completedAt: DateTime.now(),
      items: list.items
          .map((item) => ChecklistItem(id: item.id, label: item.label, checked: true, note: item.note))
          .toList(growable: false),
    );
    setState(() {
      _lists = _lists
          .map((entry) => entry.id == list.id ? optimistic : entry)
          .toList(growable: false);
    });
    try {
      final updated = await widget.api.checklisteAbschluss(list.id);
      if (!mounted) return;
      setState(() {
        _lists = _lists
            .map((entry) => entry.id == list.id
                ? optimistic.copyWith(
                    completedAt: updated.completedAt,
                    completedBy: updated.completedBy.isEmpty ? null : updated.completedBy,
                    interval: updated.interval.isEmpty ? null : updated.interval,
                    dueNext: updated.dueNext,
                    overdue: updated.overdue,
                  )
                : entry)
            .toList(growable: false);
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _lists = _lists
            .map((entry) => entry.id == list.id ? list : entry)
            .toList(growable: false);
        _error = error.message;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _lists = _lists
            .map((entry) => entry.id == list.id ? list : entry)
            .toList(growable: false);
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() => _busy.remove(list.id));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);
    return Scaffold(
      appBar: AppBar(title: Text(AppLocalizations.of(context)!.checklistenTitle)),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxW),
          child: _body(context),
        ),
      ),
    );
  }

  Widget _body(BuildContext context) {
    if (_loading && _lists.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null) ...[
            ErrorBanner(message: _error!),
            const SizedBox(height: 16),
          ],
          if (_lists.isEmpty && _error == null)
            _EmptyState(
              icon: Icons.checklist_outlined,
              message: AppLocalizations.of(context)!.checklistenEmpty,
            )
          else ...[
            if (_dueLists.isNotEmpty) ...[
              Text(
                AppLocalizations.of(context)!.checklistDueSection,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 12),
              for (final list in _dueLists) ...[
                _ChecklistCard(
                  list: list,
                  busy: _busy.contains(list.id),
                  onComplete: () => _complete(list),
                ),
                const SizedBox(height: 12),
              ],
              const SizedBox(height: 8),
            ],
            for (final list in _otherLists) ...[
              _ChecklistCard(
                list: list,
                busy: _busy.contains(list.id),
                onComplete: () => _complete(list),
              ),
              const SizedBox(height: 12),
            ],
          ],
        ],
      ),
    );
  }

  List<Checklist> get _dueLists => _lists
      .where((list) => !list.completed && (list.isDueToday || list.overdue))
      .toList();

  List<Checklist> get _otherLists => _lists
      .where((list) => list.completed || (!list.isDueToday && !list.overdue))
      .toList();
}

class _ChecklistCard extends StatelessWidget {
  const _ChecklistCard({
    required this.list,
    required this.busy,
    required this.onComplete,
  });

  final Checklist list;
  final bool busy;
  final Future<void> Function() onComplete;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  list.completed ? Icons.task_alt : Icons.checklist,
                  color: list.completed ? scheme.primary : scheme.onSurfaceVariant,
                  size: 24,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    list.title.isNotEmpty
                        ? list.title
                        : AppLocalizations.of(context)!.checklistFallback,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (list.items.isNotEmpty)
                  Chip(
                    label: Text('${list.checkedCount}/${list.items.length}'),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            if (list.isRecurring || list.overdue || list.isDueToday) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (list.interval == 'daily')
                    Chip(label: Text(AppLocalizations.of(context)!.checklistIntervalDaily)),
                  if (list.interval == 'weekly')
                    Chip(label: Text(AppLocalizations.of(context)!.checklistIntervalWeekly)),
                  if (list.interval == 'monthly')
                    Chip(label: Text(AppLocalizations.of(context)!.checklistIntervalMonthly)),
                  if (list.overdue)
                    Chip(
                      avatar: const Icon(Icons.warning_amber_rounded, size: 18),
                      label: Text(AppLocalizations.of(context)!.checklistOverdue),
                      backgroundColor: scheme.errorContainer,
                    )
                  else if (list.isDueToday)
                    Chip(
                      label: Text(AppLocalizations.of(context)!.checklistDueToday),
                    ),
                ],
              ),
            ],
            if (list.description.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                list.description,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              ),
            ],
            const SizedBox(height: 12),
            if (list.items.isEmpty)
              Text(
                AppLocalizations.of(context)!.checklistNoItems,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              )
            else
              for (final item in list.items)
                _ChecklistItemTile(item: item),
            const SizedBox(height: 8),
            if (list.completed && list.completedAt != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  AppLocalizations.of(context)!.checklistCompletedAt(
                    list.completedBy.isEmpty
                        ? _formatTimestamp(list.completedAt!)
                        : '${_formatTimestamp(list.completedAt!)} · ${list.completedBy}',
                  ),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              )
            else
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: busy ? null : onComplete,
                  icon: busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.check_circle_outline),
                  label: Text(AppLocalizations.of(context)!.checklistCompleteButton),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ChecklistItemTile extends StatelessWidget {
  const _ChecklistItemTile({required this.item});

  final ChecklistItem item;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            item.checked ? Icons.check_box : Icons.check_box_outline_blank,
            color: item.checked ? scheme.primary : scheme.onSurfaceVariant,
            size: 22,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              item.label.isNotEmpty
                  ? item.label
                  : AppLocalizations.of(context)!.checklistItemFallback,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    decoration: item.checked ? TextDecoration.lineThrough : null,
                    color: item.checked ? scheme.onSurfaceVariant : null,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

String _formatTimestamp(DateTime date) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year}, '
      '${two(date.hour)}:${two(date.minute)} Uhr';
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Column(
        children: [
          Icon(icon, size: 48, color: scheme.onSurfaceVariant),
          const SizedBox(height: 12),
          Text(message, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
    );
  }
}
