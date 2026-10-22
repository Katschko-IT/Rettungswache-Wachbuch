import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/crypto/e2ee.dart' as e2ee;
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/chat.dart';
import 'package:wachbuch_mobile/state/crypto_session.dart';
import 'package:wachbuch_mobile/state/verified_keys_store.dart';

/// Key verification sheet (R-020): colleagues compare E2EE key fingerprints.
///
/// The **own** fingerprint is always derived on-device from the unlocked
/// private scalar ([e2ee.ownFingerprintFromPrivate]) as the public point
/// `Q = d*G`; the server-reported own key/fingerprint is never trusted and can
/// never be substituted. A **colleague** fingerprint is only ever computed from
/// the server-supplied public JWK ([e2ee.validatedKeyFingerprint]); invalid or
/// off-curve keys are dropped (fail closed). If a server-reported member
/// fingerprint disagrees with the locally computed one, a tampering warning is
/// shown and the server value is never displayed or persisted.
///
/// Verified fingerprints are persisted per **(account, server, colleague)** in
/// [VerifiedKeysStore]. The account identity is resolved from the authenticated
/// user (`/me/` -> `user.id`/`username`) exactly once and captured immutably for
/// the lifetime of the sheet, so a logout/account switch cannot redirect a write
/// into another account's namespace.
class KeyVerificationSheet extends StatefulWidget {
  KeyVerificationSheet({
    super.key,
    required this.api,
    CryptoSession? session,
    this.accountKey,
  }) : session = session ?? CryptoSession.instance;

  final WachbuchApi api;
  final CryptoSession session;

  /// Immutable account identity supplied by the caller. When `null`, the sheet
  /// resolves it from `api.me()` once. If neither yields a value the sheet fails
  /// closed: it shows no stored state and refuses to persist verifications.
  final String? accountKey;

  @override
  State<KeyVerificationSheet> createState() => _KeyVerificationSheetState();
}

class _KeyVerificationSheetState extends State<KeyVerificationSheet> {
  bool _loading = true;
  String? _error;
  List<ChatMemberKey> _members = const [];

  /// Locally validated fingerprint per member (userId -> fingerprint). Members
  /// whose server key is missing/invalid are absent (hidden, fail closed).
  final Map<int, String> _fingerprints = {};

  /// Members whose server-reported fingerprint disagrees with the computed one.
  final Set<int> _serverMismatch = {};

  /// The server reported an own key/fingerprint that disagrees with the one
  /// derived from the local private scalar (diagnostic only; never trusted).
  bool _ownMismatch = false;

  /// Stored (verified) fingerprint per member (userId -> fingerprint).
  final Map<int, String> _verified = {};

  /// Members whose stored fingerprint no longer matches the current one.
  final Set<int> _changed = {};

  bool _showOwnQr = false;

  /// Captured account identity (immutable once resolved).
  String? _accountKey;
  VerifiedKeysStore? _store;
  int _loadVersion = 0;

  @override
  void initState() {
    super.initState();
    _accountKey = widget.accountKey;
    widget.session.addListener(_sessionChanged);
    _load();
  }

  void _sessionChanged() {
    if (mounted) setState(() => _showOwnQr = false);
  }

  @override
  void dispose() {
    widget.session.removeListener(_sessionChanged);
    super.dispose();
  }

