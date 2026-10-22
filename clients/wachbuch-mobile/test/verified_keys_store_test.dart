import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wachbuch_mobile/state/verified_keys_store.dart';

/// Regression tests for the persisted key-verification store (R-020).
///
/// The store keeps only fingerprints (no key material) and namespaces them by
/// **account + server + colleague**. These tests pin the behaviours the
/// verification sheet relies on: per-account/per-server/per-user scoping,
/// key-change detection, revocation, fail-closed handling of legacy/empty
/// state, and survival across instances.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'persists per account + server + user and detects a key change',
    () async {
      final prefs = await SharedPreferences.getInstance();
      final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');

      // First verification is not a "change".
      expect(await store.markVerified('https://s1', 7, 'FP-A'), isFalse);
      expect(await store.fingerprintFor('https://s1', 7), 'FP-A');
      // Same fingerprint again -> still no change.
      expect(await store.markVerified('https://s1', 7, 'FP-A'), isFalse);
      // Different fingerprint for the same user -> key change.
      expect(await store.markVerified('https://s1', 7, 'FP-B'), isTrue);

      // A missing entry is reported as null (never an empty string).
      expect(await store.fingerprintFor('https://s1', 8), isNull);
      expect(await store.fingerprintFor('https://s2', 7), isNull);
    },
  );

  test('is isolated per server', () async {
    final prefs = await SharedPreferences.getInstance();
    final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');
    await store.markVerified('https://s1', 7, 'FP-S1');
    await store.markVerified('https://s2', 7, 'FP-S2');

    expect(await store.fingerprintFor('https://s1', 7), 'FP-S1');
    expect(await store.fingerprintFor('https://s2', 7), 'FP-S2');
    expect((await store.allFor('https://s1')).keys, ['7']);
  });

  test('revoke removes only the addressed entry', () async {
    final prefs = await SharedPreferences.getInstance();
    final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');
    await store.markVerified('https://s1', 7, 'FP-A');
    await store.markVerified('https://s1', 8, 'FP-B');

    await store.remove('https://s1', 7);

    expect(await store.fingerprintFor('https://s1', 7), isNull);
    expect(await store.fingerprintFor('https://s1', 8), 'FP-B');
  });

  test('survives a fresh instance (round-trips through prefs)', () async {
    final prefs = await SharedPreferences.getInstance();
    final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');
    await store.markVerified('https://s1', 7, 'FP-A');

    final reopened = VerifiedKeysStore(prefs: prefs, accountKey: '7');
    expect(await reopened.fingerprintFor('https://s1', 7), 'FP-A');
  });

  test('a corrupt persisted value is treated as empty, not fatal', () async {
    SharedPreferences.setMockInitialValues({
      VerifiedKeysStore.storageKey: '{not json',
    });
    final prefs = await SharedPreferences.getInstance();
    final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');
    expect(await store.allFor('https://s1'), isEmpty);
    expect(await store.markVerified('https://s1', 1, 'FP'), isFalse);
    expect(await store.fingerprintFor('https://s1', 1), 'FP');
  });

  test('an empty account key is fail-closed (no read, no write)', () async {
    final prefs = await SharedPreferences.getInstance();
    final store = VerifiedKeysStore(prefs: prefs, accountKey: '');

    expect(await store.allFor('https://s1'), isEmpty);
    expect(await store.markVerified('https://s1', 7, 'FP-A'), isFalse);

    expect(await store.fingerprintFor('https://s1', 7), isNull);
    expect(prefs.getString(VerifiedKeysStore.storageKey), isNull);
  });

  group('account isolation (server + login user)', () {
    test(
      'A and B do not share verifications for the same server + colleague',
      () async {
        final prefs = await SharedPreferences.getInstance();
        final accountA = VerifiedKeysStore(prefs: prefs, accountKey: '7');
        final accountB = VerifiedKeysStore(prefs: prefs, accountKey: '8');

        await accountA.markVerified('https://s1', 2, 'FP-A');
        // B never sees A's verification for the same server + colleague id.
        expect(await accountB.fingerprintFor('https://s1', 2), isNull);
        expect(await accountB.allFor('https://s1'), isEmpty);

        await accountB.markVerified('https://s1', 2, 'FP-B');
        expect(await accountA.fingerprintFor('https://s1', 2), 'FP-A');
        expect(await accountB.fingerprintFor('https://s1', 2), 'FP-B');

        // Both account namespaces coexist in one persisted document.
        final decoded =
            jsonDecode(prefs.getString(VerifiedKeysStore.storageKey)!)
                as Map<String, dynamic>;
        expect(decoded.keys.toSet(), {'7', '8'});
        expect(decoded['7'], {
          'https://s1': {'2': 'FP-A'},
        });
        expect(decoded['8'], {
          'https://s1': {'2': 'FP-B'},
        });
      },
    );

    test('a write by one account does not clobber another account', () async {
      final prefs = await SharedPreferences.getInstance();
      // Account 7 verifies, then account 8 verifies an unrelated colleague:
      // account 7's entry must survive the (whole-document) persist of account 8.
      await VerifiedKeysStore(
        prefs: prefs,
        accountKey: '7',
      ).markVerified('https://s1', 2, 'FP-A');
      await VerifiedKeysStore(
        prefs: prefs,
        accountKey: '8',
      ).markVerified('https://s1', 3, 'FP-B');

      expect(
        await VerifiedKeysStore(
          prefs: prefs,
          accountKey: '7',
        ).fingerprintFor('https://s1', 2),
        'FP-A',
      );
      expect(
        await VerifiedKeysStore(
          prefs: prefs,
          accountKey: '8',
        ).fingerprintFor('https://s1', 3),
        'FP-B',
      );
      expect(
        await VerifiedKeysStore(
          prefs: prefs,
          accountKey: '8',
        ).fingerprintFor('https://s1', 2),
        isNull,
      );
    });

    test(
      'overlapping stores preserve writes and never resurrect revocations',
      () async {
        final prefs = await SharedPreferences.getInstance();
        final a = VerifiedKeysStore(prefs: prefs, accountKey: '7');
        final b = VerifiedKeysStore(prefs: prefs, accountKey: '8');
        await a.allFor('https://s1');
        await b.allFor('https://s1');
        await Future.wait([
          a.markVerified('https://s1', 2, 'FP-A'),
          b.markVerified('https://s1', 3, 'FP-B'),
        ]);
        expect(
          await VerifiedKeysStore(
            prefs: prefs,
            accountKey: '7',
          ).fingerprintFor('https://s1', 2),
          'FP-A',
        );
        expect(
          await VerifiedKeysStore(
            prefs: prefs,
            accountKey: '8',
          ).fingerprintFor('https://s1', 3),
          'FP-B',
        );
        await a.remove('https://s1', 2);
        await b.markVerified('https://s1', 4, 'FP-C');
        expect(
          await VerifiedKeysStore(
            prefs: prefs,
            accountKey: '7',
          ).fingerprintFor('https://s1', 2),
          isNull,
        );
        expect(
          await VerifiedKeysStore(
            prefs: prefs,
            accountKey: '8',
          ).fingerprintFor('https://s1', 3),
          'FP-B',
        );
      },
    );

    test('legacy (un-scoped) verifications are dropped, not adopted', () async {
      SharedPreferences.setMockInitialValues({
        VerifiedKeysStore.legacyStorageKey: jsonEncode({
          'https://s1': {'2': 'LEGACY'},
        }),
      });
      final prefs = await SharedPreferences.getInstance();
      final store = VerifiedKeysStore(prefs: prefs, accountKey: '7');

      // Fail closed: the old entry is not visible under the new namespace...
      expect(await store.fingerprintFor('https://s1', 2), isNull);
      expect(await store.allFor('https://s1'), isEmpty);
      // ...and the legacy key is purged from disk.
      expect(prefs.getString(VerifiedKeysStore.legacyStorageKey), isNull);
    });

    test(
      'logout race: a captured account key keeps targeting that account',
      () async {
        final prefs = await SharedPreferences.getInstance();
        // The caller captures the account identity of the current login...
        const capturedAccount = '7';
        final boundStore = VerifiedKeysStore(
          prefs: prefs,
          accountKey: capturedAccount,
        );
        await boundStore.markVerified('https://s1', 2, 'FP-A');

        // ...then the device logs out and a different user ('8') signs in. A store
        // built for the new login must not see the captured account's data.
        final afterSwitch = VerifiedKeysStore(prefs: prefs, accountKey: '8');
        expect(await afterSwitch.fingerprintFor('https://s1', 2), isNull);
        // The still-referenced, captured store keeps writing to account '7'.
        await boundStore.markVerified('https://s1', 5, 'FP-C');
        expect(await afterSwitch.fingerprintFor('https://s1', 5), isNull);
        expect(
          await VerifiedKeysStore(
            prefs: prefs,
            accountKey: '7',
          ).fingerprintFor('https://s1', 5),
          'FP-C',
        );
      },
    );
  });
}
