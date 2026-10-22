import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/crypto/e2ee.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/chat.dart';
import 'package:wachbuch_mobile/state/crypto_session.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';
import 'package:wachbuch_mobile/screens/key_verification_sheet.dart';

/// List of group chats plus a create action.
class GroupsScreen extends StatefulWidget {
  GroupsScreen({super.key, required this.api, CryptoSession? session})
      : session = session ?? CryptoSession.instance;

  final WachbuchApi api;
  final CryptoSession session;

  @override
  State<GroupsScreen> createState() => _GroupsScreenState();
}

class _GroupsScreenState extends State<GroupsScreen> {
  List<ChatGroupSummary> _groups = const [];
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
      final groups = await widget.api.chatGroups();
      if (!mounted) return;
      setState(() {
        _groups = groups;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _openCreate() async {
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _GroupCreateSheet(api: widget.api),
    );
    if (created == true) await _reload();
  }

  void _openGroup(ChatGroupSummary group) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => GroupThreadScreen(
        api: widget.api,
        groupId: group.id,
        title: group.name,
        session: widget.session,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    return Scaffold(
      appBar: AppBar(
        title: Text(l.groupsTitle),
        actions: [
          IconButton(
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              builder: (_) => KeyVerificationSheet(
                api: widget.api,
                session: widget.session,
              ),
            ),
            tooltip: l.keyVerifyTitle,
            icon: const Icon(Icons.verified_user_outlined),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCreate,
        icon: const Icon(Icons.group_add_outlined),
        label: Text(l.groupsCreate),
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: AppLayout.contentMaxWidth(width)),
          child: _body(context, l),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, AppLocalizations l) {
    if (_loading && _groups.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        children: [
          if (_error != null) ...[
            ErrorBanner(message: _error!),
            const SizedBox(height: 12),
          ],
          if (_groups.isEmpty && _error == null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 64),
              child: Center(child: Text(l.groupsEmpty)),
            )
          else
            for (final group in _groups)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.groups_outlined),
                  title: Text(group.name),
                  subtitle: Text('${group.memberCount} ${l.groupMembers}'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _openGroup(group),
                ),
              ),
        ],
      ),
    );
  }
}

class _GroupCreateSheet extends StatefulWidget {
  const _GroupCreateSheet({required this.api});
  final WachbuchApi api;

  @override
  State<_GroupCreateSheet> createState() => _GroupCreateSheetState();
}

class _GroupCreateSheetState extends State<_GroupCreateSheet> {
  final _nameController = TextEditingController();
  final Set<int> _selected = {};
  List<ChatMemberKey> _colleagues = const [];
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadColleagues();
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _loadColleagues() async {
    try {
      final keys = await widget.api.chatMemberKeys();
      if (!mounted) return;
      setState(() {
        _colleagues = keys.where((k) => k.hasKeys).toList(growable: false);
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createChatGroup(name: name, memberIds: _selected.toList());
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
          Text(l.groupsCreate, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          if (_error != null) ...[
            ErrorBanner(message: _error!),
            const SizedBox(height: 12),
          ],
          TextField(
            controller: _nameController,
            maxLength: 120,
            decoration: InputDecoration(labelText: l.groupName),
          ),
          const SizedBox(height: 8),
          Text(l.groupSelectMembers, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 4),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_colleagues.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(l.groupNoColleagues),
            )
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 240),
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final colleague in _colleagues)
                    CheckboxListTile(
                      value: _selected.contains(colleague.userId),
                      title: Text(colleague.label),
                      onChanged: _saving
                          ? null
                          : (checked) => setState(() {
                                if (checked == true) {
                                  _selected.add(colleague.userId);
                                } else {
                                  _selected.remove(colleague.userId);
                                }
                              }),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _saving ? null : _submit,
            child: _saving
                ? const SizedBox(
                    height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(l.groupCreateAction),
          ),
        ],
      ),
    );
  }
}

/// A single group's message thread with E2EE unlock, display and compose.
class GroupThreadScreen extends StatefulWidget {
  GroupThreadScreen({
    super.key,
    required this.api,
    required this.groupId,
    required this.title,
    CryptoSession? session,
  }) : session = session ?? CryptoSession.instance;

  final WachbuchApi api;
  final int groupId;
  final String title;
  final CryptoSession session;

  @override
  State<GroupThreadScreen> createState() => _GroupThreadScreenState();
}

class _GroupThreadScreenState extends State<GroupThreadScreen> {
  bool _loading = true;
  bool _needsUnlock = false;
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _bundle;
  List<ChatMemberKey> _members = const [];
  List<_GroupDisplayMessage> _messages = const [];

