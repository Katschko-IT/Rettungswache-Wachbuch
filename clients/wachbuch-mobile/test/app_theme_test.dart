import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wachbuch_mobile/theme/app_theme.dart';
import 'package:wachbuch_mobile/theme/design_tokens.dart';
import 'package:wachbuch_mobile/theme/high_contrast_theme.dart';

void main() {
  test('light theme uses deterministic white-blue design tokens', () {
    final theme = buildWachbuchTheme(Brightness.light);

    expect(theme.useMaterial3, isTrue);
    expect(theme.colorScheme.primary, const Color(0xFF0D47A1));
    expect(theme.scaffoldBackgroundColor, const Color(0xFFF7F9FC));
    expect(theme.cardTheme.color, Colors.white);
    expect(theme.textTheme.bodySmall?.fontSize, greaterThanOrEqualTo(14));
    expect(theme.textTheme.labelMedium?.fontSize, greaterThanOrEqualTo(14));
  });

  test('dark theme keeps readable blue accents and opaque surfaces', () {
    final theme = buildWachbuchTheme(Brightness.dark);

    expect(theme.colorScheme.primary, const Color(0xFF9ECAFF));
    expect(theme.scaffoldBackgroundColor, const Color(0xFF0B1220));
    expect(theme.cardTheme.color, const Color(0xFF121C2E));
    expect(theme.colorScheme.surface.a, 1.0);
  });

  test('interactive controls use accessible minimum heights', () {
    final theme = buildWachbuchTheme(Brightness.light);

    expect(theme.filledButtonTheme.style?.minimumSize?.resolve({})?.height, 52);
    expect(
      theme.outlinedButtonTheme.style?.minimumSize?.resolve({})?.height,
      52,
    );
    expect(theme.inputDecorationTheme.constraints?.minHeight, 56);
  });

  test('high contrast emergency themes stay black and white', () {
    final light = HighContrastTheme.light();
    final dark = HighContrastTheme.dark();

    expect(light.colorScheme.primary, const Color(0xFF000000));
    expect(light.colorScheme.surface, const Color(0xFFFFFFFF));
    expect(light.colorScheme.onSurface, const Color(0xFF000000));
    expect(dark.colorScheme.primary, const Color(0xFFFFFFFF));
    expect(dark.colorScheme.surface, const Color(0xFF000000));
    expect(dark.colorScheme.onSurface, const Color(0xFFFFFFFF));
    expect(
      light.elevatedButtonTheme.style?.minimumSize?.resolve({})?.height,
      WachbuchTokens.touchTarget,
    );
  });

  test('shared tokens match the web PWA palette', () {
    expect(WachbuchTokens.primary, const Color(0xFF0D47A1));
    expect(WachbuchTokens.surfaceLight, const Color(0xFFF7F9FC));
    expect(WachbuchTokens.surfaceDark, const Color(0xFF0B1220));
    expect(WachbuchTokens.brandHover, const Color(0xFF082E63));
    expect(WachbuchTokens.brandDeep, const Color(0xFF17343D));
    expect(WachbuchTokens.brandAccent, const Color(0xFF2563EB));
  });
}
