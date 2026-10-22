import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/auth/session_store.dart';
import 'package:wachbuch_mobile/demo/demo_api.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/layout.dart';

/// Second screen: username + password against the chosen server.
class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.store,
    required this.serverUrl,
    required this.onLoggedIn,
    required this.onChangeServer,
    this.notice,
    this.apiFactory = demoAwareApiFactory,
  });

  final SessionStore store;
  final String serverUrl;
  final String? notice;
  final Future<void> Function(
    String serverUrl,
    String token, {
    DateTime? expiresAt,
  })
  onLoggedIn;
  final Future<void> Function() onChangeServer;
  final WachbuchApiFactory apiFactory;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _tokenCtrl = TextEditingController();
  bool _busy = false;
  bool _useTokenPaste = false;
  bool _obscure = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _error = widget.notice;
  }

  @override
  void didUpdateWidget(covariant LoginScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.notice != oldWidget.notice && widget.notice != null) {
      _error = widget.notice;
    }
  }

  @override
  void dispose() {
    _userCtrl.dispose();
    _passCtrl.dispose();
    _tokenCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final l = AppLocalizations.of(context)!;
    setState(() {
      _busy = true;
      _error = null;
    });
    WachbuchApi? api;
    try {
      api = widget.apiFactory(widget.serverUrl);
      late final String token;
      DateTime? expiresAt;
      if (_useTokenPaste) {
        token = _tokenCtrl.text.trim();
        if (token.isEmpty) {
          throw ApiException(400, l.loginTokenPasteHint);
        }
        await api.copyWithToken(token).me();
      } else {
        final auth = await api.obtainToken(
          username: _userCtrl.text.trim(),
          password: _passCtrl.text,
          label: 'Wachbuch Mobile',
        );
        token = auth.value;
        expiresAt = auth.expiresAt;
      }
      TextInput.finishAutofillContext(shouldSave: true);
      _passCtrl.clear();
      _tokenCtrl.clear();
      await widget.onLoggedIn(
        widget.serverUrl,
        token,
        expiresAt: expiresAt,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        if (error.isMfaRequired) {
          _error = '${error.message}\n\n${l.loginMfaHint}';
          _useTokenPaste = true;
        }
      });
    } catch (error) {
      if (!mounted) return;
      final message = error is ArgumentError
          ? (error.message?.toString() ?? l.loginInvalidInput)
          : error.toString();
      setState(() => _error = message);
    } finally {
      api?.close();
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.isTablet(width) ? 480.0 : 420.0;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: Text(l.loginAppBarTitle),
        leading: IconButton(
          tooltip: l.loginChangeServer,
          onPressed: _busy ? null : () => widget.onChangeServer(),
          icon: const Icon(Icons.arrow_back),
        ),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxW),
            child: AutofillGroup(
              child: Form(
                key: _formKey,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    Text(
                      l.loginHeading,
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      widget.serverUrl,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 28),
                    if (_useTokenPaste)
                      TextFormField(
                        controller: _tokenCtrl,
                        decoration: InputDecoration(
                          labelText: l.loginTokenLabel,
                          border: const OutlineInputBorder(),
                          prefixIcon: const Icon(Icons.key_outlined),
                          helperText: l.loginTokenHelper,
                        ),
                        obscureText: true,
                        validator: (v) => (v == null || v.trim().isEmpty)
                            ? l.loginTokenRequired
                            : null,
                      )
                    else ...[
                      TextFormField(
                        controller: _userCtrl,
                        decoration: InputDecoration(
                          labelText: l.loginUsername,
                          border: const OutlineInputBorder(),
                          prefixIcon: const Icon(Icons.person_outline),
                        ),
                        textInputAction: TextInputAction.next,
                        autocorrect: false,
                        enableSuggestions: false,
                        autofillHints: const [AutofillHints.username],
                        inputFormatters: [
                          FilteringTextInputFormatter.deny(RegExp(r'\s')),
                        ],
                        validator: (v) => (v == null || v.trim().isEmpty)
                            ? l.loginUsernameRequired
                            : null,
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: _passCtrl,
                        decoration: InputDecoration(
                          labelText: l.loginPassword,
                          border: const OutlineInputBorder(),
                          prefixIcon: const Icon(Icons.lock_outline),
                          suffixIcon: IconButton(
                            tooltip: _obscure ? l.loginShow : l.loginHide,
                            onPressed: () =>
                                setState(() => _obscure = !_obscure),
                            icon: Icon(
                              _obscure
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined,
                            ),
                          ),
                        ),
                        obscureText: _obscure,
                        textInputAction: TextInputAction.done,
                        autofillHints: const [AutofillHints.password],
                        onFieldSubmitted: (_) {
                          if (!_busy) _submit();
                        },
                        validator: (v) => (v == null || v.isEmpty)
                            ? l.loginPasswordRequired
                            : null,
                      ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      ErrorBanner(message: _error!),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              height: 22,
                              width: 22,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(l.loginSubmit),
                    ),
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: _busy
                          ? null
                          : () => setState(() {
                              _useTokenPaste = !_useTokenPaste;
                              _error = null;
                            }),
                      child: Text(
                        _useTokenPaste ? l.loginUseCredentials : l.loginUseToken,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
