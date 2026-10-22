import 'package:flutter/material.dart';

import 'design_tokens.dart';

class HighContrastTheme {
  HighContrastTheme._();

  static ThemeData light() {
    final base = ThemeData.light(useMaterial3: true);
    return base.copyWith(
      colorScheme: const ColorScheme.highContrastLight(
        primary: Color(0xFF000000),
        onPrimary: Color(0xFFFFFFFF),
        secondary: Color(0xFF000000),
        onSecondary: Color(0xFFFFFFFF),
        surface: Color(0xFFFFFFFF),
        onSurface: Color(0xFF000000),
        error: Color(0xFFB91C1C),
        onError: Color(0xFFFFFFFF),
      ),
      textTheme: base.textTheme.copyWith(
        bodySmall: base.textTheme.bodySmall?.copyWith(fontSize: WachbuchTokens.textBody),
        bodyMedium: base.textTheme.bodyMedium?.copyWith(fontSize: WachbuchTokens.textBody + 2),
        bodyLarge: base.textTheme.bodyLarge?.copyWith(fontSize: WachbuchTokens.textTitle),
        titleSmall: base.textTheme.titleSmall?.copyWith(fontSize: WachbuchTokens.textTitle),
        titleMedium: base.textTheme.titleMedium?.copyWith(fontSize: WachbuchTokens.textHeadline),
        titleLarge: base.textTheme.titleLarge?.copyWith(fontSize: WachbuchTokens.textHeadline + 4),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          minimumSize: const Size(64, WachbuchTokens.touchTarget),
          textStyle: const TextStyle(fontWeight: FontWeight.bold),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(64, WachbuchTokens.touchTarget),
          side: const BorderSide(color: Color(0xFF000000), width: 2),
        ),
      ),
      cardTheme: CardThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(WachbuchTokens.radiusMd),
          side: const BorderSide(color: Color(0xFF000000), width: 1),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFF000000),
        foregroundColor: Color(0xFFFFFFFF),
      ),
    );
  }

  static ThemeData dark() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      colorScheme: const ColorScheme.highContrastDark(
        primary: Color(0xFFFFFFFF),
        onPrimary: Color(0xFF000000),
        secondary: Color(0xFFFFFFFF),
        onSecondary: Color(0xFF000000),
        surface: Color(0xFF000000),
        onSurface: Color(0xFFFFFFFF),
        error: Color(0xFFFF6B6B),
        onError: Color(0xFF000000),
      ),
      textTheme: base.textTheme.copyWith(
        bodySmall: base.textTheme.bodySmall?.copyWith(fontSize: WachbuchTokens.textBody),
        bodyMedium: base.textTheme.bodyMedium?.copyWith(fontSize: WachbuchTokens.textBody + 2),
        bodyLarge: base.textTheme.bodyLarge?.copyWith(fontSize: WachbuchTokens.textTitle),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          minimumSize: const Size(64, WachbuchTokens.touchTarget),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFFFFFFFF),
        foregroundColor: Color(0xFF000000),
      ),
    );
  }
}
