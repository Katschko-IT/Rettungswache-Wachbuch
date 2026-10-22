import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';

MaterialApp localizedApp({
  required Widget home,
  Locale locale = const Locale('de'),
  ThemeData? theme,
  TransitionBuilder? builder,
}) {
  return MaterialApp(
    locale: locale,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: theme,
    builder: builder,
    home: home,
  );
}