  final _passphraseController = TextEditingController();
  final _composeController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _passphraseController.dispose();
    _composeController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (!widget.session.isUnlocked) {
        final identity = await widget.api.chatIdentity();
        if (identity['configured'] != true) {
          setState(() {
            _loading = false;
            _needsUnlock = true;
            _error = AppLocalizations.of(context)!.chatSetupHint;
          });
          return;
        }
        _bundle = identity;
        setState(() {
          _loading = false;
          _needsUnlock = true;
        });
        return;
      }
      await _loadThread();
    } on ApiException catch (error) {
      setState(() {
        _loading = false;
        _error = error.message;
      });
    }
  }

  Future<void> _unlock() async {
    final passphrase = _passphraseController.text;
    if (passphrase.isEmpty || _bundle == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final privateJwk = E2ee.unlockIdentity(
        wrappedPrivateJwk: _bundle!['wrapped_private_jwk'] as String,
        kdfSalt: _bundle!['kdf_salt'] as String,
        kdfIterations: (_bundle!['kdf_iterations'] as num).toInt(),
        passphrase: passphrase,
      );
      widget.session.unlockWith(privateJwk);
      _passphraseController.clear();
      setState(() => _needsUnlock = false);
      await _loadThread();
    } on E2eeException {
      setState(() => _error = AppLocalizations.of(context)!.chatWrongPassphrase);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadThread() async {
    setState(() => _loading = true);
    final thread = await widget.api.groupThread(widget.groupId);
    final privateJwk = widget.session.privateJwk!;
    _members = thread.members;
    _messages = thread.messages.map((item) {
      if (!item.readable) {
        return _GroupDisplayMessage(item.authorName, item.isOwn, '', false);
      }
      try {
        return _GroupDisplayMessage(
          item.authorName,
          item.isOwn,
          E2ee.decryptEnvelope(item.toEnvelope(), privateJwk),
          true,
        );
      } on Object {
        return _GroupDisplayMessage(item.authorName, item.isOwn, '', false);
      }
    }).toList(growable: false);
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _send() async {
    final text = _composeController.text.trim();
    if (text.isEmpty || !widget.session.isUnlocked) return;
    final recipients = _members
        .where((key) => key.hasKeys && key.publicJwk != null)
        .map((key) => key.toRecipient())
        .toList(growable: false);
    if (recipients.isEmpty) return;
    setState(() => _busy = true);
    try {
      final payload = E2ee.encryptForRecipients(text, recipients);
      await widget.api.sendGroupMessage(widget.groupId, payload);
      _composeController.clear();
      await _loadThread();
    } on ApiException catch (error) {
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: AppLayout.contentMaxWidth(width)),
          child: _body(context, l),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, AppLocalizations l) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_needsUnlock) {
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(l.chatUnlockTitle, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Text(l.chatUnlockHint),
          const SizedBox(height: 16),
          if (_error != null) ...[
            ErrorBanner(message: _error!),
            const SizedBox(height: 12),
          ],
          TextField(
            controller: _passphraseController,
            obscureText: true,
            decoration: InputDecoration(labelText: l.chatPassphrase),
            onSubmitted: (_) => _unlock(),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _unlock,
            child: _busy
                ? const SizedBox(
                    height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(l.chatUnlockAction),
          ),
        ],
      );
    }
    return Column(
      children: [
        if (_error != null)
          Padding(padding: const EdgeInsets.all(12), child: ErrorBanner(message: _error!)),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _loadThread,
            child: _messages.isEmpty
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 64),
                        child: Center(child: Text(l.chatEmpty)),
                      ),
                    ],
                  )
                : ListView.builder(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(12),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final message = _messages[index];
                      final scheme = Theme.of(context).colorScheme;
                      return Align(
                        alignment:
                            message.isOwn ? Alignment.centerRight : Alignment.centerLeft,
                        child: Container(
                          margin: const EdgeInsets.symmetric(vertical: 4),
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          constraints: const BoxConstraints(maxWidth: 320),
                          decoration: BoxDecoration(
                            color: message.isOwn
                                ? scheme.primaryContainer
                                : scheme.surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                message.isOwn ? l.chatMe : message.authorName,
                                style: Theme.of(context).textTheme.labelSmall,
                              ),
                              const SizedBox(height: 2),
                              message.readable
                                  ? Text(message.text)
                                  : Text(
                                      l.chatUnreadable,
                                      style: const TextStyle(fontStyle: FontStyle.italic),
                                    ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _composeController,
                    maxLength: 500,
                    minLines: 1,
                    maxLines: 3,
                    decoration: InputDecoration(
                      hintText: l.chatComposeHint,
                      counterText: '',
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: _busy ? null : _send,
                  icon: const Icon(Icons.send),
                  tooltip: l.chatSend,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _GroupDisplayMessage {
  const _GroupDisplayMessage(this.authorName, this.isOwn, this.text, this.readable);
  final String authorName;
  final bool isOwn;
  final String text;
  final bool readable;
}
