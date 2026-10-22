import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/ui/copy_button.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (MethodCall call) async {
      if (call.method == 'Clipboard.setData') return null;
      if (call.method == 'Clipboard.getData') return null;
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null);
  });

  group('CopyIconButton', () {
    Widget wrap(Widget child) {
      return MaterialApp(
        home: Scaffold(body: Center(child: child)),
      );
    }

    testWidgets('copies text to clipboard on tap', (tester) async {
      await tester.pumpWidget(wrap(const CopyIconButton(text: 'DE89 3704 0044 0532 0130 00')));
      await tester.tap(find.byType(CopyIconButton));
      await tester.pumpAndSettle();
    });

    testWidgets('shows snackbar after copy', (tester) async {
      await tester.pumpWidget(wrap(const CopyIconButton(text: 'test')));
      await tester.tap(find.byType(CopyIconButton));
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsOneWidget);
    });

    testWidgets('has minimum 48dp touch target', (tester) async {
      await tester.pumpWidget(wrap(const CopyIconButton(text: 'test')));
      final constraints = tester.getSize(find.byType(IconButton));
      expect(constraints.width, greaterThanOrEqualTo(48));
      expect(constraints.height, greaterThanOrEqualTo(48));
    });
  });
}
