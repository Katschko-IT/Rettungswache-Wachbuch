import 'package:flutter/material.dart';

/// Deterministic, field-readable Wachbuch design system.
///
/// The palette follows Material 3 semantics with a calm white/blue identity.
/// Status colors remain semantic and are never used as low-contrast body text.
ThemeData buildWachbuchTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = dark ? _darkScheme : _lightScheme;
  final base = ThemeData(
    brightness: brightness,
    colorScheme: scheme,
    useMaterial3: true,
  );
  final readableText = base.textTheme.copyWith(
    headlineMedium: base.textTheme.headlineMedium?.copyWith(
      fontWeight: FontWeight.w700,
      height: 1.2,
    ),
    headlineSmall: base.textTheme.headlineSmall?.copyWith(
      fontWeight: FontWeight.w700,
      height: 1.25,
    ),
    titleLarge: base.textTheme.titleLarge?.copyWith(
      fontWeight: FontWeight.w700,
      height: 1.25,
    ),
    titleMedium: base.textTheme.titleMedium?.copyWith(
      fontWeight: FontWeight.w600,
      height: 1.3,
    ),
    bodyLarge: base.textTheme.bodyLarge?.copyWith(fontSize: 16, height: 1.5),
    bodyMedium: base.textTheme.bodyMedium?.copyWith(fontSize: 15, height: 1.45),
    bodySmall: base.textTheme.bodySmall?.copyWith(fontSize: 14, height: 1.4),
    labelLarge: base.textTheme.labelLarge?.copyWith(
      fontSize: 14,
      fontWeight: FontWeight.w600,
    ),
    labelMedium: base.textTheme.labelMedium?.copyWith(
      fontSize: 14,
      fontWeight: FontWeight.w600,
    ),
  );
  final cardBorder = dark ? const Color(0xFF263650) : const Color(0xFFDCE4EF);
  final inputBorder = OutlineInputBorder(
    borderRadius: BorderRadius.circular(12),
    borderSide: BorderSide(color: cardBorder),
  );
  final buttonShape = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(12),
  );

  return base.copyWith(
    scaffoldBackgroundColor: dark
        ? const Color(0xFF0B1220)
        : const Color(0xFFF7F9FC),
    textTheme: readableText,
    appBarTheme: AppBarTheme(
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      titleTextStyle: readableText.titleLarge?.copyWith(
        color: scheme.onSurface,
      ),
    ),
    cardTheme: CardThemeData(
      color: dark ? const Color(0xFF121C2E) : Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: cardBorder),
      ),
    ),
    dividerColor: cardBorder,
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface,
      constraints: const BoxConstraints(minHeight: 56),
      border: inputBorder,
      enabledBorder: inputBorder,
      focusedBorder: inputBorder.copyWith(
        borderSide: BorderSide(color: scheme.primary, width: 2),
      ),
      labelStyle: readableText.bodyMedium,
      helperStyle: readableText.bodySmall?.copyWith(
        color: scheme.onSurfaceVariant,
      ),
      errorStyle: readableText.bodySmall?.copyWith(color: scheme.error),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: buttonShape,
        textStyle: readableText.labelLarge,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: buttonShape,
        side: BorderSide(color: scheme.primary),
        textStyle: readableText.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: buttonShape,
        textStyle: readableText.labelLarge,
      ),
    ),
    searchBarTheme: SearchBarThemeData(
      backgroundColor: WidgetStatePropertyAll(scheme.surface),
      surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
      elevation: const WidgetStatePropertyAll(0),
      side: WidgetStatePropertyAll(BorderSide(color: cardBorder)),
      shape: WidgetStatePropertyAll(buttonShape),
      textStyle: WidgetStatePropertyAll(readableText.bodyLarge),
      hintStyle: WidgetStatePropertyAll(
        readableText.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
      ),
      constraints: const BoxConstraints(minHeight: 56),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: scheme.surfaceContainerHighest,
      selectedColor: scheme.primary,
      labelStyle: readableText.labelLarge?.copyWith(color: scheme.onSurface),
      secondaryLabelStyle: readableText.labelLarge?.copyWith(
        color: scheme.onPrimary,
      ),
      side: BorderSide(color: cardBorder),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      height: 76,
      indicatorColor: scheme.primaryContainer,
      iconTheme: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return IconThemeData(
          size: 26,
          color: selected ? scheme.primary : scheme.onSurfaceVariant,
        );
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return readableText.labelMedium?.copyWith(
          color: selected ? scheme.primary : scheme.onSurfaceVariant,
          fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
        );
      }),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: scheme.surface,
      indicatorColor: scheme.primaryContainer,
      selectedIconTheme: IconThemeData(color: scheme.primary, size: 28),
      unselectedIconTheme: IconThemeData(
        color: scheme.onSurfaceVariant,
        size: 26,
      ),
      selectedLabelTextStyle: readableText.labelLarge?.copyWith(
        color: scheme.primary,
      ),
      unselectedLabelTextStyle: readableText.labelLarge?.copyWith(
        color: scheme.onSurfaceVariant,
      ),
    ),
  );
}

