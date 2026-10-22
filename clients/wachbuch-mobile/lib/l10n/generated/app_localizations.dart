import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_de.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('de'),
    Locale('en'),
  ];

  /// No description provided for @appName.
  ///
  /// In de, this message translates to:
  /// **'Wachbuch'**
  String get appName;

  /// No description provided for @errorSemanticsLabel.
  ///
  /// In de, this message translates to:
  /// **'Fehler: {message}'**
  String errorSemanticsLabel(String message);

  /// No description provided for @commonCancel.
  ///
  /// In de, this message translates to:
  /// **'Abbrechen'**
  String get commonCancel;

  /// No description provided for @commonSwitch.
  ///
  /// In de, this message translates to:
  /// **'Wechseln'**
  String get commonSwitch;

  /// No description provided for @commonSave.
  ///
  /// In de, this message translates to:
  /// **'Speichern'**
  String get commonSave;

  /// No description provided for @commonClose.
  ///
  /// In de, this message translates to:
  /// **'Schließen'**
  String get commonClose;

  /// No description provided for @commonRetry.
  ///
  /// In de, this message translates to:
  /// **'Erneut versuchen'**
  String get commonRetry;

  /// No description provided for @noticeSessionExpired.
  ///
  /// In de, this message translates to:
  /// **'Ihre Anmeldung ist abgelaufen. Bitte erneut anmelden.'**
  String get noticeSessionExpired;

  /// No description provided for @noticeSessionEnded.
  ///
  /// In de, this message translates to:
  /// **'Sitzung beendet. Bitte erneut anmelden.'**
  String get noticeSessionEnded;

  /// No description provided for @serverSwitchTitle.
  ///
  /// In de, this message translates to:
  /// **'Server wechseln?'**
  String get serverSwitchTitle;

  /// No description provided for @serverSwitchMessage.
  ///
  /// In de, this message translates to:
  /// **'Ein Link möchte die App auf\n{url}\numstellen. Die aktuelle Anmeldung wird dabei beendet.'**
  String serverSwitchMessage(String url);

  /// No description provided for @navOverview.
  ///
  /// In de, this message translates to:
  /// **'Übersicht'**
  String get navOverview;

  /// No description provided for @navHandovers.
  ///
  /// In de, this message translates to:
  /// **'Übergaben'**
  String get navHandovers;

  /// No description provided for @navAccount.
  ///
  /// In de, this message translates to:
  /// **'Konto'**
  String get navAccount;

  /// No description provided for @refreshTooltip.
  ///
  /// In de, this message translates to:
  /// **'Aktualisieren'**
  String get refreshTooltip;

  /// No description provided for @stationFallback.
  ///
  /// In de, this message translates to:
  /// **'Wachbuch'**
  String get stationFallback;

  /// No description provided for @sessionExpiredError.
  ///
  /// In de, this message translates to:
  /// **'Anmeldung abgelaufen oder widerrufen.'**
  String get sessionExpiredError;

  /// No description provided for @overviewActiveHandovers.
  ///
  /// In de, this message translates to:
  /// **'Aktive Übergaben'**
  String get overviewActiveHandovers;

  /// No description provided for @metricOpen.
  ///
  /// In de, this message translates to:
  /// **'offen'**
  String get metricOpen;

  /// No description provided for @metricInProgress.
  ///
  /// In de, this message translates to:
  /// **'in Bearbeitung'**
  String get metricInProgress;

  /// No description provided for @metricUrgent.
  ///
  /// In de, this message translates to:
  /// **'dringend'**
  String get metricUrgent;

  /// No description provided for @overviewModulesTitle.
  ///
  /// In de, this message translates to:
  /// **'Module dieser Wache'**
  String get overviewModulesTitle;

  /// No description provided for @overviewModulesHint.
  ///
  /// In de, this message translates to:
  /// **'Ihre Wache und die verfügbaren Module werden automatisch aus Ihrem Benutzerkonto geladen.'**
  String get overviewModulesHint;

  /// No description provided for @moduleCalendarTitle.
  ///
  /// In de, this message translates to:
  /// **'Kalender'**
  String get moduleCalendarTitle;

  /// No description provided for @moduleCalendarSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Wachentermine und Dienste'**
  String get moduleCalendarSubtitle;

  /// No description provided for @moduleCoffeeTitle.
  ///
  /// In de, this message translates to:
  /// **'Kaffeekasse'**
  String get moduleCoffeeTitle;

  /// No description provided for @moduleCoffeeSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Kassenstand und Buchungen'**
  String get moduleCoffeeSubtitle;

  /// No description provided for @moduleChecklistsTitle.
  ///
  /// In de, this message translates to:
  /// **'Checklisten'**
  String get moduleChecklistsTitle;

  /// No description provided for @moduleChecklistsSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Punkte abhaken und abschließen'**
  String get moduleChecklistsSubtitle;

  /// No description provided for @moduleDefectsTitle.
  ///
  /// In de, this message translates to:
  /// **'Mängel'**
  String get moduleDefectsTitle;

  /// No description provided for @moduleDefectsSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Offene Punkte mit Owner und Frist'**
  String get moduleDefectsSubtitle;

  /// No description provided for @moduleAssetsTitle.
  ///
  /// In de, this message translates to:
  /// **'Geräte'**
  String get moduleAssetsTitle;

  /// No description provided for @moduleAssetsSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Fahrzeug- und Gerätestatus der Wache'**
  String get moduleAssetsSubtitle;

  /// No description provided for @moduleReportsTitle.
  ///
  /// In de, this message translates to:
  /// **'Auswertung'**
  String get moduleReportsTitle;

  /// No description provided for @moduleReportsSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Mängel, Fälligkeiten und Einsatzklar-Quote'**
  String get moduleReportsSubtitle;

  /// No description provided for @quickAccessTitle.
  ///
  /// In de, this message translates to:
  /// **'Schnellzugriff'**
  String get quickAccessTitle;

  /// No description provided for @defectsTitle.
  ///
  /// In de, this message translates to:
  /// **'Mängel'**
  String get defectsTitle;

  /// No description provided for @defectsHint.
  ///
  /// In de, this message translates to:
  /// **'Offene Punkte aus dem Wachalltag — Status und Zuständigkeit nachvollziehbar halten.'**
  String get defectsHint;

  /// No description provided for @defectsEmpty.
  ///
  /// In de, this message translates to:
  /// **'Keine Mängel für diesen Filter.'**
  String get defectsEmpty;

  /// No description provided for @defectAdd.
  ///
  /// In de, this message translates to:
  /// **'Mangel anlegen'**
  String get defectAdd;

  /// No description provided for @defectCreateTitle.
  ///
  /// In de, this message translates to:
  /// **'Neuen Mangel anlegen'**
  String get defectCreateTitle;

  /// No description provided for @defectTitleLabel.
  ///
  /// In de, this message translates to:
  /// **'Titel'**
  String get defectTitleLabel;

  /// No description provided for @defectDescriptionLabel.
  ///
  /// In de, this message translates to:
  /// **'Beschreibung'**
  String get defectDescriptionLabel;

  /// No description provided for @defectCategoryLabel.
  ///
  /// In de, this message translates to:
  /// **'Kategorie'**
  String get defectCategoryLabel;

  /// No description provided for @defectPriorityLabel.
  ///
  /// In de, this message translates to:
  /// **'Priorität'**
  String get defectPriorityLabel;

  /// No description provided for @defectAssetLabel.
  ///
  /// In de, this message translates to:
  /// **'Bezug'**
  String get defectAssetLabel;

  /// No description provided for @defectOwnerLabel.
  ///
  /// In de, this message translates to:
  /// **'Zuständig'**
  String get defectOwnerLabel;

  /// No description provided for @defectOwnerSelf.
  ///
  /// In de, this message translates to:
  /// **'Mir zuordnen'**
  String get defectOwnerSelf;

  /// No description provided for @defectDueLabel.
  ///
  /// In de, this message translates to:
  /// **'Frist'**
  String get defectDueLabel;

  /// No description provided for @defectSetStatus.
  ///
  /// In de, this message translates to:
  /// **'Status setzen'**
  String get defectSetStatus;

  /// No description provided for @defectStatusWaiting.
  ///
  /// In de, this message translates to:
  /// **'Wartend'**
  String get defectStatusWaiting;

  /// No description provided for @defectCreateFailed.
  ///
  /// In de, this message translates to:
  /// **'Mangel konnte nicht angelegt werden.'**
  String get defectCreateFailed;

  /// No description provided for @defectPhotosTitle.
  ///
  /// In de, this message translates to:
  /// **'Fotos'**
  String get defectPhotosTitle;

  /// No description provided for @defectPhotosHint.
  ///
  /// In de, this message translates to:
  /// **'Nur Zustandsbilder des Mangels. Keine Patienten- oder Einsatzdaten fotografieren.'**
  String get defectPhotosHint;

  /// No description provided for @defectPhotosEmpty.
  ///
  /// In de, this message translates to:
  /// **'Noch keine Fotos.'**
  String get defectPhotosEmpty;

  /// No description provided for @defectAddPhoto.
  ///
  /// In de, this message translates to:
  /// **'Foto hinzufügen'**
  String get defectAddPhoto;

  /// No description provided for @defectTakePhoto.
  ///
  /// In de, this message translates to:
  /// **'Kamera'**
  String get defectTakePhoto;

  /// No description provided for @defectChoosePhoto.
  ///
  /// In de, this message translates to:
  /// **'Fotomediathek'**
  String get defectChoosePhoto;

  /// No description provided for @defectPhotoUploadFailed.
  ///
  /// In de, this message translates to:
  /// **'Foto konnte nicht hochgeladen werden.'**
  String get defectPhotoUploadFailed;

  /// No description provided for @defectPhotoTooLarge.
  ///
  /// In de, this message translates to:
  /// **'Das Bild darf maximal 2 MiB groß sein.'**
  String get defectPhotoTooLarge;

  /// No description provided for @defectPhotoUploaded.
  ///
  /// In de, this message translates to:
  /// **'Foto wurde hochgeladen.'**
  String get defectPhotoUploaded;

  /// No description provided for @assetsBoardTitle.
  ///
  /// In de, this message translates to:
  /// **'Fahrzeug- & Gerätestatus'**
  String get assetsBoardTitle;

  /// No description provided for @assetsScreenTitle.
  ///
  /// In de, this message translates to:
  /// **'Geräte & Status'**
  String get assetsScreenTitle;

  /// No description provided for @assetsEmpty.
  ///
  /// In de, this message translates to:
  /// **'Keine Geräte oder Pools verfügbar.'**
  String get assetsEmpty;

  /// No description provided for @assetStatusReady.
  ///
  /// In de, this message translates to:
  /// **'Einsatzklar'**
  String get assetStatusReady;

  /// No description provided for @assetStatusLimited.
  ///
  /// In de, this message translates to:
  /// **'Eingeschränkt'**
  String get assetStatusLimited;

  /// No description provided for @assetStatusOob.
  ///
  /// In de, this message translates to:
  /// **'Außer Betrieb'**
  String get assetStatusOob;

  /// No description provided for @assetStatusWorkshop.
  ///
  /// In de, this message translates to:
  /// **'Werkstatt'**
  String get assetStatusWorkshop;

  /// No description provided for @inventoryTitle.
  ///
  /// In de, this message translates to:
  /// **'Schlüssel & Pools'**
  String get inventoryTitle;

  /// No description provided for @inventoryHint.
  ///
  /// In de, this message translates to:
  /// **'Checkout / Checkin für Pool-Geräte und Schlüssel.'**
  String get inventoryHint;

  /// No description provided for @inventoryAvailable.
  ///
  /// In de, this message translates to:
  /// **'Verfügbar'**
  String get inventoryAvailable;

  /// No description provided for @inventoryHolderLabel.
  ///
  /// In de, this message translates to:
  /// **'Bei'**
  String get inventoryHolderLabel;

  /// No description provided for @inventoryCheckout.
  ///
  /// In de, this message translates to:
  /// **'Ausgeben'**
  String get inventoryCheckout;

  /// No description provided for @inventoryCheckin.
  ///
  /// In de, this message translates to:
  /// **'Zurückgeben'**
  String get inventoryCheckin;

  /// No description provided for @checklistIntervalDaily.
  ///
  /// In de, this message translates to:
  /// **'Täglich'**
  String get checklistIntervalDaily;

  /// No description provided for @checklistIntervalWeekly.
  ///
  /// In de, this message translates to:
  /// **'Wöchentlich'**
  String get checklistIntervalWeekly;

  /// No description provided for @checklistIntervalMonthly.
  ///
  /// In de, this message translates to:
  /// **'Monatlich'**
  String get checklistIntervalMonthly;

  /// No description provided for @checklistDueToday.
  ///
  /// In de, this message translates to:
  /// **'Fällig heute'**
  String get checklistDueToday;

  /// No description provided for @checklistOverdue.
  ///
  /// In de, this message translates to:
  /// **'Überfällig'**
  String get checklistOverdue;

  /// No description provided for @checklistDueSection.
  ///
  /// In de, this message translates to:
  /// **'Fällig heute / überfällig'**
  String get checklistDueSection;

  /// No description provided for @reportsTitle.
  ///
  /// In de, this message translates to:
  /// **'Auswertung'**
  String get reportsTitle;

  /// No description provided for @reportsHint.
  ///
  /// In de, this message translates to:
  /// **'Leichte Stationsübersicht ohne individuelle Leistungsbewertung.'**
  String get reportsHint;

  /// No description provided for @reportsOpenDefects.
  ///
  /// In de, this message translates to:
  /// **'Offene Mängel'**
  String get reportsOpenDefects;

  /// No description provided for @reportsOverdueDefects.
  ///
  /// In de, this message translates to:
  /// **'Mängel überfällig'**
  String get reportsOverdueDefects;

  /// No description provided for @reportsOverdueChecks.
  ///
  /// In de, this message translates to:
  /// **'Checks überfällig'**
  String get reportsOverdueChecks;

  /// No description provided for @reportsAssetReady.
  ///
  /// In de, this message translates to:
  /// **'Assets einsatzklar'**
  String get reportsAssetReady;

  /// No description provided for @reportsInventoryOut.
  ///
  /// In de, this message translates to:
  /// **'Pools ausgegeben'**
  String get reportsInventoryOut;

  /// No description provided for @reportsUnacked.
  ///
  /// In de, this message translates to:
  /// **'Unquittierte Übergaben'**
  String get reportsUnacked;

  /// No description provided for @reportsOldestOpen.
  ///
  /// In de, this message translates to:
  /// **'Ältester offener Mangel'**
  String get reportsOldestOpen;

  /// No description provided for @reportsDays.
  ///
  /// In de, this message translates to:
  /// **'Tage'**
  String get reportsDays;

  /// No description provided for @reportsByOwner.
  ///
  /// In de, this message translates to:
  /// **'Offene Mängel nach Zuständigkeit'**
  String get reportsByOwner;

  /// No description provided for @reportsNoOwner.
  ///
  /// In de, this message translates to:
  /// **'Ohne Zuständigkeit'**
  String get reportsNoOwner;

  /// No description provided for @reportsPrivacyHint.
  ///
  /// In de, this message translates to:
  /// **'Diese Auswertung dient der Stationsorganisation, nicht zur Leistungsbewertung einzelner Beschäftigter.'**
  String get reportsPrivacyHint;

  /// No description provided for @handoverAckButton.
  ///
  /// In de, this message translates to:
  /// **'Übernommen'**
  String get handoverAckButton;

  /// No description provided for @handoverAckDone.
  ///
  /// In de, this message translates to:
  /// **'Von Ihnen quittiert'**
  String get handoverAckDone;

  /// No description provided for @handoverAckListTitle.
  ///
  /// In de, this message translates to:
  /// **'Quittierungen'**
  String get handoverAckListTitle;

  /// No description provided for @handoverAckEmpty.
  ///
  /// In de, this message translates to:
  /// **'Noch nicht quittiert.'**
  String get handoverAckEmpty;

  /// No description provided for @handoverAckFailed.
  ///
  /// In de, this message translates to:
  /// **'Quittierung fehlgeschlagen.'**
  String get handoverAckFailed;

  /// No description provided for @handoverSearchHint.
  ///
  /// In de, this message translates to:
  /// **'Übergaben durchsuchen'**
  String get handoverSearchHint;

  /// No description provided for @handoverSearchClear.
  ///
  /// In de, this message translates to:
  /// **'Suche löschen'**
  String get handoverSearchClear;

  /// No description provided for @filterStatus.
  ///
  /// In de, this message translates to:
  /// **'Status'**
  String get filterStatus;

  /// No description provided for @filterPriority.
  ///
  /// In de, this message translates to:
  /// **'Priorität'**
  String get filterPriority;

  /// No description provided for @handoversCount.
  ///
  /// In de, this message translates to:
  /// **'{count} von {total} Übergaben'**
  String handoversCount(int count, int total);

  /// No description provided for @filterSectionLabel.
  ///
  /// In de, this message translates to:
  /// **'{title} filtern'**
  String filterSectionLabel(String title);

  /// No description provided for @handoversNoneActive.
  ///
  /// In de, this message translates to:
  /// **'Keine aktiven Übergaben.'**
  String get handoversNoneActive;

  /// No description provided for @handoversNoneForFilter.
  ///
  /// In de, this message translates to:
  /// **'Keine Übergaben für diese Filter.'**
  String get handoversNoneForFilter;

  /// No description provided for @handoverUntitled.
  ///
  /// In de, this message translates to:
  /// **'ohne Titel'**
  String get handoverUntitled;

  /// No description provided for @handoverFallback.
  ///
  /// In de, this message translates to:
  /// **'Übergabe'**
  String get handoverFallback;

  /// No description provided for @handoverOpenSemantics.
  ///
  /// In de, this message translates to:
  /// **'Übergabe {title} öffnen'**
  String handoverOpenSemantics(String title);

  /// No description provided for @detailsLoadFailed.
  ///
  /// In de, this message translates to:
  /// **'Details konnten nicht geladen werden.'**
  String get detailsLoadFailed;

  /// No description provided for @detailsNoFurtherInfo.
  ///
  /// In de, this message translates to:
  /// **'Keine weiteren Angaben.'**
  String get detailsNoFurtherInfo;

  /// No description provided for @detailsUpdatedAt.
  ///
  /// In de, this message translates to:
  /// **'Aktualisiert {timestamp}'**
  String detailsUpdatedAt(String timestamp);

  /// No description provided for @detailsVersion.
  ///
  /// In de, this message translates to:
  /// **'Version {version}'**
  String detailsVersion(String version);

  /// No description provided for @accountLoggedInAs.
  ///
  /// In de, this message translates to:
  /// **'Angemeldet als'**
  String get accountLoggedInAs;

  /// No description provided for @accountServer.
  ///
  /// In de, this message translates to:
  /// **'Server'**
  String get accountServer;

  /// No description provided for @accountLicense.
  ///
  /// In de, this message translates to:
  /// **'Lizenz'**
  String get accountLicense;

  /// No description provided for @accountLicenseValue.
  ///
  /// In de, this message translates to:
  /// **'AGPL-3.0-or-later · Quellcode offen'**
  String get accountLicenseValue;

  /// No description provided for @accountRefreshProfile.
  ///
  /// In de, this message translates to:
  /// **'Profil aktualisieren'**
  String get accountRefreshProfile;

  /// No description provided for @accountLogout.
  ///
  /// In de, this message translates to:
  /// **'Abmelden'**
  String get accountLogout;

  /// No description provided for @accountChangeServer.
  ///
  /// In de, this message translates to:
  /// **'Anderen Server einrichten'**
  String get accountChangeServer;

  /// No description provided for @kalenderTitle.
  ///
  /// In de, this message translates to:
  /// **'Kalender'**
  String get kalenderTitle;

  /// No description provided for @kalenderEmpty.
  ///
  /// In de, this message translates to:
  /// **'Keine anstehenden Termine.'**
  String get kalenderEmpty;

  /// No description provided for @kalenderEntryFallback.
  ///
  /// In de, this message translates to:
  /// **'Termin'**
  String get kalenderEntryFallback;

  /// No description provided for @kalenderTimeTbd.
  ///
  /// In de, this message translates to:
  /// **'Zeit folgt'**
  String get kalenderTimeTbd;

  /// No description provided for @kalenderAllDay.
  ///
  /// In de, this message translates to:
  /// **'Ganztägig'**
  String get kalenderAllDay;

  /// No description provided for @kaffeekasseTitle.
  ///
  /// In de, this message translates to:
  /// **'Kaffeekasse'**
  String get kaffeekasseTitle;

  /// No description provided for @kaffeekasseBalanceLabel.
  ///
  /// In de, this message translates to:
  /// **'Aktueller Kassenstand'**
  String get kaffeekasseBalanceLabel;

  /// No description provided for @kaffeekasseNegative.
  ///
  /// In de, this message translates to:
  /// **'Die Kasse ist im Minus – bitte nachzahlen.'**
  String get kaffeekasseNegative;

  /// No description provided for @kaffeekasseLastTransactions.
  ///
  /// In de, this message translates to:
  /// **'Letzte Buchungen'**
  String get kaffeekasseLastTransactions;

  /// No description provided for @kaffeekasseEmptyLedger.
  ///
  /// In de, this message translates to:
  /// **'Noch keine Buchungen.'**
  String get kaffeekasseEmptyLedger;

  /// No description provided for @kaffeekasseEntryFallback.
  ///
  /// In de, this message translates to:
  /// **'Buchung'**
  String get kaffeekasseEntryFallback;

  /// No description provided for @checklistenTitle.
  ///
  /// In de, this message translates to:
  /// **'Checklisten'**
  String get checklistenTitle;

  /// No description provided for @checklistenEmpty.
  ///
  /// In de, this message translates to:
  /// **'Keine Checklisten verfügbar.'**
  String get checklistenEmpty;

  /// No description provided for @checklistFallback.
  ///
  /// In de, this message translates to:
  /// **'Checkliste'**
  String get checklistFallback;

  /// No description provided for @checklistNoItems.
  ///
  /// In de, this message translates to:
  /// **'Keine Punkte.'**
  String get checklistNoItems;

  /// No description provided for @checklistCompleteButton.
  ///
  /// In de, this message translates to:
  /// **'Checkliste abschließen'**
  String get checklistCompleteButton;

  /// No description provided for @checklistItemFallback.
  ///
  /// In de, this message translates to:
  /// **'Punkt'**
  String get checklistItemFallback;

  /// No description provided for @checklistCompletedAt.
  ///
  /// In de, this message translates to:
  /// **'Abgeschlossen {timestamp}'**
  String checklistCompletedAt(String timestamp);

  /// No description provided for @loginAppBarTitle.
  ///
  /// In de, this message translates to:
  /// **'Anmelden'**
  String get loginAppBarTitle;

  /// No description provided for @loginChangeServer.
  ///
  /// In de, this message translates to:
  /// **'Server ändern'**
  String get loginChangeServer;

  /// No description provided for @loginHeading.
  ///
  /// In de, this message translates to:
  /// **'Anmeldung'**
  String get loginHeading;

  /// No description provided for @loginTokenLabel.
  ///
  /// In de, this message translates to:
  /// **'App-Token (wb_…)'**
  String get loginTokenLabel;

  /// No description provided for @loginTokenHelper.
  ///
  /// In de, this message translates to:
  /// **'Aus dem Web unter /konto/api/ – nötig bei MFA'**
  String get loginTokenHelper;

  /// No description provided for @loginTokenRequired.
  ///
  /// In de, this message translates to:
  /// **'Token erforderlich'**
  String get loginTokenRequired;

  /// No description provided for @loginUsername.
  ///
  /// In de, this message translates to:
  /// **'Benutzername'**
  String get loginUsername;

  /// No description provided for @loginUsernameRequired.
  ///
  /// In de, this message translates to:
  /// **'Benutzername erforderlich'**
  String get loginUsernameRequired;

  /// No description provided for @loginPassword.
  ///
  /// In de, this message translates to:
  /// **'Passwort'**
  String get loginPassword;

  /// No description provided for @loginPasswordRequired.
  ///
  /// In de, this message translates to:
  /// **'Passwort erforderlich'**
  String get loginPasswordRequired;

  /// No description provided for @loginShow.
  ///
  /// In de, this message translates to:
  /// **'Anzeigen'**
  String get loginShow;

  /// No description provided for @loginHide.
  ///
  /// In de, this message translates to:
  /// **'Verbergen'**
  String get loginHide;

  /// No description provided for @loginSubmit.
  ///
  /// In de, this message translates to:
  /// **'Anmelden'**
  String get loginSubmit;

  /// No description provided for @loginUseCredentials.
  ///
  /// In de, this message translates to:
  /// **'Mit Benutzername und Passwort'**
  String get loginUseCredentials;

  /// No description provided for @loginUseToken.
  ///
  /// In de, this message translates to:
  /// **'Stattdessen App-Token nutzen'**
  String get loginUseToken;

  /// No description provided for @loginTokenPasteHint.
  ///
  /// In de, this message translates to:
  /// **'Bitte App-Token einfügen (aus /konto/api/).'**
  String get loginTokenPasteHint;

  /// No description provided for @loginMfaHint.
  ///
  /// In de, this message translates to:
  /// **'Bei Zwei-Faktor: App-Token im Web unter Mein Konto → App-Tokens erzeugen.'**
  String get loginMfaHint;

  /// No description provided for @loginInvalidInput.
  ///
  /// In de, this message translates to:
  /// **'Ungültige Eingabe.'**
  String get loginInvalidInput;

  /// No description provided for @setupServerAddressTitle.
  ///
  /// In de, this message translates to:
  /// **'Server-Adresse Ihrer Wache'**
  String get setupServerAddressTitle;

  /// No description provided for @setupHint.
  ///
  /// In de, this message translates to:
  /// **'Geben Sie die Adresse ein oder scannen Sie den QR-Code aus dem Web.'**
  String get setupHint;

  /// No description provided for @setupAddressLabel.
  ///
  /// In de, this message translates to:
  /// **'Adresse'**
  String get setupAddressLabel;

  /// No description provided for @setupAddressHint.
  ///
  /// In de, this message translates to:
  /// **'https://wache.example.org'**
  String get setupAddressHint;

  /// No description provided for @setupScanQr.
  ///
  /// In de, this message translates to:
  /// **'QR-Code scannen'**
  String get setupScanQr;

  /// No description provided for @setupAddressRequired.
  ///
  /// In de, this message translates to:
  /// **'Adresse eingeben'**
  String get setupAddressRequired;

  /// No description provided for @setupAddressInvalid.
  ///
  /// In de, this message translates to:
  /// **'Ungültige Adresse'**
  String get setupAddressInvalid;

  /// No description provided for @setupConfirm.
  ///
  /// In de, this message translates to:
  /// **'Bestätigen'**
  String get setupConfirm;

  /// No description provided for @setupFooter.
  ///
  /// In de, this message translates to:
  /// **'Play-Store-Client: Verbindung nur zu Ihrem selbst gehosteten Server. Produktion: HTTPS erforderlich.'**
  String get setupFooter;

  /// No description provided for @setupDemoButton.
  ///
  /// In de, this message translates to:
  /// **'Demo-Modus ausprobieren'**
  String get setupDemoButton;

  /// No description provided for @setupDemoTitle.
  ///
  /// In de, this message translates to:
  /// **'Demo-Modus wählen'**
  String get setupDemoTitle;

  /// No description provided for @setupDemoSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Lokale Musterdaten ohne Server — für Rettungsdienst, Feuerwehr, FFW oder Polizei.'**
  String get setupDemoSubtitle;

  /// No description provided for @setupDemoRettungsdienst.
  ///
  /// In de, this message translates to:
  /// **'Rettungsdienst'**
  String get setupDemoRettungsdienst;

  /// No description provided for @setupDemoRettungsdienstHint.
  ///
  /// In de, this message translates to:
  /// **'Schichtübergabe & Material auf der Rettungswache'**
  String get setupDemoRettungsdienstHint;

  /// No description provided for @setupDemoFeuerwehr.
  ///
  /// In de, this message translates to:
  /// **'Feuerwehr'**
  String get setupDemoFeuerwehr;

  /// No description provided for @setupDemoFeuerwehrHint.
  ///
  /// In de, this message translates to:
  /// **'Gerätehaus, Fahrzeuge und Dienstübergabe'**
  String get setupDemoFeuerwehrHint;

  /// No description provided for @setupDemoFfw.
  ///
  /// In de, this message translates to:
  /// **'Freiwillige Feuerwehr'**
  String get setupDemoFfw;

  /// No description provided for @setupDemoFfwHint.
  ///
  /// In de, this message translates to:
  /// **'Gerätehaus, Fahrzeuge und ehrenamtlicher Wachalltag'**
  String get setupDemoFfwHint;

  /// No description provided for @setupDemoPolizei.
  ///
  /// In de, this message translates to:
  /// **'Polizei'**
  String get setupDemoPolizei;

  /// No description provided for @setupDemoPolizeiHint.
  ///
  /// In de, this message translates to:
  /// **'Wachalltag, Material und Dienstgruppe'**
  String get setupDemoPolizeiHint;

  /// No description provided for @demoBannerLabel.
  ///
  /// In de, this message translates to:
  /// **'Demo-Modus'**
  String get demoBannerLabel;

  /// No description provided for @demoBannerRettungsdienst.
  ///
  /// In de, this message translates to:
  /// **'Rettungsdienst'**
  String get demoBannerRettungsdienst;

  /// No description provided for @demoBannerFeuerwehr.
  ///
  /// In de, this message translates to:
  /// **'Feuerwehr'**
  String get demoBannerFeuerwehr;

  /// No description provided for @demoBannerFfw.
  ///
  /// In de, this message translates to:
  /// **'Freiwillige Feuerwehr'**
  String get demoBannerFfw;

  /// No description provided for @demoBannerPolizei.
  ///
  /// In de, this message translates to:
  /// **'Polizei'**
  String get demoBannerPolizei;

  /// No description provided for @qrScanTitle.
  ///
  /// In de, this message translates to:
  /// **'Server-QR scannen'**
  String get qrScanTitle;

  /// No description provided for @qrScanCameraHint.
  ///
  /// In de, this message translates to:
  /// **'Die Kamera wird hier nur zum Lesen der Server-Adresse genutzt. Es werden dabei keine Fotos gespeichert oder hochgeladen.'**
  String get qrScanCameraHint;

  /// No description provided for @qrScanInvalid.
  ///
  /// In de, this message translates to:
  /// **'Kein gültiger Wachbuch-Server-QR.'**
  String get qrScanInvalid;

  /// No description provided for @qrScanWebHint.
  ///
  /// In de, this message translates to:
  /// **'QR aus dem Wachbuch-Web unter Mein Konto → App-Tokens'**
  String get qrScanWebHint;

  /// No description provided for @qrCameraDialogTitle.
  ///
  /// In de, this message translates to:
  /// **'Kamera für QR-Code'**
  String get qrCameraDialogTitle;

  /// No description provided for @qrCameraDialogMessage.
  ///
  /// In de, this message translates to:
  /// **'Wachbuch benötigt die Kamera hier ausschließlich, um den QR-Code mit der Server-Adresse Ihrer Wache zu scannen. Ohne Kamera können Sie die Adresse auch manuell eingeben.'**
  String get qrCameraDialogMessage;

  /// No description provided for @qrCameraContinue.
  ///
  /// In de, this message translates to:
  /// **'Weiter'**
  String get qrCameraContinue;

  /// No description provided for @qrCameraDeniedTitle.
  ///
  /// In de, this message translates to:
  /// **'Kamera nicht freigegeben'**
  String get qrCameraDeniedTitle;

  /// No description provided for @qrCameraDeniedMessage.
  ///
  /// In de, this message translates to:
  /// **'Ohne Kamerazugriff können Sie den QR nicht scannen. Geben Sie die Server-Adresse manuell ein oder aktivieren Sie die Kamera in den Systemeinstellungen.'**
  String get qrCameraDeniedMessage;

  /// No description provided for @qrCameraOk.
  ///
  /// In de, this message translates to:
  /// **'OK'**
  String get qrCameraOk;

  /// No description provided for @qrCameraSettings.
  ///
  /// In de, this message translates to:
  /// **'Einstellungen'**
  String get qrCameraSettings;

  /// No description provided for @handoverStatusOpen.
  ///
  /// In de, this message translates to:
  /// **'Offen'**
  String get handoverStatusOpen;

  /// No description provided for @handoverStatusInProgress.
  ///
  /// In de, this message translates to:
  /// **'In Bearbeitung'**
  String get handoverStatusInProgress;

  /// No description provided for @handoverStatusDone.
  ///
  /// In de, this message translates to:
  /// **'Erledigt'**
  String get handoverStatusDone;

  /// No description provided for @handoverPriorityNormal.
  ///
  /// In de, this message translates to:
  /// **'Normal'**
  String get handoverPriorityNormal;

  /// No description provided for @handoverPriorityImportant.
  ///
  /// In de, this message translates to:
  /// **'Wichtig'**
  String get handoverPriorityImportant;

  /// No description provided for @handoverPriorityUrgent.
  ///
  /// In de, this message translates to:
  /// **'Dringend'**
  String get handoverPriorityUrgent;

  /// No description provided for @handoverCategoryStation.
  ///
  /// In de, this message translates to:
  /// **'Wache'**
  String get handoverCategoryStation;

  /// No description provided for @handoverCategoryVehicle.
  ///
  /// In de, this message translates to:
  /// **'Fahrzeugstatus'**
  String get handoverCategoryVehicle;

  /// No description provided for @handoverCategoryMaterial.
  ///
  /// In de, this message translates to:
  /// **'Material'**
  String get handoverCategoryMaterial;

  /// No description provided for @handoverCategoryTask.
  ///
  /// In de, this message translates to:
  /// **'Offene Aufgabe'**
  String get handoverCategoryTask;

  /// No description provided for @handoverCategorySafety.
  ///
  /// In de, this message translates to:
  /// **'Sicherheit/Mangel'**
  String get handoverCategorySafety;

  /// No description provided for @handoverEnumUnknown.
  ///
  /// In de, this message translates to:
  /// **'Nicht angegeben'**
  String get handoverEnumUnknown;

  /// No description provided for @chatTitle.
  ///
  /// In de, this message translates to:
  /// **'Wachenchat'**
  String get chatTitle;

  /// No description provided for @chatSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Ende-zu-Ende verschlüsselt'**
  String get chatSubtitle;

  /// No description provided for @chatSetupTitle.
  ///
  /// In de, this message translates to:
  /// **'Chat-Schlüssel einrichten'**
  String get chatSetupTitle;

  /// No description provided for @chatSetupHint.
  ///
  /// In de, this message translates to:
  /// **'Lege eine Passphrase fest. Sie schützt deinen privaten Schlüssel und wird nie an den Server übertragen.'**
  String get chatSetupHint;

  /// No description provided for @chatSetupAction.
  ///
  /// In de, this message translates to:
  /// **'Schlüssel erstellen'**
  String get chatSetupAction;

  /// No description provided for @chatUnlockTitle.
  ///
  /// In de, this message translates to:
  /// **'Chat entsperren'**
  String get chatUnlockTitle;

  /// No description provided for @chatUnlockHint.
  ///
  /// In de, this message translates to:
  /// **'Gib deine Passphrase ein, um verschlüsselte Nachrichten zu lesen und zu schreiben.'**
  String get chatUnlockHint;

  /// No description provided for @chatUnlockAction.
  ///
  /// In de, this message translates to:
  /// **'Entsperren'**
  String get chatUnlockAction;

  /// No description provided for @chatPassphrase.
  ///
  /// In de, this message translates to:
  /// **'Passphrase'**
  String get chatPassphrase;

  /// No description provided for @chatWrongPassphrase.
  ///
  /// In de, this message translates to:
  /// **'Falsche Passphrase oder beschädigter Schlüssel.'**
  String get chatWrongPassphrase;

  /// No description provided for @chatComposeHint.
  ///
  /// In de, this message translates to:
  /// **'Kurze Nachricht an die Wache …'**
  String get chatComposeHint;

  /// No description provided for @chatSend.
  ///
  /// In de, this message translates to:
  /// **'Senden'**
  String get chatSend;

  /// No description provided for @chatEmpty.
  ///
  /// In de, this message translates to:
  /// **'Noch keine Nachrichten.'**
  String get chatEmpty;

  /// No description provided for @chatUnreadable.
  ///
  /// In de, this message translates to:
  /// **'Nachricht nicht lesbar (kein Schlüssel für dich).'**
  String get chatUnreadable;

  /// No description provided for @chatLoadError.
  ///
  /// In de, this message translates to:
  /// **'Chat konnte nicht geladen werden.'**
  String get chatLoadError;

  /// No description provided for @chatMe.
  ///
  /// In de, this message translates to:
  /// **'Ich'**
  String get chatMe;

  /// No description provided for @groupsTitle.
  ///
  /// In de, this message translates to:
  /// **'Gruppen'**
  String get groupsTitle;

  /// No description provided for @groupsSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Gruppen-Chats (Ende-zu-Ende)'**
  String get groupsSubtitle;

  /// No description provided for @groupsEmpty.
  ///
  /// In de, this message translates to:
  /// **'Noch keine Gruppen.'**
  String get groupsEmpty;

  /// No description provided for @groupsCreate.
  ///
  /// In de, this message translates to:
  /// **'Gruppe erstellen'**
  String get groupsCreate;

  /// No description provided for @groupName.
  ///
  /// In de, this message translates to:
  /// **'Gruppenname'**
  String get groupName;

  /// No description provided for @groupMembers.
  ///
  /// In de, this message translates to:
  /// **'Mitglieder'**
  String get groupMembers;

  /// No description provided for @groupCreateAction.
  ///
  /// In de, this message translates to:
  /// **'Erstellen'**
  String get groupCreateAction;

  /// No description provided for @groupSelectMembers.
  ///
  /// In de, this message translates to:
  /// **'Mitglieder auswählen'**
  String get groupSelectMembers;

  /// No description provided for @groupNoColleagues.
  ///
  /// In de, this message translates to:
  /// **'Keine Kolleginnen und Kollegen mit Schlüsseln verfügbar.'**
  String get groupNoColleagues;

  /// No description provided for @pinboardTitle.
  ///
  /// In de, this message translates to:
  /// **'Pinnwand'**
  String get pinboardTitle;

  /// No description provided for @pinboardSubtitle.
  ///
  /// In de, this message translates to:
  /// **'Aushänge und Hinweise für die Wache'**
  String get pinboardSubtitle;

  /// No description provided for @pinboardEmpty.
  ///
  /// In de, this message translates to:
  /// **'Noch keine Aushänge an der Pinnwand.'**
  String get pinboardEmpty;

  /// No description provided for @pinboardCreate.
  ///
  /// In de, this message translates to:
  /// **'Aushang anlegen'**
  String get pinboardCreate;

  /// No description provided for @pinboardFieldTitle.
  ///
  /// In de, this message translates to:
  /// **'Titel'**
  String get pinboardFieldTitle;

  /// No description provided for @pinboardFieldBody.
  ///
  /// In de, this message translates to:
  /// **'Text'**
  String get pinboardFieldBody;

  /// No description provided for @pinboardCategory.
  ///
  /// In de, this message translates to:
  /// **'Art'**
  String get pinboardCategory;

  /// No description provided for @pinboardPinned.
  ///
  /// In de, this message translates to:
  /// **'Angepinnt'**
  String get pinboardPinned;

  /// No description provided for @pinboardSave.
  ///
  /// In de, this message translates to:
  /// **'Speichern'**
  String get pinboardSave;

  /// No description provided for @pinboardCancel.
  ///
  /// In de, this message translates to:
  /// **'Abbrechen'**
  String get pinboardCancel;

  /// No description provided for @pinboardCategoryInfo.
  ///
  /// In de, this message translates to:
  /// **'Info'**
  String get pinboardCategoryInfo;

  /// No description provided for @pinboardCategoryImportant.
  ///
  /// In de, this message translates to:
  /// **'Wichtig'**
  String get pinboardCategoryImportant;

  /// No description provided for @pinboardCategoryEvent.
  ///
  /// In de, this message translates to:
  /// **'Termin/Hinweis'**
  String get pinboardCategoryEvent;

  /// No description provided for @pinboardLoadError.
  ///
  /// In de, this message translates to:
  /// **'Pinnwand konnte nicht geladen werden.'**
  String get pinboardLoadError;

  /// No description provided for @pinboardCreated.
  ///
  /// In de, this message translates to:
  /// **'Aushang wurde angelegt.'**
  String get pinboardCreated;

  /// No description provided for @updateTitleAvailable.
  ///
  /// In de, this message translates to:
  /// **'Neue Version verfügbar'**
  String get updateTitleAvailable;

  /// No description provided for @updateTitleRequired.
  ///
  /// In de, this message translates to:
  /// **'Wichtiges Update erforderlich'**
  String get updateTitleRequired;

  /// No description provided for @updateCurrentVersion.
  ///
  /// In de, this message translates to:
  /// **'Aktuelle Version: {version}'**
  String updateCurrentVersion(Object version);

  /// No description provided for @updateNewVersion.
  ///
  /// In de, this message translates to:
  /// **'Neue Version: {version}'**
  String updateNewVersion(Object version);

  /// No description provided for @updateReleasedAt.
  ///
  /// In de, this message translates to:
  /// **'Veröffentlicht am: {date}'**
  String updateReleasedAt(Object date);

  /// No description provided for @updateWhatsNew.
  ///
  /// In de, this message translates to:
  /// **'Was gibt es Neues?'**
  String get updateWhatsNew;

  /// No description provided for @updateRequiredNotice.
  ///
  /// In de, this message translates to:
  /// **'Dieses Update ist erforderlich, um die App weiter nutzen zu können.'**
  String get updateRequiredNotice;

  /// No description provided for @updateForceExplanation.
  ///
  /// In de, this message translates to:
  /// **'Um die App weiter nutzen zu können, musst du auf die neueste Version updaten.'**
  String get updateForceExplanation;

  /// No description provided for @updateRequiredVersion.
  ///
  /// In de, this message translates to:
  /// **'Erforderliche Version: {version}'**
  String updateRequiredVersion(Object version);

  /// No description provided for @updateLater.
  ///
  /// In de, this message translates to:
  /// **'Später erinnern'**
  String get updateLater;

  /// No description provided for @updateClose.
  ///
  /// In de, this message translates to:
  /// **'Schließen'**
  String get updateClose;

  /// No description provided for @updateDownload.
  ///
  /// In de, this message translates to:
  /// **'Update herunterladen'**
  String get updateDownload;

  /// No description provided for @updateNow.
  ///
  /// In de, this message translates to:
  /// **'Jetzt updaten'**
  String get updateNow;

  /// No description provided for @updateVersionEntry.
  ///
  /// In de, this message translates to:
  /// **'Version {version}'**
  String updateVersionEntry(Object version);

  /// No description provided for @keyVerifyTitle.
  ///
  /// In de, this message translates to:
  /// **'Schlüssel verifizieren'**
  String get keyVerifyTitle;

  /// No description provided for @keyVerifyExplanation.
  ///
  /// In de, this message translates to:
  /// **'Vergleiche den Fingerprint deines Schlüssels mit dem deiner Kolleginnen und Kollegen – persönlich oder per QR-Scan. Stimmen sie überein, ist der Schlüssel echt.'**
  String get keyVerifyExplanation;

  /// No description provided for @keyVerifyOwnKey.
  ///
  /// In de, this message translates to:
  /// **'Dein Schlüssel'**
  String get keyVerifyOwnKey;

  /// No description provided for @keyVerifyOwnTag.
  ///
  /// In de, this message translates to:
  /// **'(du)'**
  String get keyVerifyOwnTag;

  /// No description provided for @keyVerifyVerifiedTag.
  ///
  /// In de, this message translates to:
  /// **'verifiziert'**
  String get keyVerifyVerifiedTag;

  /// No description provided for @keyVerifyScanAction.
  ///
  /// In de, this message translates to:
  /// **'Per Scan verifizieren'**
  String get keyVerifyScanAction;

  /// No description provided for @keyVerifyScanTitle.
  ///
  /// In de, this message translates to:
  /// **'Fingerprint scannen'**
  String get keyVerifyScanTitle;

  /// No description provided for @keyVerifyMatch.
  ///
  /// In de, this message translates to:
  /// **'Fingerprint stimmt mit {name} überein.'**
  String keyVerifyMatch(Object name);

  /// No description provided for @keyVerifyNoMatch.
  ///
  /// In de, this message translates to:
  /// **'Kein Mitglied mit diesem Fingerprint gefunden.'**
  String get keyVerifyNoMatch;

  /// No description provided for @keyVerifyCopied.
  ///
  /// In de, this message translates to:
  /// **'Fingerprint kopiert.'**
  String get keyVerifyCopied;

  /// No description provided for @keyVerifyShowQr.
  ///
  /// In de, this message translates to:
  /// **'QR-Code anzeigen'**
  String get keyVerifyShowQr;

  /// No description provided for @keyVerifyConfirmAction.
  ///
  /// In de, this message translates to:
  /// **'Als verifiziert markieren'**
  String get keyVerifyConfirmAction;

  /// No description provided for @keyVerifyRevoke.
  ///
  /// In de, this message translates to:
  /// **'Verifizierung zurückziehen'**
  String get keyVerifyRevoke;

  /// No description provided for @keyVerifyReverified.
  ///
  /// In de, this message translates to:
  /// **'Geänderter Schlüssel von {name} erneut verifiziert.'**
  String keyVerifyReverified(Object name);

  /// No description provided for @keyVerifyChangedTag.
  ///
  /// In de, this message translates to:
  /// **'Schlüssel geändert!'**
  String get keyVerifyChangedTag;

  /// No description provided for @keyVerifyChangedWarning.
  ///
  /// In de, this message translates to:
  /// **'{count, plural, one {{count} verifizierter Schlüssel hat sich geändert} other {{count} verifizierte Schlüssel haben sich geändert}}. Bitte persönlich erneut prüfen.'**
  String keyVerifyChangedWarning(num count);

  /// No description provided for @keyVerifyServerMismatch.
  ///
  /// In de, this message translates to:
  /// **'{count, plural, one {{count} vom Server gemeldeter Fingerprint weicht vom Schlüssel ab} other {{count} vom Server gemeldete Fingerprints weichen vom Schlüssel ab}}. Mögliche Server-Manipulation – nicht verifizieren.'**
  String keyVerifyServerMismatch(num count);
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['de', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'de':
      return AppLocalizationsDe();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