  @override
  void didUpdateWidget(KeyVerificationSheet oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.session != widget.session) {
      oldWidget.session.removeListener(_sessionChanged);
      widget.session.addListener(_sessionChanged);
    }
    if (oldWidget.api != widget.api ||
        oldWidget.session != widget.session ||
        oldWidget.accountKey != widget.accountKey) {
      _accountKey = widget.accountKey;
      _store = null;
      _showOwnQr = false;
      _members = const [];
      _fingerprints.clear();
      _verified.clear();
      _changed.clear();
      _serverMismatch.clear();
      _ownMismatch = false;
      _load();
    }
  }

  String? get _ownFingerprint =>
      e2ee.ownFingerprintFromPrivate(widget.session.privateJwk);

  Future<String?> _resolveAccountKey() async {
    final provided = widget.accountKey;
    if (provided != null && provided.isNotEmpty) return provided;
    try {
      final me = await widget.api.me();
      final user = me['user'];
      if (user is Map) {
        final id = user['id'];
        if (id != null && id.toString().isNotEmpty) return id.toString();
        final name = user['username']?.toString();
        if (name != null && name.isNotEmpty) return name;
      }
      final top = me['username']?.toString();
      if (top != null && top.isNotEmpty) return top;
    } catch (_) {
      // Fail closed: no account identity -> no reads or writes.
    }
    return null;
  }

  Future<void> _load() async {
    final version = ++_loadVersion;
    final api = widget.api;
    final session = widget.session;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final accountKey = _accountKey ?? await _resolveAccountKey();
      if (!mounted || version != _loadVersion) return;
      _accountKey = accountKey;
      final store = accountKey == null
          ? null
          : VerifiedKeysStore(accountKey: accountKey);
      _store = store;
      final members = await api.chatMemberKeys();
      final stored = store == null
          ? <String, String>{}
          : await store.allFor(api.baseUrl);

      // The server-reported own key is only ever used as a diagnostic; the
      // displayed/QR own fingerprint is derived from the local private scalar.
      String? serverOwnFingerprint;
      try {
        final identity = await api.chatIdentity();
        final reported = identity['fingerprint'];
        if (reported is String && reported.isNotEmpty) {
          serverOwnFingerprint = reported;
        } else {
          final jwk = identity['public_jwk'];
          if (jwk is Map) {
            serverOwnFingerprint = e2ee.keyFingerprint(
              Map<String, dynamic>.from(jwk),
            );
          }
        }
      } catch (_) {
        // Ignore: the own key is derived locally regardless of the server.
      }
      final own = e2ee.ownFingerprintFromPrivate(session.privateJwk);
      final ownMismatch =
          own != null &&
          serverOwnFingerprint != null &&
          serverOwnFingerprint != own;
      if (!mounted || version != _loadVersion) return;

      final fingerprints = <int, String>{};
      final mismatch = <int>{};
      final verified = <int, String>{};
      final changed = <int>{};
      for (final member in members) {
        final computed = e2ee.validatedKeyFingerprint(member.publicJwk);
        if (computed == null) continue; // invalid server key -> hidden
        fingerprints[member.userId] = computed;
        final reported = member.fingerprint;
        if (reported != null && reported.isNotEmpty && reported != computed) {
          mismatch.add(member.userId);
        }
        final previous = stored[member.userId.toString()];
        if (previous != null) {
          if (previous == computed) {
            verified[member.userId] = computed;
          } else {
            changed.add(member.userId);
          }
        }
      }
      setState(() {
        _members = members;
        _fingerprints
          ..clear()
          ..addAll(fingerprints);
        _serverMismatch
          ..clear()
          ..addAll(mismatch);
        _ownMismatch = ownMismatch;
        _verified
          ..clear()
          ..addAll(verified);
        _changed
          ..clear()
          ..addAll(changed);
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted || version != _loadVersion) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _verifyByScan() async {
    final version = _loadVersion;
    final l = AppLocalizations.of(context)!;
    final scanned = await showDialog<String>(
      context: context,
      builder: (ctx) => Dialog(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(l.keyVerifyScanTitle),
            ),
            SizedBox(
              height: 260,
              width: 300,
              child: MobileScanner(
                onDetect: (capture) {
                  final value = capture.barcodes.firstOrNull?.rawValue;
                  if (value != null && value.isNotEmpty) {
                    Navigator.pop(ctx, value);
                  }
                },
              ),
            ),
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text(l.commonCancel),
            ),
          ],
        ),
      ),
    );
    if (scanned == null ||
        scanned.isEmpty ||
        !mounted ||
        version != _loadVersion) {
      return;
    }
    final normalized = scanned.replaceAll(RegExp(r'\s+'), '').toLowerCase();
    final match = _members
        .where((m) {
          final fp = _fingerprints[m.userId];
          return fp != null &&
              fp.replaceAll(RegExp(r'\s+'), '').toLowerCase() == normalized;
        })
        .toList(growable: false);
    final message = match.length != 1
        ? l.keyVerifyNoMatch
        : l.keyVerifyMatch(match.single.label);
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
    if (match.length == 1) {
      await _confirmVerified(match.single);
    }
  }

  Future<void> _confirmVerified(ChatMemberKey member) async {
    final version = _loadVersion;
    final fingerprint = _fingerprints[member.userId];
    final store = _store;
    if (fingerprint == null || store == null) return;
    final changed = await store.markVerified(
      widget.api.baseUrl,
      member.userId,
      fingerprint,
    );
    if (!mounted || version != _loadVersion) return;
    setState(() {
      _verified[member.userId] = fingerprint;
      _changed.remove(member.userId);
    });
    final l = AppLocalizations.of(context)!;
    if (changed) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.keyVerifyReverified(member.label))),
      );
    }
  }

  Future<void> _revoke(ChatMemberKey member) async {
    final version = _loadVersion;
    final store = _store;
    if (store == null) return;
    await store.remove(widget.api.baseUrl, member.userId);
    if (!mounted || version != _loadVersion) return;
    setState(() => _verified.remove(member.userId));
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final own = _ownFingerprint;
    return Material(
      color: theme.colorScheme.surface,
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      l.keyVerifyTitle,
                      style: theme.textTheme.titleLarge,
                    ),
                  ),
                  IconButton(
                    onPressed: _verifyByScan,
                    tooltip: l.keyVerifyScanAction,
                    icon: const Icon(Icons.qr_code_scanner),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                l.keyVerifyExplanation,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                Text(_error!, style: TextStyle(color: theme.colorScheme.error))
              else ...[
                if (_changed.isNotEmpty)
                  _Banner(
                    color: theme.colorScheme.errorContainer,
                    onColor: theme.colorScheme.onErrorContainer,
                    icon: Icons.warning_amber_rounded,
                    text: l.keyVerifyChangedWarning(_changed.length),
                  ),
                if (_serverMismatch.isNotEmpty || _ownMismatch)
                  _Banner(
                    color: theme.colorScheme.errorContainer,
                    onColor: theme.colorScheme.onErrorContainer,
                    icon: Icons.gpp_maybe_outlined,
                    text: l.keyVerifyServerMismatch(
                      _serverMismatch.length + (_ownMismatch ? 1 : 0),
                    ),
                  ),
                if (own == null)
                  // Locked session: no own key/QR, point at the unlock flow.
                  Text(l.chatUnlockHint, style: theme.textTheme.bodyMedium)
                else ...[
                  _FingerprintCard(
                    label: l.keyVerifyOwnKey,
                    fingerprint: own,
                    own: true,
                    verified: true,
                    onToggleQr: () => setState(() => _showOwnQr = !_showOwnQr),
                  ),
                  if (_showOwnQr)
                    Center(
                      child: Container(
                        color: Colors.white,
                        padding: const EdgeInsets.all(12),
                        margin: const EdgeInsets.only(top: 8),
                        child: QrImageView(
                          data: own,
                          semanticsLabel: own,
                          version: QrVersions.auto,
                          size: 180,
                        ),
                      ),
                    ),
                ],
                const SizedBox(height: 8),
                for (final member in _members)
                  if (_fingerprints.containsKey(member.userId))
                    _FingerprintCard(
                      label: member.label,
                      fingerprint: _fingerprints[member.userId]!,
                      own: false,
                      verified: _verified.containsKey(member.userId),
                      changed: _changed.contains(member.userId),
                      onVerify: () => _confirmVerified(member),
                      onRevoke: () => _revoke(member),
                    ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({
    required this.color,
    required this.onColor,
    required this.icon,
    required this.text,
  });

  final Color color;
  final Color onColor;
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, color: onColor),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: onColor),
            ),
          ),
        ],
      ),
    );
  }
}

