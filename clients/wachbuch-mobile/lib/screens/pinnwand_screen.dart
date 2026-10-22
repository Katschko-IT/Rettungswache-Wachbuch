import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/pinboard_note.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

/// Station pinboard: short notices/announcements (`/api/v1/pinnwand/`).
class PinnwandScreen extends StatefulWidget {
  const PinnwandScreen({super.key, required this.api});

  final WachbuchApi api;

  @override
  State<PinnwandScreen> createState() => _PinnwandScreenState();
}

class _PinnwandScreenState extends State<PinnwandScreen> {
  List<PinboardNote> _notes = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final notes = await widget.api.pinboard();
      if (!mounted) return;
      setState(() {
        _notes = notes;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message.isNotEmpty
            ? error.message
            : AppLocalizations.of(context)!.pinboardLoadError;
        _loading = false;
      });
    }
  }

  Future<void> _openCreate() async {
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) => _PinboardCreateSheet(api: widget.api),
    );
    if (created == true) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AppLocalizations.of(context)!.pinboardCreated)),
        );
      }
      await _reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);
    return Scaffold(
      appBar: AppBar(title: Text(l.pinboardTitle)),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCreate,
        icon: const Icon(Icons.push_pin_outlined),
        label: Text(l.pinboardCreate),
      ),
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
    final l = AppLocalizations.of(context)!;
    if (_loading && _notes.isEmpty) {
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
          if (_notes.isEmpty && _error == null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 48),
              child: Column(
                children: [
                  Icon(Icons.push_pin_outlined,
                      size: 48, color: Theme.of(context).colorScheme.onSurfaceVariant),
                  const SizedBox(height: 12),
                  Text(l.pinboardEmpty,
                      style: Theme.of(context).textTheme.bodyLarge),
                ],
              ),
            )
          else
            for (final note in _notes) ...[
              _PinboardCard(note: note),
              const SizedBox(height: 12),
            ],
        ],
      ),
    );
  }
}

String pinboardCategoryLabel(BuildContext context, String category) {
  final l = AppLocalizations.of(context)!;
  switch (category) {
    case 'important':
      return l.pinboardCategoryImportant;
    case 'event':
      return l.pinboardCategoryEvent;
    default:
      return l.pinboardCategoryInfo;
  }
}

class _PinboardCard extends StatelessWidget {
  const _PinboardCard({required this.note});

  final PinboardNote note;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    final accent =
        note.category == 'important' ? scheme.errorContainer : scheme.secondaryContainer;
    final onAccent =
        note.category == 'important' ? scheme.onErrorContainer : scheme.onSecondaryContainer;
    return Material(
      color: scheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (note.isPinned) ...[
                  Icon(Icons.push_pin, size: 16, color: scheme.primary),
                  const SizedBox(width: 6),
                ],
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: accent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    pinboardCategoryLabel(context, note.category),
                    style: Theme.of(context)
                        .textTheme
                        .labelSmall
                        ?.copyWith(color: onAccent),
                  ),
                ),
                if (note.isPinned) ...[
                  const SizedBox(width: 8),
                  Text(l.pinboardPinned,
                      style: Theme.of(context).textTheme.labelSmall),
                ],
              ],
            ),
            const SizedBox(height: 8),
            Text(note.title,
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700)),
            if (note.body.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(note.body, style: Theme.of(context).textTheme.bodyMedium),
            ],
            const SizedBox(height: 8),
            Text(
              [
                if (note.authorName.isNotEmpty) note.authorName,
                if (note.updatedAt != null) _formatTimestamp(note.updatedAt!),
              ].join(' · '),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _PinboardCreateSheet extends StatefulWidget {
  const _PinboardCreateSheet({required this.api});

  final WachbuchApi api;

  @override
  State<_PinboardCreateSheet> createState() => _PinboardCreateSheetState();
}

class _PinboardCreateSheetState extends State<_PinboardCreateSheet> {
  final _titleController = TextEditingController();
  final _bodyController = TextEditingController();
  String _category = 'info';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _titleController.dispose();
    _bodyController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final title = _titleController.text.trim();
    final body = _bodyController.text.trim();
    if (title.isEmpty || body.isEmpty) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createPinboardNote(
        title: title,
        body: body,
        category: _category,
      );
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final insets = MediaQuery.viewInsetsOf(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + insets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l.pinboardCreate,
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          if (_error != null) ...[
            ErrorBanner(message: _error!),
            const SizedBox(height: 12),
          ],
          TextField(
            controller: _titleController,
            maxLength: 140,
            decoration: InputDecoration(labelText: l.pinboardFieldTitle),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _bodyController,
            maxLength: 2000,
            maxLines: 4,
            decoration: InputDecoration(labelText: l.pinboardFieldBody),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: _category,
            decoration: InputDecoration(labelText: l.pinboardCategory),
            items: [
              DropdownMenuItem(value: 'info', child: Text(l.pinboardCategoryInfo)),
              DropdownMenuItem(
                  value: 'important', child: Text(l.pinboardCategoryImportant)),
              DropdownMenuItem(
                  value: 'event', child: Text(l.pinboardCategoryEvent)),
            ],
            onChanged: _saving
                ? null
                : (value) => setState(() => _category = value ?? 'info'),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed:
                      _saving ? null : () => Navigator.of(context).pop(false),
                  child: Text(l.pinboardCancel),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: _saving ? null : _submit,
                  child: _saving
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Text(l.pinboardSave),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

String _formatTimestamp(DateTime date) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year}, '
      '${two(date.hour)}:${two(date.minute)}';
}
