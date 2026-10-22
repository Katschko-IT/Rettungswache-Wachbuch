// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appName => 'Wachbuch';

  @override
  String errorSemanticsLabel(String message) {
    return 'Error: $message';
  }

  @override
  String get commonCancel => 'Cancel';

  @override
  String get commonSwitch => 'Switch';

  @override
  String get commonSave => 'Save';

  @override
  String get commonClose => 'Close';

  @override
  String get commonRetry => 'Try again';

  @override
  String get noticeSessionExpired =>
      'Your session has expired. Please sign in again.';

  @override
  String get noticeSessionEnded => 'Session ended. Please sign in again.';

  @override
  String get serverSwitchTitle => 'Switch server?';

  @override
  String serverSwitchMessage(String url) {
    return 'A link wants to switch the app to\n$url.\nThe current login will be ended.';
  }

  @override
  String get navOverview => 'Overview';

  @override
  String get navHandovers => 'Handovers';

  @override
  String get navAccount => 'Account';

  @override
  String get refreshTooltip => 'Refresh';

  @override
  String get stationFallback => 'Wachbuch';

  @override
  String get sessionExpiredError => 'Login expired or revoked.';

  @override
  String get overviewActiveHandovers => 'Active handovers';

  @override
  String get metricOpen => 'open';

  @override
  String get metricInProgress => 'in progress';

  @override
  String get metricUrgent => 'urgent';

  @override
  String get overviewModulesTitle => 'Modules of this station';

  @override
  String get overviewModulesHint =>
      'Your station and the available modules are loaded automatically from your account.';

  @override
  String get moduleCalendarTitle => 'Calendar';

  @override
  String get moduleCalendarSubtitle => 'Shift schedules and duties';

  @override
  String get moduleCoffeeTitle => 'Coffee fund';

  @override
  String get moduleCoffeeSubtitle => 'Balance and transactions';

  @override
  String get moduleChecklistsTitle => 'Checklists';

  @override
  String get moduleChecklistsSubtitle => 'Tick off items and complete';

  @override
  String get moduleDefectsTitle => 'Defects';

  @override
  String get moduleDefectsSubtitle => 'Open items with owner and due date';

  @override
  String get moduleAssetsTitle => 'Assets';

  @override
  String get moduleAssetsSubtitle =>
      'Vehicle and equipment status at the station';

  @override
  String get moduleReportsTitle => 'Reports';

  @override
  String get moduleReportsSubtitle => 'Defects, due checks and readiness rate';

  @override
  String get quickAccessTitle => 'Quick access';

  @override
  String get defectsTitle => 'Defects';

  @override
  String get defectsHint =>
      'Open station items — keep status and ownership traceable.';

  @override
  String get defectsEmpty => 'No defects for this filter.';

  @override
  String get defectAdd => 'Add defect';

  @override
  String get defectCreateTitle => 'Create defect';

  @override
  String get defectTitleLabel => 'Title';

  @override
  String get defectDescriptionLabel => 'Description';

  @override
  String get defectCategoryLabel => 'Category';

  @override
  String get defectPriorityLabel => 'Priority';

  @override
  String get defectAssetLabel => 'Asset';

  @override
  String get defectOwnerLabel => 'Owner';

  @override
  String get defectOwnerSelf => 'Assign to me';

  @override
  String get defectDueLabel => 'Due';

  @override
  String get defectSetStatus => 'Set status';

  @override
  String get defectStatusWaiting => 'Waiting';

  @override
  String get defectCreateFailed => 'Defect could not be created.';

  @override
  String get defectPhotosTitle => 'Photos';

  @override
  String get defectPhotosHint =>
      'Only photograph the defect condition. Do not photograph patient or incident data.';

  @override
  String get defectPhotosEmpty => 'No photos yet.';

  @override
  String get defectAddPhoto => 'Add photo';

  @override
  String get defectTakePhoto => 'Camera';

  @override
  String get defectChoosePhoto => 'Photo library';

  @override
  String get defectPhotoUploadFailed => 'Photo could not be uploaded.';

  @override
  String get defectPhotoTooLarge => 'The image may be at most 2 MiB.';

  @override
  String get defectPhotoUploaded => 'Photo uploaded.';

  @override
  String get assetsBoardTitle => 'Vehicle & equipment status';

  @override
  String get assetsScreenTitle => 'Assets & status';

  @override
  String get assetsEmpty => 'No assets or pools available.';

  @override
  String get assetStatusReady => 'Ready';

  @override
  String get assetStatusLimited => 'Limited';

  @override
  String get assetStatusOob => 'Out of service';

  @override
  String get assetStatusWorkshop => 'Workshop';

  @override
  String get inventoryTitle => 'Keys & pools';

  @override
  String get inventoryHint =>
      'Checkout / check-in for pooled devices and keys.';

  @override
  String get inventoryAvailable => 'Available';

  @override
  String get inventoryHolderLabel => 'Held by';

  @override
  String get inventoryCheckout => 'Check out';

  @override
  String get inventoryCheckin => 'Check in';

  @override
  String get checklistIntervalDaily => 'Daily';

  @override
  String get checklistIntervalWeekly => 'Weekly';

  @override
  String get checklistIntervalMonthly => 'Monthly';

  @override
  String get checklistDueToday => 'Due today';

  @override
  String get checklistOverdue => 'Overdue';

  @override
  String get checklistDueSection => 'Due today / overdue';

  @override
  String get reportsTitle => 'Reports';

  @override
  String get reportsHint =>
      'Lightweight station overview without individual performance scoring.';

  @override
  String get reportsOpenDefects => 'Open defects';

  @override
  String get reportsOverdueDefects => 'Overdue defects';

  @override
  String get reportsOverdueChecks => 'Overdue checks';

  @override
  String get reportsAssetReady => 'Assets ready';

  @override
  String get reportsInventoryOut => 'Pools checked out';

  @override
  String get reportsUnacked => 'Unacknowledged handovers';

  @override
  String get reportsOldestOpen => 'Oldest open defect';

  @override
  String get reportsDays => 'days';

  @override
  String get reportsByOwner => 'Open defects by owner';

  @override
  String get reportsNoOwner => 'No owner';

  @override
  String get reportsPrivacyHint =>
      'This report supports station organisation and is not intended for individual employee performance scoring.';

  @override
  String get handoverAckButton => 'Acknowledged';

  @override
  String get handoverAckDone => 'Acknowledged by you';

  @override
  String get handoverAckListTitle => 'Acknowledgements';

  @override
  String get handoverAckEmpty => 'Not acknowledged yet.';

  @override
  String get handoverAckFailed => 'Acknowledgement failed.';

  @override
  String get handoverSearchHint => 'Search handovers';

  @override
  String get handoverSearchClear => 'Clear search';

  @override
  String get filterStatus => 'Status';

  @override
  String get filterPriority => 'Priority';

  @override
  String handoversCount(int count, int total) {
    return '$count of $total handovers';
  }

  @override
  String filterSectionLabel(String title) {
    return 'Filter $title';
  }

  @override
  String get handoversNoneActive => 'No active handovers.';

  @override
  String get handoversNoneForFilter => 'No handovers match these filters.';

  @override
  String get handoverUntitled => 'untitled';

  @override
  String get handoverFallback => 'Handover';

  @override
  String handoverOpenSemantics(String title) {
    return 'Open handover $title';
  }

  @override
  String get detailsLoadFailed => 'Details could not be loaded.';

  @override
  String get detailsNoFurtherInfo => 'No further details.';

  @override
  String detailsUpdatedAt(String timestamp) {
    return 'Updated $timestamp';
  }

  @override
  String detailsVersion(String version) {
    return 'Version $version';
  }

  @override
  String get accountLoggedInAs => 'Signed in as';

  @override
  String get accountServer => 'Server';

  @override
  String get accountLicense => 'License';

  @override
  String get accountLicenseValue => 'AGPL-3.0-or-later · Open source';

  @override
  String get accountRefreshProfile => 'Refresh profile';

  @override
  String get accountLogout => 'Sign out';

  @override
  String get accountChangeServer => 'Set up another server';

  @override
  String get kalenderTitle => 'Calendar';

  @override
  String get kalenderEmpty => 'No upcoming appointments.';

  @override
  String get kalenderEntryFallback => 'Appointment';

  @override
  String get kalenderTimeTbd => 'Time to be announced';

  @override
  String get kalenderAllDay => 'All day';

  @override
  String get kaffeekasseTitle => 'Coffee fund';

  @override
  String get kaffeekasseBalanceLabel => 'Current balance';

  @override
  String get kaffeekasseNegative =>
      'The fund is in the negative – please top up.';

  @override
  String get kaffeekasseLastTransactions => 'Recent transactions';

  @override
  String get kaffeekasseEmptyLedger => 'No transactions yet.';

  @override
  String get kaffeekasseEntryFallback => 'Transaction';

  @override
  String get checklistenTitle => 'Checklists';

  @override
  String get checklistenEmpty => 'No checklists available.';

  @override
  String get checklistFallback => 'Checklist';

  @override
  String get checklistNoItems => 'No items.';

  @override
  String get checklistCompleteButton => 'Complete checklist';

  @override
  String get checklistItemFallback => 'Item';

  @override
  String checklistCompletedAt(String timestamp) {
    return 'Completed $timestamp';
  }

  @override
  String get loginAppBarTitle => 'Sign in';

  @override
  String get loginChangeServer => 'Change server';

  @override
  String get loginHeading => 'Sign in';

  @override
  String get loginTokenLabel => 'App token (wb_…)';

  @override
  String get loginTokenHelper =>
      'From the web at /konto/api/ – required for MFA';

  @override
  String get loginTokenRequired => 'Token required';

  @override
  String get loginUsername => 'Username';

  @override
  String get loginUsernameRequired => 'Username required';

  @override
  String get loginPassword => 'Password';

  @override
  String get loginPasswordRequired => 'Password required';

  @override
  String get loginShow => 'Show';

  @override
  String get loginHide => 'Hide';

  @override
  String get loginSubmit => 'Sign in';

  @override
  String get loginUseCredentials => 'With username and password';

  @override
  String get loginUseToken => 'Use an app token instead';

  @override
  String get loginTokenPasteHint =>
      'Please paste an app token (from /konto/api/).';

  @override
  String get loginMfaHint =>
      'For two-factor: create an app token on the web under My Account → App Tokens.';

  @override
  String get loginInvalidInput => 'Invalid input.';

  @override
  String get setupServerAddressTitle => 'Server address of your station';

  @override
  String get setupHint => 'Enter the address or scan the QR code from the web.';

  @override
  String get setupAddressLabel => 'Address';

  @override
  String get setupAddressHint => 'https://station.example.org';

  @override
  String get setupScanQr => 'Scan QR code';

  @override
  String get setupAddressRequired => 'Enter an address';

  @override
  String get setupAddressInvalid => 'Invalid address';

  @override
  String get setupConfirm => 'Confirm';

  @override
  String get setupFooter =>
      'Play Store client: connects only to your self-hosted server. Production: HTTPS required.';

  @override
  String get setupDemoButton => 'Try demo mode';

  @override
  String get setupDemoTitle => 'Choose a demo';

  @override
  String get setupDemoSubtitle =>
      'Local sample data without a server — for EMS, fire service, volunteer fire or police.';

  @override
  String get setupDemoRettungsdienst => 'Emergency medical services';

  @override
  String get setupDemoRettungsdienstHint =>
      'Shift handover and equipment at the EMS station';

  @override
  String get setupDemoFeuerwehr => 'Fire service';

  @override
  String get setupDemoFeuerwehrHint =>
      'Station house, vehicles and duty handover';

  @override
  String get setupDemoFfw => 'Volunteer fire service';

  @override
  String get setupDemoFfwHint =>
      'Station house, vehicles and volunteer routines';

  @override
  String get setupDemoPolizei => 'Police';

  @override
  String get setupDemoPolizeiHint =>
      'Station routines, equipment and duty group';

  @override
  String get demoBannerLabel => 'Demo mode';

  @override
  String get demoBannerRettungsdienst => 'EMS';

  @override
  String get demoBannerFeuerwehr => 'Fire service';

  @override
  String get demoBannerFfw => 'Volunteer fire';

  @override
  String get demoBannerPolizei => 'Police';

  @override
  String get qrScanTitle => 'Scan server QR';

  @override
  String get qrScanCameraHint =>
      'The camera is used here only to read the server address. No photos are saved or uploaded during QR scanning.';

  @override
  String get qrScanInvalid => 'Not a valid Wachbuch server QR code.';

  @override
  String get qrScanWebHint =>
      'QR from the Wachbuch web under My Account → App Tokens';

  @override
  String get qrCameraDialogTitle => 'Camera for QR code';

  @override
  String get qrCameraDialogMessage =>
      'Wachbuch needs the camera here solely to scan the QR code containing your station\'s server address. You can also enter the address manually without the camera.';

  @override
  String get qrCameraContinue => 'Continue';

  @override
  String get qrCameraDeniedTitle => 'Camera not enabled';

  @override
  String get qrCameraDeniedMessage =>
      'Without camera access you cannot scan the QR code. Enter the server address manually or enable the camera in the system settings.';

  @override
  String get qrCameraOk => 'OK';

  @override
  String get qrCameraSettings => 'Settings';

  @override
  String get handoverStatusOpen => 'Open';

  @override
  String get handoverStatusInProgress => 'In progress';

  @override
  String get handoverStatusDone => 'Done';

  @override
  String get handoverPriorityNormal => 'Normal';

  @override
  String get handoverPriorityImportant => 'Important';

  @override
  String get handoverPriorityUrgent => 'Urgent';

  @override
  String get handoverCategoryStation => 'Station';

  @override
  String get handoverCategoryVehicle => 'Vehicle status';

  @override
  String get handoverCategoryMaterial => 'Material';

  @override
  String get handoverCategoryTask => 'Open task';

  @override
  String get handoverCategorySafety => 'Safety/defect';

  @override
  String get handoverEnumUnknown => 'Not specified';

  @override
  String get chatTitle => 'Station chat';

  @override
  String get chatSubtitle => 'End-to-end encrypted';

  @override
  String get chatSetupTitle => 'Set up chat keys';

  @override
  String get chatSetupHint =>
      'Choose a passphrase. It protects your private key and is never sent to the server.';

  @override
  String get chatSetupAction => 'Create keys';

  @override
  String get chatUnlockTitle => 'Unlock chat';

  @override
  String get chatUnlockHint =>
      'Enter your passphrase to read and write encrypted messages.';

  @override
  String get chatUnlockAction => 'Unlock';

  @override
  String get chatPassphrase => 'Passphrase';

  @override
  String get chatWrongPassphrase => 'Wrong passphrase or damaged key.';

  @override
  String get chatComposeHint => 'Short message to the station …';

  @override
  String get chatSend => 'Send';

  @override
  String get chatEmpty => 'No messages yet.';

  @override
  String get chatUnreadable => 'Message not readable (no key for you).';

  @override
  String get chatLoadError => 'Could not load the chat.';

  @override
  String get chatMe => 'Me';

  @override
  String get groupsTitle => 'Groups';

  @override
  String get groupsSubtitle => 'Group chats (end-to-end)';

  @override
  String get groupsEmpty => 'No groups yet.';

  @override
  String get groupsCreate => 'Create group';

  @override
  String get groupName => 'Group name';

  @override
  String get groupMembers => 'Members';

  @override
  String get groupCreateAction => 'Create';

  @override
  String get groupSelectMembers => 'Select members';

  @override
  String get groupNoColleagues => 'No colleagues with keys available.';

  @override
  String get pinboardTitle => 'Pinboard';

  @override
  String get pinboardSubtitle => 'Notices and hints for the station';

  @override
  String get pinboardEmpty => 'No notices on the pinboard yet.';

  @override
  String get pinboardCreate => 'New notice';

  @override
  String get pinboardFieldTitle => 'Title';

  @override
  String get pinboardFieldBody => 'Text';

  @override
  String get pinboardCategory => 'Type';

  @override
  String get pinboardPinned => 'Pinned';

  @override
  String get pinboardSave => 'Save';

  @override
  String get pinboardCancel => 'Cancel';

  @override
  String get pinboardCategoryInfo => 'Info';

  @override
  String get pinboardCategoryImportant => 'Important';

  @override
  String get pinboardCategoryEvent => 'Event/Note';

  @override
  String get pinboardLoadError => 'Could not load the pinboard.';

  @override
  String get pinboardCreated => 'Notice created.';

  @override
  String get updateTitleAvailable => 'New version available';

  @override
  String get updateTitleRequired => 'Important update required';

  @override
  String updateCurrentVersion(Object version) {
    return 'Current version: $version';
  }

  @override
  String updateNewVersion(Object version) {
    return 'New version: $version';
  }

  @override
  String updateReleasedAt(Object date) {
    return 'Released on: $date';
  }

  @override
  String get updateWhatsNew => 'What\'s new?';

  @override
  String get updateRequiredNotice =>
      'This update is required to continue using the app.';

  @override
  String get updateForceExplanation =>
      'To continue using the app, you need to update to the latest version.';

  @override
  String updateRequiredVersion(Object version) {
    return 'Required version: $version';
  }

  @override
  String get updateLater => 'Remind me later';

  @override
  String get updateClose => 'Close';

  @override
  String get updateDownload => 'Download update';

  @override
  String get updateNow => 'Update now';

  @override
  String updateVersionEntry(Object version) {
    return 'Version $version';
  }

  @override
  String get keyVerifyTitle => 'Verify keys';

  @override
  String get keyVerifyExplanation =>
      'Compare your key fingerprint with your colleagues\' — in person or by scanning a QR code. Matching fingerprints mean the key is genuine.';

  @override
  String get keyVerifyOwnKey => 'Your key';

  @override
  String get keyVerifyOwnTag => '(you)';

  @override
  String get keyVerifyVerifiedTag => 'verified';

  @override
  String get keyVerifyScanAction => 'Verify by scan';

  @override
  String get keyVerifyScanTitle => 'Scan fingerprint';

  @override
  String keyVerifyMatch(Object name) {
    return 'Fingerprint matches $name.';
  }

  @override
  String get keyVerifyNoMatch => 'No member with this fingerprint found.';

  @override
  String get keyVerifyCopied => 'Fingerprint copied.';

  @override
  String get keyVerifyShowQr => 'Show QR code';

  @override
  String get keyVerifyConfirmAction => 'Mark as verified';

  @override
  String get keyVerifyRevoke => 'Revoke verification';

  @override
  String keyVerifyReverified(Object name) {
    return 'Changed key of $name verified again.';
  }

  @override
  String get keyVerifyChangedTag => 'Key changed!';

  @override
  String keyVerifyChangedWarning(num count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count verified keys have changed',
      one: '$count verified key has changed',
    );
    return '$_temp0. Please compare again in person.';
  }

  @override
  String keyVerifyServerMismatch(num count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count server-reported fingerprints disagree with the key',
      one: '$count server-reported fingerprint disagrees with the key',
    );
    return '$_temp0. Possible server tampering – do not verify.';
  }
}
