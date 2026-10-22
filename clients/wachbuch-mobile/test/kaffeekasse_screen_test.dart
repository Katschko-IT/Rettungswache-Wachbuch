import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/models/kaffeekasse.dart';
import 'package:wachbuch_mobile/screens/kaffeekasse_screen.dart';

import 'test_localization.dart';

class _KaffeekasseApi extends WachbuchApi {
  _KaffeekasseApi(this.kasse)
      : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  final Kaffeekasse kasse;

  @override
  Future<Kaffeekasse> kaffeekasse() async => kasse;
}

class _ErrorApi extends WachbuchApi {
  _ErrorApi() : super(baseUrl: 'https://wache.example.org', token: 'wb_test');

  @override
  Future<Kaffeekasse> kaffeekasse() async =>
      throw ApiException(503, 'Kaffeekasse nicht erreichbar.');
}

void main() {
  testWidgets('renders balance, payment hint and ledger', (tester) async {
    await tester.pumpWidget(
      localizedApp(
        home: KaffeekasseScreen(
          api: _KaffeekasseApi(Kaffeekasse(
            balance: '12,50 €',
            currency: 'EUR',
            paymentHint: 'PayPal: paypal.me/wache',
            ledger: [
              KaffeekasseEntry(
                id: 1,
                amount: -2,
                description: 'Kaffee',
                userName: 'Michael',
              ),
              KaffeekasseEntry(
                id: 2,
                amount: 10,
                description: 'Einzahlung',
                userName: 'Sandra',
              ),
            ],
          )),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Kaffeekasse'), findsOneWidget);
    expect(find.textContaining('12,50'), findsWidgets);
    expect(find.text('PayPal: paypal.me/wache'), findsOneWidget);
    expect(find.text('Kaffee'), findsOneWidget);
    expect(find.text('Einzahlung'), findsOneWidget);
    expect(find.text('Michael'), findsOneWidget);
  });

  testWidgets('warns when the balance is negative', (tester) async {
    await tester.pumpWidget(
      localizedApp(
        home: KaffeekasseScreen(
          api: _KaffeekasseApi(Kaffeekasse(
            balance: '-5,00 €',
            currency: 'EUR',
            ledger: const [],
          )),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Minus'), findsOneWidget);
  });

  testWidgets('shows empty ledger state', (tester) async {
    await tester.pumpWidget(
      localizedApp(
        home: KaffeekasseScreen(
          api: _KaffeekasseApi(Kaffeekasse(
            balance: '0,00 €',
            currency: 'EUR',
          )),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Noch keine Buchungen.'), findsOneWidget);
  });

  testWidgets('shows an error banner on API failure', (tester) async {
    await tester.pumpWidget(
      localizedApp(home: KaffeekasseScreen(api: _ErrorApi())),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('nicht erreichbar'), findsOneWidget);
  });
}