class _FingerprintCard extends StatelessWidget {
  const _FingerprintCard({
    required this.label,
    required this.fingerprint,
    required this.own,
    required this.verified,
    this.changed = false,
    this.onToggleQr,
    this.onVerify,
    this.onRevoke,
  });

  final String label;
  final String fingerprint;
  final bool own;
  final bool verified;
  final bool changed;
  final VoidCallback? onToggleQr;
  final VoidCallback? onVerify;
  final VoidCallback? onRevoke;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onLongPress: () {
          Clipboard.setData(ClipboardData(text: fingerprint));
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(l.keyVerifyCopied)));
        },
        child: Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Icon(
                  verified
                      ? Icons.verified_outlined
                      : changed
                      ? Icons.warning_amber_rounded
                      : Icons.key_outlined,
                  color: verified
                      ? theme.colorScheme.primary
                      : changed
                      ? theme.colorScheme.error
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              label,
                              style: theme.textTheme.titleSmall,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (own) ...[
                            const SizedBox(width: 6),
                            Text(
                              l.keyVerifyOwnTag,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                          if (verified && !own) ...[
                            const SizedBox(width: 6),
                            Text(
                              l.keyVerifyVerifiedTag,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.primary,
                              ),
                            ),
                          ],
                          if (changed && !own) ...[
                            const SizedBox(width: 6),
                            Text(
                              l.keyVerifyChangedTag,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.error,
                              ),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        fingerprint,
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontFamily: 'monospace',
                          letterSpacing: 0.5,
                        ),
                      ),
                      if (!own) ...[
                        const SizedBox(height: 4),
                        if (verified)
                          TextButton(
                            onPressed: onRevoke,
                            child: Text(l.keyVerifyRevoke),
                          )
                        else
                          TextButton(
                            onPressed: onVerify,
                            child: Text(l.keyVerifyConfirmAction),
                          ),
                      ],
                    ],
                  ),
                ),
                if (own)
                  IconButton(
                    onPressed: onToggleQr,
                    tooltip: l.keyVerifyShowQr,
                    icon: const Icon(Icons.qr_code_2_outlined),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
