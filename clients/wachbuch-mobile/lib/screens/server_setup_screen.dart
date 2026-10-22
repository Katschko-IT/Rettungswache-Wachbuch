import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/api/server_address.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/demo/demo_api.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/screens/demo_picker_sheet.dart';
import 'package:wachbuch_mobile/screens/privacy_screen.dart';
import 'package:wachbuch_mobile/screens/qr_scan_screen.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

/// First screen: only server address (typed or QR) + confirm.
/// Matches Nextcloud/Paperless self-host onboarding and Material 3 forms.
class ServerSetupScreen extends StatefulWidget {
  const ServerSetupScreen({
    super.key,
    required this.store,
    required this.onServerReady,
    this.onDemoReady,
    this.apiFactory = demoAwareApiFactory,
  });

  final SessionStore store;
  final Future<void> Function(String serverUrl) onServerReady;
  final Future<void> Function(DemoService service)? onDemoReady;
  final WachbuchApiFactory apiFactory;

  @override
  State<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

class _ServerSetupScreenState extends State<ServerSetupScreen> {
  final _formKey = GlobalKey<FormState>();
  final _addressCtrl = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _addressCtrl.dispose();
    super.dispose();
  }

  Future<void> _scanQr() async {
    final address = await openServerQrScanner(context);
    if (address != null && mounted) {
      setState(() {
        _addressCtrl.text = address;
        _error = null;
      });
    }
  }

  Future<void> _confirm() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    WachbuchApi? api;
    try {
      final url = parseServerAddress(_addressCtrl.text);
      api = widget.apiFactory(url);
      await api.discover();
      await widget.onServerReady(url);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      api?.close();
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openDemo() async {
    final service = await showDemoPickerSheet(context);
    if (service == null || !mounted) return;
    final onDemoReady = widget.onDemoReady;
    if (onDemoReady != null) {
      await onDemoReady(service);
      return;
    }
    await widget.onServerReady(service.serverUrl);
  }

  void _openPrivacy() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const PrivacyScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.isTablet(width) ? 480.0 : 420.0;
    final scheme = Theme.of(context).colorScheme;
    final german = Localizations.localeOf(context).languageCode == 'de';

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxW),
            child: Form(
              key: _formKey,
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  const SizedBox(height: 32),
                  Icon(
                    Icons.apartment_outlined,
                    size: AppLayout.isTablet(width) ? 64 : 52,
                    color: scheme.primary,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    l.appName,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    l.setupServerAddressTitle,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    l.setupHint,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _addressCtrl,
                    decoration: InputDecoration(
                      labelText: l.setupAddressLabel,
                      hintText: l.setupAddressHint,
                      border: const OutlineInputBorder(),
                      prefixIcon: const Icon(Icons.link),
                      suffixIcon: IconButton(
                        tooltip: l.setupScanQr,
                        onPressed: _busy ? null : _scanQr,
                        icon: const Icon(Icons.qr_code_scanner),
                      ),
                    ),
                    keyboardType: TextInputType.url,
                    textInputAction: TextInputAction.done,
                    autocorrect: false,
                    enableSuggestions: false,
                    autofillHints: const [AutofillHints.url],
                    onFieldSubmitted: (_) {
                      if (!_busy) _confirm();
                    },
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return l.setupAddressRequired;
                      }
                      try {
                        parseServerAddress(value);
                      } catch (_) {
                        return l.setupAddressInvalid;
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _busy ? null : _scanQr,
                    icon: const Icon(Icons.photo_camera_outlined),
                    label: Text(l.setupScanQr),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    ErrorBanner(message: _error!),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _confirm,
                    child: _busy
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(l.setupConfirm),
                  ),
                  const SizedBox(height: 12),
                  TextButton.icon(
                    onPressed: _busy ? null : _openDemo,
                    icon: const Icon(Icons.science_outlined),
                    label: Text(l.setupDemoButton),
                  ),
                  const SizedBox(height: 4),
                  TextButton.icon(
                    key: const Key('privacy-policy-button'),
                    onPressed: _busy ? null : _openPrivacy,
                    icon: const Icon(Icons.privacy_tip_outlined),
                    label: Text(german ? 'Datenschutz' : 'Privacy'),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    l.setupFooter,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
