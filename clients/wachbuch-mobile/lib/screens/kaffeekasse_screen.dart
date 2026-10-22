import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/kaffeekasse.dart';
import 'package:wachbuch_mobile/state/coffee_state.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

class KaffeekasseScreen extends StatefulWidget {
  const KaffeekasseScreen({
    super.key,
    required this.api,
    this.state,
  });

  final WachbuchApi api;
  final CoffeeState? state;

  @override
  State<KaffeekasseScreen> createState() => _KaffeekasseScreenState();
}

class _KaffeekasseScreenState extends State<KaffeekasseScreen> {
  late final CoffeeState _state;
  late final bool _ownsState;

  @override
  void initState() {
    super.initState();
    _state = widget.state ?? CoffeeState(api: widget.api);
    _ownsState = widget.state == null;
    _state.addListener(_onStateChanged);
    _state.reload();
  }

  @override
  void dispose() {
    _state.removeListener(_onStateChanged);
    if (_ownsState) {
      _state.dispose();
    }
    super.dispose();
  }

  void _onStateChanged() {
    if (mounted) setState(() {});
  }

  Kaffeekasse? get _kasse => _state.data;
  bool get _loading => _state.loading;
  String? get _error => _state.error;

  Future<void> _reload() => _state.reload();

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);
    return Scaffold(
      appBar: AppBar(title: Text(AppLocalizations.of(context)!.kaffeekasseTitle)),
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
    if (_loading && _kasse == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final kasse = _kasse;
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
          if (kasse != null) ...[
            _BalanceCard(kasse: kasse),
            const SizedBox(height: 16),
            if (kasse.paymentHint.isNotEmpty) ...[
              _PaymentHintCard(hint: kasse.paymentHint),
              const SizedBox(height: 16),
            ],
            _SectionTitle(title: AppLocalizations.of(context)!.kaffeekasseLastTransactions),
            const SizedBox(height: 8),
            if (kasse.ledger.isEmpty)
              _EmptyState(
                icon: Icons.receipt_long_outlined,
                message: AppLocalizations.of(context)!.kaffeekasseEmptyLedger,
              )
            else
              for (final entry in kasse.ledger) ...[
                _LedgerTile(entry: entry),
                const Divider(height: 1),
              ],
          ],
        ],
      ),
    );
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.kasse});

  final Kaffeekasse kasse;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final urgent = kasse.isNegative;
    final background = urgent ? scheme.errorContainer : scheme.primaryContainer;
    final foreground = urgent ? scheme.onErrorContainer : scheme.onPrimaryContainer;
    return Material(
      color: background,
      borderRadius: BorderRadius.circular(18),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.coffee_outlined,
                  color: foreground,
                  size: 28,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    AppLocalizations.of(context)!.kaffeekasseBalanceLabel,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: foreground,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              kasse.balance,
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: foreground,
                    fontWeight: FontWeight.w700,
                  ),
            ),
            if (urgent) ...[
              const SizedBox(height: 6),
              Text(
                AppLocalizations.of(context)!.kaffeekasseNegative,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: foreground,
                    ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PaymentHintCard extends StatelessWidget {
  const _PaymentHintCard({required this.hint});

  final String hint;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.secondaryContainer,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.payments_outlined,
              color: scheme.onSecondaryContainer,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                hint,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSecondaryContainer,
                    ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(Icons.receipt_outlined, size: 22, color: scheme.primary),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
      ],
    );
  }
}

class _LedgerTile extends StatelessWidget {
  const _LedgerTile({required this.entry});

  final KaffeekasseEntry entry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final amountColor =
        entry.isNegative ? scheme.error : scheme.primary;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(vertical: 4),
      title: Text(
        entry.description.isNotEmpty
            ? entry.description
            : AppLocalizations.of(context)!.kaffeekasseEntryFallback,
        style: Theme.of(context).textTheme.bodyLarge,
      ),
      subtitle: Text(
        [
          if (entry.userName.isNotEmpty) entry.userName,
          if (entry.createdAt != null) _formatTimestamp(entry.createdAt!),
        ].join(' · '),
        style: Theme.of(context).textTheme.bodySmall,
      ),
      trailing: Text(
        entry.formattedAmount,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: amountColor,
              fontWeight: FontWeight.w600,
            ),
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
