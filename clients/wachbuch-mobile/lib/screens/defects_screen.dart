import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/defect.dart';
import 'package:wachbuch_mobile/models/defect_attachment.dart';
import 'package:wachbuch_mobile/state/defect_state.dart';
import 'package:wachbuch_mobile/theme/design_tokens.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';
import 'package:wachbuch_mobile/ui/priority_badge.dart';
import 'package:wachbuch_mobile/ui/status_chip.dart';

/// Persistent station defects: list, create, status workflow and photos.
class DefectsScreen extends StatefulWidget {
  const DefectsScreen({super.key, required this.api});

  final WachbuchApi api;

  @override
  State<DefectsScreen> createState() => _DefectsScreenState();
}

class _DefectsScreenState extends State<DefectsScreen> {
  late final DefectState _state;
  String? _statusFilter;

  @override
  void initState() {
    super.initState();
    _state = DefectState(api: widget.api)..reload();
  }

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  List<Defect> get _visible {
    final filter = _statusFilter;
    if (filter == null) return _state.items;
    return _state.items
        .where((item) => item.status == filter)
        .toList(growable: false);
  }

  Future<void> _openCreate() async {
    final draft = await showModalBottomSheet<_DefectDraft>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _DefectCreateSheet(),
    );
    if (draft == null || !mounted) return;
    final created = await _state.create(
      title: draft.title,
      description: draft.description,
      assetRef: draft.assetRef,
      priority: draft.priority,
      category: draft.category,
      dueAt: draft.dueAt,
    );
    if (!mounted) return;
    if (created == null) {
      final l = AppLocalizations.of(context)!;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_state.error ?? l.defectCreateFailed)),
      );
    }
  }

  Future<void> _openDetail(Defect defect) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _DefectDetailSheet(
        api: widget.api,
        defect: defect,
        onSetStatus: _state.setStatus,
      ),
    );
  }

  String _statusLabel(AppLocalizations l, String status) {
    return switch (status) {
      'in_progress' => l.handoverStatusInProgress,
      'waiting' => l.defectStatusWaiting,
      'done' => l.handoverStatusDone,
      _ => l.handoverStatusOpen,
    };
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);

    return Scaffold(
      appBar: AppBar(
        title: Text(l.defectsTitle),
        actions: [
          IconButton(
            tooltip: l.defectAdd,
            onPressed: _openCreate,
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCreate,
        icon: const Icon(Icons.add),
        label: Text(l.defectAdd),
      ),
      body: ListenableBuilder(
        listenable: _state,
        builder: (context, _) {
          final items = _visible;
          return RefreshIndicator(
            onRefresh: _state.reload,
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: maxW),
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
                  children: [
                    Text(
                      l.defectsHint,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final status in const [
                          'open',
                          'in_progress',
                          'waiting',
                          'done',
                        ])
                          FilterChip(
                            label: Text(_statusLabel(l, status)),
                            selected: _statusFilter == status,
                            onSelected: (selected) {
                              setState(() {
                                _statusFilter = selected ? status : null;
                              });
                            },
                          ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (_state.error != null) ...[
                      ErrorBanner(message: _state.error!),
                      const SizedBox(height: 12),
                    ],
                    if (_state.loading && !_state.hasData)
                      const Padding(
                        padding: EdgeInsets.all(32),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    else if (items.isEmpty)
                      Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(l.defectsEmpty),
                      )
                    else
                      ...items.map(
                        (defect) => Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: _DefectCard(
                            defect: defect,
                            onTap: () => _openDetail(defect),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _DefectDraft {
  const _DefectDraft({
    required this.title,
    required this.description,
    required this.assetRef,
    required this.priority,
    required this.category,
    this.dueAt,
  });

  final String title;
  final String description;
  final String assetRef;
  final String priority;
  final String category;
  final DateTime? dueAt;
}

class _DefectCreateSheet extends StatefulWidget {
  const _DefectCreateSheet();

  @override
  State<_DefectCreateSheet> createState() => _DefectCreateSheetState();
}

class _DefectCreateSheetState extends State<_DefectCreateSheet> {
  final _formKey = GlobalKey<FormState>();
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _asset = TextEditingController();
  String _priority = 'normal';
  String _category = 'task';
  DateTime? _dueAt;

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    _asset.dispose();
    super.dispose();
  }

  Future<void> _pickDue() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: DateTime(now.year + 3),
      initialDate: _dueAt ?? now,
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_dueAt ?? now),
    );
    if (time == null || !mounted) return;
    setState(() {
      _dueAt = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    });
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.of(context).pop(
      _DefectDraft(
        title: _title.text.trim(),
        description: _description.text.trim(),
        assetRef: _asset.text.trim(),
        priority: _priority,
        category: _category,
        dueAt: _dueAt,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final locale = Localizations.localeOf(context).languageCode;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          24,
          0,
          24,
          24 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  l.defectCreateTitle,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _title,
                  maxLength: 160,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: l.defectTitleLabel,
                    border: const OutlineInputBorder(),
                  ),
                  validator: (value) => value == null || value.trim().isEmpty
                      ? l.defectTitleLabel
                      : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _description,
                  minLines: 3,
                  maxLines: 6,
                  maxLength: 3000,
                  decoration: InputDecoration(
                    labelText: l.defectDescriptionLabel,
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _asset,
                  maxLength: 160,
                  decoration: InputDecoration(
                    labelText: l.defectAssetLabel,
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _priority,
                  decoration: InputDecoration(
                    labelText: l.defectPriorityLabel,
                    border: const OutlineInputBorder(),
                  ),
                  items: const ['normal', 'important', 'urgent']
                      .map(
                        (value) => DropdownMenuItem(
                          value: value,
                          child: Text(_priorityLabel(l, value)),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => _priority = value ?? 'normal'),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _category,
                  decoration: InputDecoration(
                    labelText: l.defectCategoryLabel,
                    border: const OutlineInputBorder(),
                  ),
                  items: const [
                    'task',
                    'vehicle',
                    'material',
                    'safety',
                    'facility',
                    'device',
                    'key',
                  ]
                      .map(
                        (value) => DropdownMenuItem(
                          value: value,
                          child: Text(_categoryLabel(l, locale, value)),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => _category = value ?? 'task'),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _pickDue,
                  icon: const Icon(Icons.event_outlined),
                  label: Text(
                    _dueAt == null
                        ? l.defectDueLabel
                        : '${l.defectDueLabel}: ${MaterialLocalizations.of(context).formatMediumDate(_dueAt!)} · ${MaterialLocalizations.of(context).formatTimeOfDay(TimeOfDay.fromDateTime(_dueAt!))}',
                  ),
                ),
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: _submit,
                  child: Text(l.commonSave),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DefectDetailSheet extends StatefulWidget {
  const _DefectDetailSheet({
    required this.api,
    required this.defect,
    required this.onSetStatus,
  });

  final WachbuchApi api;
  final Defect defect;
  final Future<bool> Function(int id, String status) onSetStatus;

  @override
  State<_DefectDetailSheet> createState() => _DefectDetailSheetState();
}

class _DefectDetailSheetState extends State<_DefectDetailSheet> {
  late Defect _defect;
  List<DefectAttachment> _attachments = const [];
  bool _attachmentsLoading = true;
  bool _photoBusy = false;
  String? _attachmentError;

  @override
  void initState() {
    super.initState();
    _defect = widget.defect;
    _reloadAttachments();
  }

  Future<void> _reloadAttachments() async {
    try {
      final attachments = await widget.api.defectAttachments(_defect.id);
      if (!mounted) return;
      setState(() {
        _attachments = attachments;
        _attachmentsLoading = false;
        _attachmentError = null;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _attachmentsLoading = false;
        _attachmentError = error.message;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _attachmentsLoading = false;
        _attachmentError = error.toString();
      });
    }
  }

  Future<void> _setStatus(String status) async {
    final ok = await widget.onSetStatus(_defect.id, status);
    if (!mounted) return;
    if (ok) {
      setState(() => _defect = _defect.copyWith(status: status));
    }
  }

  Future<ImageSource?> _choosePhotoSource() {
    final l = AppLocalizations.of(context)!;
    return showModalBottomSheet<ImageSource>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: Text(l.defectTakePhoto),
              onTap: () => Navigator.of(context).pop(ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: Text(l.defectChoosePhoto),
              onTap: () => Navigator.of(context).pop(ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
  }

  String? _contentTypeFor(XFile file) {
    final provided = file.mimeType?.toLowerCase();
    if (provided == 'image/jpeg' || provided == 'image/png' || provided == 'image/webp') {
      return provided;
    }
    final name = file.name.toLowerCase();
    if (name.endsWith('.jpg') || name.endsWith('.jpeg')) return 'image/jpeg';
    if (name.endsWith('.png')) return 'image/png';
    if (name.endsWith('.webp')) return 'image/webp';
    return null;
  }

  Future<void> _addPhoto() async {
    final l = AppLocalizations.of(context)!;
    final source = await _choosePhotoSource();
    if (source == null || !mounted) return;
    final file = await ImagePicker().pickImage(
      source: source,
      maxWidth: 1600,
      imageQuality: 80,
    );
    if (file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    if (bytes.length > 2 * 1024 * 1024) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.defectPhotoTooLarge)),
      );
      return;
    }
    final contentType = _contentTypeFor(file);
    if (contentType == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.defectPhotoUploadFailed)),
      );
      return;
    }
    setState(() => _photoBusy = true);
    try {
      await widget.api.uploadDefectAttachment(
        _defect.id,
        filename: file.name,
        contentType: contentType,
        bytes: bytes,
      );
      await _reloadAttachments();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.defectPhotoUploaded)),
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) setState(() => _photoBusy = false);
    }
  }

  Future<void> _preview(DefectAttachment attachment) async {
    final l = AppLocalizations.of(context)!;
    try {
      final bytes = await widget.api.downloadAttachment(attachment.id);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => Dialog(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900, maxHeight: 800),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(child: InteractiveViewer(child: Image.memory(bytes))),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(attachment.filename),
                ),
              ],
            ),
          ),
        ),
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message.isEmpty ? l.detailsLoadFailed : error.message)),
      );
    }
  }

  String _statusLabel(AppLocalizations l, String status) => switch (status) {
        'in_progress' => l.handoverStatusInProgress,
        'waiting' => l.defectStatusWaiting,
        'done' => l.handoverStatusDone,
        _ => l.handoverStatusOpen,
      };

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.86,
      minChildSize: 0.45,
      maxChildSize: 0.96,
      builder: (context, controller) => Material(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        clipBehavior: Clip.antiAlias,
        child: SafeArea(
          top: false,
          child: ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 32),
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.outlineVariant,
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                _defect.title,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  PriorityBadge(priority: _defect.priority),
                  StatusChip(status: _defect.status),
                ],
              ),
              const SizedBox(height: 16),
              Text(
                _defect.description.isEmpty
                    ? l.detailsNoFurtherInfo
                    : _defect.description,
              ),
              const SizedBox(height: 8),
              Text('${l.defectAssetLabel}: ${_defect.assetRef.isEmpty ? "—" : _defect.assetRef}'),
              Text('${l.defectOwnerLabel}: ${_defect.owner.isEmpty ? "—" : _defect.owner}'),
              if (_defect.dueDisplay.isNotEmpty)
                Text('${l.defectDueLabel}: ${_defect.dueDisplay}'),
              const SizedBox(height: 24),
              Text(l.defectSetStatus, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final status in const ['open', 'in_progress', 'waiting', 'done'])
                    FilterChip(
                      label: Text(_statusLabel(l, status)),
                      selected: _defect.status == status,
                      onSelected: _defect.status == status ? null : (_) => _setStatus(status),
                    ),
                ],
              ),
              const SizedBox(height: 28),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      l.defectPhotosTitle,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                  ),
                  FilledButton.tonalIcon(
                    onPressed: _photoBusy ? null : _addPhoto,
                    icon: _photoBusy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.add_a_photo_outlined),
                    label: Text(l.defectAddPhoto),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                l.defectPhotosHint,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
              const SizedBox(height: 12),
              if (_attachmentError != null) ErrorBanner(message: _attachmentError!),
              if (_attachmentsLoading)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_attachments.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(l.defectPhotosEmpty),
                )
              else
                for (final attachment in _attachments)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    minTileHeight: WachbuchTokens.touchTarget,
                    leading: const Icon(Icons.image_outlined),
                    title: Text(attachment.filename),
                    subtitle: Text('${attachment.sizeLabel} · ${attachment.uploadedBy}'),
                    trailing: const Icon(Icons.open_in_full),
                    onTap: () => _preview(attachment),
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DefectCard extends StatelessWidget {
  const _DefectCard({required this.defect, required this.onTap});

  final Defect defect;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: WachbuchTokens.touchTarget),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    PriorityBadge(priority: defect.priority),
                    StatusChip(status: defect.status),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  defect.title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  [
                    if (defect.assetRef.isNotEmpty) defect.assetRef,
                    if (defect.owner.isNotEmpty) defect.owner,
                    if (defect.dueDisplay.isNotEmpty)
                      '${l.defectDueLabel}: ${defect.dueDisplay}',
                  ].join(' · '),
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String _priorityLabel(AppLocalizations l, String priority) => switch (priority) {
      'urgent' => l.handoverPriorityUrgent,
      'important' => l.handoverPriorityImportant,
      _ => l.handoverPriorityNormal,
    };

String _categoryLabel(AppLocalizations l, String locale, String category) {
  return switch (category) {
    'vehicle' => l.handoverCategoryVehicle,
    'material' => l.handoverCategoryMaterial,
    'safety' => l.handoverCategorySafety,
    'task' => l.handoverCategoryTask,
    'facility' => locale == 'en' ? 'Facility' : 'Gebäude',
    'device' => locale == 'en' ? 'Device' : 'Gerät',
    'key' => locale == 'en' ? 'Key' : 'Schlüssel',
    _ => l.handoverEnumUnknown,
  };
}
