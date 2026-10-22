import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/crypto/e2ee.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/chat.dart';
import 'package:wachbuch_mobile/state/crypto_session.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

enum _ChatPhase { loading, needsSetup, locked, ready, error }

class _DisplayMessage {
  const _DisplayMessage({
    required this.authorName,
    required this.isOwn,
    required this.text,
    required this.readable,
    this.createdAt,
  });

  final String authorName;
  final bool isOwn;
  final String text;
  final bool readable;
  final DateTime? createdAt;
}

/// Station chat (Wachenchat) with end-to-end encryption handled locally.
class ChatScreen extends StatefulWidget {
  ChatScreen({super.key, required this.api, CryptoSession? session})
      : session = session ?? CryptoSession.instance;

  final WachbuchApi api;
  final CryptoSession session;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  _ChatPhase _phase = _ChatPhase.loading;
  String? _error;
  bool _busy = false;

  Map<String, dynamic>? _bundle;
  List<ChatMemberKey> _memberKeys = const [];
  List<_DisplayMessage> _messages = const [];

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
      _phase = _ChatPhase.loading;
      _error = null;
    });
    try {
      final identity = await widget.api.chatIdentity();
      if (identity['configured'] != true) {
        setState(() => _phase = _ChatPhase.needsSetup);
        return;
      }
      _bundle = identity;
      if (widget.session.isUnlocked) {
        await _loadFeed();
      } else {
        setState(() => _phase = _ChatPhase.locked);
      }
    } on ApiException catch (error) {
      setState(() {
        _phase = _ChatPhase.error;
        _error = error.message.isNotEmpty ? error.message : null;
      });
    }
  }

  Future<void> _loadFeed() async {
    final privateJwk = widget.session.privateJwk!;
    _memberKeys = await widget.api.chatMemberKeys();
    final feed = await widget.api.stationChat();
    _messages = feed.map((item) {
      if (!item.readable) {
        return _DisplayMessage(
          authorName: item.authorName,
          isOwn: item.isOwn,
          text: '',
          readable: false,
          createdAt: item.createdAt,
        );
      }
      try {
        final text = E2ee.decryptEnvelope(item.toEnvelope(), privateJwk);
        return _DisplayMessage(
          authorName: item.authorName,
          isOwn: item.isOwn,
          text: text,
          readable: true,
          createdAt: item.createdAt,
        );
      } on Object {
        return _DisplayMessage(
          authorName: item.authorName,
          isOwn: item.isOwn,
          text: '',
          readable: false,
          createdAt: item.createdAt,
        );
      }
    }).toList(growable: false);
    if (mounted) setState(() => _phase = _ChatPhase.ready);
  }

  Future<void> _setup() async {
    final passphrase = _passphraseController.text;
    if (passphrase.length < 8) {
      setState(() => _error = AppLocalizations.of(context)!.chatSetupHint);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final identity = E2ee.generateIdentity(passphrase);
      await widget.api.registerChatIdentity(
        publicJwk: identity.publicJwk,
        wrappedPrivateJwk: identity.wrappedPrivateJwk,
        kdfSalt: identity.kdfSalt,
        kdfIterations: identity.kdfIterations,
      );
      widget.session.unlockWith(identity.privateJwk);
      _passphraseController.clear();
      await _loadFeed();
    } on ApiException catch (error) {
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _unlock() async {
    final passphrase = _passphraseController.text;
    if (passphrase.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final bundle = _bundle!;
      final privateJwk = E2ee.unlockIdentity(
        wrappedPrivateJwk: bundle['wrapped_private_jwk'] as String,
        kdfSalt: bundle['kdf_salt'] as String,
        kdfIterations: (bundle['kdf_iterations'] as num).toInt(),
        passphrase: passphrase,
      );
      widget.session.unlockWith(privateJwk);
      _passphraseController.clear();
      await _loadFeed();
    } on E2eeException {
      setState(() => _error = AppLocalizations.of(context)!.chatWrongPassphrase);
    } on ApiException catch (error) {
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send() async {
    final text = _composeController.text.trim();
    if (text.isEmpty || !widget.session.isUnlocked) return;
    final recipients = _memberKeys
        .where((key) => key.hasKeys && key.publicJwk != null)
        .map((key) => key.toRecipient())
        .toList(growable: false);
    if (recipients.isEmpty) return;
    setState(() => _busy = true);
    try {
      final payload = E2ee.encryptForRecipients(text, recipients);
      await widget.api.sendStationChat(payload);
      _composeController.clear();
      await _loadFeed();
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
    final maxW = AppLayout.contentMaxWidth(width);
    return Scaffold(
      appBar: AppBar(
        title: Text(l.chatTitle),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(20),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(
              l.chatSubtitle,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ),
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
    switch (_phase) {
      case _ChatPhase.loading:
        return const Center(child: CircularProgressIndicator());
      case _ChatPhase.error:
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            ErrorBanner(message: _error ?? l.chatLoadError),
            const SizedBox(height: 12),
            FilledButton(onPressed: _load, child: Text(l.chatUnlockAction)),
          ],
        );
      case _ChatPhase.needsSetup:
        return _passphrasePane(
          title: l.chatSetupTitle,
          hint: l.chatSetupHint,
          action: l.chatSetupAction,
          onSubmit: _setup,
        );
      case _ChatPhase.locked:
        return _passphrasePane(
          title: l.chatUnlockTitle,
          hint: l.chatUnlockHint,
          action: l.chatUnlockAction,
          onSubmit: _unlock,
        );
      case _ChatPhase.ready:
        return _chatPane(context);
    }
  }

  Widget _passphrasePane({
    required String title,
    required String hint,
    required String action,
    required Future<void> Function() onSubmit,
  }) {
    final l = AppLocalizations.of(context)!;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(hint, style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 16),
        if (_error != null) ...[
          ErrorBanner(message: _error!),
          const SizedBox(height: 12),
        ],
        TextField(
          controller: _passphraseController,
          obscureText: true,
          decoration: InputDecoration(labelText: l.chatPassphrase),
          onSubmitted: (_) => onSubmit(),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : onSubmit,
          child: _busy
              ? const SizedBox(
                  height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : Text(action),
        ),
      ],
    );
  }

  Widget _chatPane(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    return Column(
      children: [
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(12),
            child: ErrorBanner(message: _error!),
          ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _loadFeed,
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
                    itemBuilder: (context, index) => _MessageBubble(
                      message: _messages[index],
                      meLabel: l.chatMe,
                      unreadableLabel: l.chatUnreadable,
                    ),
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

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.message,
    required this.meLabel,
    required this.unreadableLabel,
  });

  final _DisplayMessage message;
  final String meLabel;
  final String unreadableLabel;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final align = message.isOwn ? CrossAxisAlignment.end : CrossAxisAlignment.start;
    final bubbleColor = message.isOwn ? scheme.primaryContainer : scheme.surfaceContainerHighest;
    final onBubble = message.isOwn ? scheme.onPrimaryContainer : scheme.onSurface;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: align,
        children: [
          Text(
            message.isOwn ? meLabel : message.authorName,
            style: Theme.of(context).textTheme.labelSmall,
          ),
          const SizedBox(height: 2),
          Container(
            constraints: const BoxConstraints(maxWidth: 320),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: bubbleColor,
              borderRadius: BorderRadius.circular(14),
            ),
            child: message.readable
                ? Text(message.text, style: TextStyle(color: onBubble))
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.lock_outline, size: 14, color: scheme.onSurfaceVariant),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          unreadableLabel,
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
