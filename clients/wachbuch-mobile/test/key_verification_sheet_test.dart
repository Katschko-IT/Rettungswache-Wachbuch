import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/crypto/e2ee.dart' as e2ee;
import 'package:wachbuch_mobile/models/chat.dart';
import 'package:wachbuch_mobile/screens/key_verification_sheet.dart';
import 'package:wachbuch_mobile/state/crypto_session.dart';
import 'package:wachbuch_mobile/state/verified_keys_store.dart';

import 'test_localization.dart';

// Recipient identity from the interop vector (see crypto/e2ee_test.dart).
const Map<String, dynamic> _privateJwk = {
  'kty': 'EC',
  'crv': 'P-256',
  'x': 'AZQtv9vAQ-cNiNrOIXNMnoltPWutBNOBKBaT-vVGU1M',
  'y': 'X-eE4z_DhcDRcTARZ7-_DM0KtrG4dnc3M9lFEJAJFa0',
  'd': 'iDvAFh2kA0hYX7FJk7scKjwJkLatZBpd1u8Au-0t_pQ',
};
const Map<String, dynamic> _publicJwk = {
  'kty': 'EC',
  'crv': 'P-256',
  'x': 'AZQtv9vAQ-cNiNrOIXNMnoltPWutBNOBKBaT-vVGU1M',
  'y': 'X-eE4z_DhcDRcTARZ7-_DM0KtrG4dnc3M9lFEJAJFa0',
};
const String _localFingerprint = '9ec5edaf 05c3d6e7 04c48669 4fada691';
const String _baseUrl = 'https://wache.example.org';

/// Off-curve (x, y) = (1, 1): not a valid P-256 public key.
const Map<String, dynamic> _offCurveJwk = {
  'kty': 'EC',
  'crv': 'P-256',
  'x': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE',
  'y': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE',
};

class _FakeVerifyApi extends WachbuchApi {
  _FakeVerifyApi({required this.members, this.identity, this.meAccount = '7'})
    : super(baseUrl: _baseUrl, token: 'wb_test');

  final List<ChatMemberKey> members;
  final Map<String, dynamic>? identity;

  /// Current login identity (`/me/` -> `user.id`). Mutable to model a logout /
  /// account switch mid-session.
  String meAccount;

  @override
  Future<List<ChatMemberKey>> chatMemberKeys() async => members;

  @override
  Future<Map<String, dynamic>> chatIdentity() async => identity ?? const {};

  @override
  Future<Map<String, dynamic>> me() async => {
    'user': {'id': int.tryParse(meAccount), 'username': 'tester-$meAccount'},
  };
}

class _DelayedVerifyApi extends _FakeVerifyApi {
  _DelayedVerifyApi() : super(members: const []);
  final pendingMembers = Completer<List<ChatMemberKey>>();
  @override
  Future<List<ChatMemberKey>> chatMemberKeys() => pendingMembers.future;
}

ChatMemberKey _member({
  required int userId,
  required String label,
  Map<String, dynamic>? publicJwk,
  String? fingerprint,
}) => ChatMemberKey(
  userId: userId,
  label: label,
  hasKeys: true,
  publicJwk: publicJwk,
  fingerprint: fingerprint,
);