const _lightScheme = ColorScheme(
  brightness: Brightness.light,
  primary: Color(0xFF0D47A1),
  onPrimary: Colors.white,
  primaryContainer: Color(0xFFDCEBFF),
  onPrimaryContainer: Color(0xFF082E63),
  secondary: Color(0xFF1565C0),
  onSecondary: Colors.white,
  secondaryContainer: Color(0xFFE3F2FD),
  onSecondaryContainer: Color(0xFF0B3D70),
  tertiary: Color(0xFF425E91),
  onTertiary: Colors.white,
  tertiaryContainer: Color(0xFFE0E8FF),
  onTertiaryContainer: Color(0xFF263F70),
  error: Color(0xFFBA1A1A),
  onError: Colors.white,
  errorContainer: Color(0xFFFFDAD6),
  onErrorContainer: Color(0xFF710B0B),
  surface: Colors.white,
  onSurface: Color(0xFF172033),
  onSurfaceVariant: Color(0xFF445066),
  outline: Color(0xFF6F7A8F),
  outlineVariant: Color(0xFFDCE4EF),
  shadow: Color(0xFF000000),
  scrim: Color(0xFF000000),
  inverseSurface: Color(0xFF2D3443),
  onInverseSurface: Color(0xFFF1F3F8),
  inversePrimary: Color(0xFF9ECAFF),
  surfaceTint: Color(0xFF0D47A1),
);

const _darkScheme = ColorScheme(
  brightness: Brightness.dark,
  primary: Color(0xFF9ECAFF),
  onPrimary: Color(0xFF00315D),
  primaryContainer: Color(0xFF164B78),
  onPrimaryContainer: Color(0xFFD3E5FF),
  secondary: Color(0xFFA8CAFF),
  onSecondary: Color(0xFF00315D),
  secondaryContainer: Color(0xFF1B3E67),
  onSecondaryContainer: Color(0xFFD6E7FF),
  tertiary: Color(0xFFBBC8F7),
  onTertiary: Color(0xFF243257),
  tertiaryContainer: Color(0xFF3A4970),
  onTertiaryContainer: Color(0xFFDDE2FF),
  error: Color(0xFFFFB4AB),
  onError: Color(0xFF690005),
  errorContainer: Color(0xFF93000A),
  onErrorContainer: Color(0xFFFFDAD6),
  surface: Color(0xFF0B1220),
  onSurface: Color(0xFFE5EAF3),
  onSurfaceVariant: Color(0xFFC2CAD8),
  outline: Color(0xFF8C96A8),
  outlineVariant: Color(0xFF3E495D),
  shadow: Color(0xFF000000),
  scrim: Color(0xFF000000),
  inverseSurface: Color(0xFFE5EAF3),
  onInverseSurface: Color(0xFF263044),
  inversePrimary: Color(0xFF0D47A1),
  surfaceTint: Color(0xFF9ECAFF),
);
