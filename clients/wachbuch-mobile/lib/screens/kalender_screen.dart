import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/kalender_entry.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

class KalenderScreen extends StatefulWidget {
  const KalenderScreen({super.key, required this.api});

  final WachbuchApi api;

  @override
  State<KalenderScreen> createState() => _KalenderScreenState();
}

class _KalenderScreenState extends State<KalenderScreen> {
  List<KalenderEntry> _entries = const [];
  bool _loading = true;
  String? _error;
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
      final entries = await widget.api.kalender();
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _entries = entries;
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

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);
    return Scaffold(
      appBar: AppBar(title: Text(AppLocalizations.of(context)!.kalenderTitle)),
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
    if (_loading && _entries.isEmpty) {
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
          if (_entries.isEmpty && _error == null)
            _EmptyState(
              icon: Icons.event_busy,
              message: AppLocalizations.of(context)!.kalenderEmpty,
            )
          else
            for (final entry in _entries) ...[
              _KalenderCard(entry: entry),
              const SizedBox(height: 12),
            ],
        ],
      ),
    );
  }
}

class _KalenderCard extends StatelessWidget {
  const _KalenderCard({required this.entry});

  final KalenderEntry entry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 4,
              height: 56,
              decoration: BoxDecoration(
                color: scheme.primary,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.title.isNotEmpty
                        ? entry.title
                        : AppLocalizations.of(context)!.kalenderEntryFallback,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(
                        Icons.schedule,
                        size: 18,
                        color: scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          _formatRange(entry, AppLocalizations.of(context)!),
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: scheme.onSurfaceVariant,
                              ),
                        ),
                      ),
                    ],
                  ),
                  if (entry.location.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Icon(
                          Icons.place_outlined,
                          size: 18,
                          color: scheme.onSurfaceVariant,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            entry.location,
                            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                  color: scheme.onSurfaceVariant,
                                ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  if (entry.description.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Text(
                      entry.description,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _formatRange(KalenderEntry entry, AppLocalizations l10n) {
  final start = entry.startsAt;
  final end = entry.endsAt;
  if (start == null && end == null) return l10n.kalenderTimeTbd;
  if (entry.allDay) {
    return start != null ? _formatDay(start) : l10n.kalenderAllDay;
  }
  if (start != null && end != null) {
    final sameDay = _isSameDay(start, end);
    return sameDay
        ? '${_formatDay(start)}, ${_formatTime(start)} – ${_formatTime(end)} Uhr'
        : '${_formatDay(start)} ${_formatTime(start)} – ${_formatDay(end)} ${_formatTime(end)} Uhr';
  }
  if (start != null) return '${_formatDay(start)}, ${_formatTime(start)} Uhr';
  return _formatDay(end!);
}

String _formatDay(DateTime date) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year}';
}

String _formatTime(DateTime date) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.hour)}:${two(date.minute)}';
}

bool _isSameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

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