Future<void> _pumpSheet(
  WidgetTester tester, {
  required _FakeVerifyApi api,
  required CryptoSession session,
}) async {
  await tester.pumpWidget(
    localizedApp(
      home: Scaffold(
        body: KeyVerificationSheet(api: api, session: session),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('own fingerprint comes from the local key, never the server', (
    tester,
  ) async {
    // A malicious server advertises a different key/fingerprint for us.
    final serverIdentity = e2ee.E2ee.generateIdentity('server-pw');
    final serverFp = e2ee.keyFingerprint(serverIdentity.publicJwk)!;
    expect(serverFp, isNot(_localFingerprint));

    final api = _FakeVerifyApi(
      members: const [],
      identity: {
        'configured': true,
        'fingerprint': serverFp,
        'public_jwk': serverIdentity.publicJwk,
      },
    );
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    expect(find.text(_localFingerprint), findsOneWidget);
    expect(find.text(serverFp), findsNothing);
  });

  testWidgets('a malicious server own key is flagged, local key still shown', (
    tester,
  ) async {
    final serverIdentity = e2ee.E2ee.generateIdentity('server-pw');
    final api = _FakeVerifyApi(
      members: const [],
      identity: {'configured': true, 'public_jwk': serverIdentity.publicJwk},
    );
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    // Own key/QR stays local; the substitution is surfaced as a warning.
    expect(find.text(_localFingerprint), findsOneWidget);
    expect(find.textContaining('Mögliche Server-Manipulation'), findsOneWidget);
  });

  testWidgets('late old-account response cannot replace the current account', (
    tester,
  ) async {
    final oldApi = _DelayedVerifyApi();
    final session = CryptoSession()..unlockWith(_privateJwk);
    await tester.pumpWidget(
      localizedApp(
        home: Scaffold(
          body: KeyVerificationSheet(api: oldApi, session: session),
        ),
      ),
    );
    await tester.pump();
    await _pumpSheet(
      tester,
      api: _FakeVerifyApi(members: const [], meAccount: '8'),
      session: session,
    );
    oldApi.pendingMembers.complete([
      _member(userId: 2, label: 'Old account colleague', publicJwk: _publicJwk),
    ]);
    await tester.pumpAndSettle();
    expect(find.text('Old account colleague'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('no own key or QR while the session is locked', (tester) async {
    final api = _FakeVerifyApi(members: const []);
    final session = CryptoSession(); // locked

    await _pumpSheet(tester, api: api, session: session);

    expect(find.text(_localFingerprint), findsNothing);
    expect(find.byIcon(Icons.qr_code_2_outlined), findsNothing);
    expect(find.byType(QrImageView), findsNothing);
    // The existing unlock flow is pointed at instead of showing a key.
    expect(
      find.textContaining('um verschlüsselte Nachrichten'),
      findsOneWidget,
    );
  });

  testWidgets('the QR carries the locally computed fingerprint', (
    tester,
  ) async {
    final api = _FakeVerifyApi(members: const []);
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    await tester.tap(find.byIcon(Icons.qr_code_2_outlined));
    await tester.pumpAndSettle();

    final qr = tester.widget<QrImageView>(find.byType(QrImageView));
    // The QR payload is the locally derived fingerprint (data mirrors the
    // public semanticsLabel; QrImageView keeps `data` private).
    expect(qr.semanticsLabel, _localFingerprint);
  });

  testWidgets('locking an open sheet immediately removes the own QR', (
    tester,
  ) async {
    final session = CryptoSession()..unlockWith(_privateJwk);
    await _pumpSheet(
      tester,
      api: _FakeVerifyApi(members: []),
      session: session,
    );
    await tester.tap(find.byIcon(Icons.qr_code_2_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(QrImageView), findsOneWidget);
    session.lock();
    await tester.pumpAndSettle();
    expect(find.byType(QrImageView), findsNothing);
    expect(find.text(_localFingerprint), findsNothing);
  });

  testWidgets('fingerprints remain scrollable on a small viewport', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(320, 400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await _pumpSheet(
      tester,
      api: _FakeVerifyApi(
        members: [_member(userId: 2, label: 'Alex', publicJwk: _publicJwk)],
      ),
      session: CryptoSession()..unlockWith(_privateJwk),
    );
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text(_localFingerprint).last);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('members with an invalid key are hidden (fail closed)', (
    tester,
  ) async {
    final api = _FakeVerifyApi(
      members: [
        _member(userId: 2, label: 'Alex', publicJwk: _publicJwk),
        _member(
          userId: 4,
          label: 'Böse',
          publicJwk: _offCurveJwk,
          fingerprint: 'x',
        ),
      ],
    );
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    expect(find.text('Alex'), findsOneWidget);
    // The off-curve key yields no fingerprint, so the member is not listed and
    // cannot be marked verified.
    expect(find.text('Böse'), findsNothing);
  });

  testWidgets('a faked server fingerprint is diagnostic, not trusted', (
    tester,
  ) async {
    final api = _FakeVerifyApi(
      members: [
        _member(
          userId: 3,
          label: 'Mara',
          publicJwk: _publicJwk,
          fingerprint: 'DEADBEEF DEADBEEF DEADBEEF DEADBEEF',
        ),
      ],
    );
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    // The locally computed fingerprint is shown, the server's fake is not.
    expect(find.text(_localFingerprint), findsNWidgets(2)); // own + member
    expect(find.text('DEADBEEF DEADBEEF DEADBEEF DEADBEEF'), findsNothing);
    expect(find.textContaining('Mögliche Server-Manipulation'), findsOneWidget);
  });

  testWidgets(
    'a stored fingerprint that no longer matches warns (key change)',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        VerifiedKeysStore.storageKey: jsonEncode({
          '7': {
            _baseUrl: {'2': 'STALE STALE STALE STALE'},
          },
        }),
      });
      final api = _FakeVerifyApi(
        members: [_member(userId: 2, label: 'Alex', publicJwk: _publicJwk)],
      );
      final session = CryptoSession()
        ..unlockWith(Map<String, dynamic>.from(_privateJwk));

      await _pumpSheet(tester, api: api, session: session);

      expect(find.text('Schlüssel geändert!'), findsOneWidget);
      expect(find.textContaining('hat sich geändert'), findsOneWidget);
    },
  );

  testWidgets('confirming persists the locally computed fingerprint', (
    tester,
  ) async {
    final api = _FakeVerifyApi(
      members: [_member(userId: 2, label: 'Alex', publicJwk: _publicJwk)],
    );
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    await tester.tap(find.text('Als verifiziert markieren'));
    await tester.pumpAndSettle();

    final prefs = await SharedPreferences.getInstance();
    final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');
    expect(await store.fingerprintFor(_baseUrl, 2), _localFingerprint);
  });

  testWidgets('two accounts on the same server do not share verifications', (
    tester,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));
    final member = [_member(userId: 2, label: 'Alex', publicJwk: _publicJwk)];

    // Account 7 verifies Alex.
    final apiA = _FakeVerifyApi(members: member, meAccount: '7');
    await _pumpSheet(tester, api: apiA, session: session);
    await tester.tap(find.text('Als verifiziert markieren'));
    await tester.pumpAndSettle();
    expect(
      await VerifiedKeysStore(
        prefs: prefs,
        accountKey: '7',
      ).fingerprintFor(_baseUrl, 2),
      _localFingerprint,
    );

    // Account 8 opens the sheet for the same colleague: not verified.
    final apiB = _FakeVerifyApi(members: member, meAccount: '8');
    await _pumpSheet(tester, api: apiB, session: session);

    expect(find.text('verifiziert'), findsNothing);
    expect(
      await VerifiedKeysStore(
        prefs: prefs,
        accountKey: '8',
      ).fingerprintFor(_baseUrl, 2),
      isNull,
    );
  });

  testWidgets('account identity is captured immutably across a logout switch', (
    tester,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final api = _FakeVerifyApi(
      members: [_member(userId: 2, label: 'Alex', publicJwk: _publicJwk)],
      meAccount: '7',
    );
    final session = CryptoSession()
      ..unlockWith(Map<String, dynamic>.from(_privateJwk));

    await _pumpSheet(tester, api: api, session: session);

    // The device logs out and a different user signs in mid-session.
    api.meAccount = '8';

    await tester.tap(find.text('Als verifiziert markieren'));
    await tester.pumpAndSettle();

    // The write landed in the originally captured account, never the new one.
    expect(
      await VerifiedKeysStore(
        prefs: prefs,
        accountKey: '7',
      ).fingerprintFor(_baseUrl, 2),
      _localFingerprint,
    );
    expect(
      await VerifiedKeysStore(
        prefs: prefs,
        accountKey: '8',
      ).fingerprintFor(_baseUrl, 2),
      isNull,
    );
  });
}
