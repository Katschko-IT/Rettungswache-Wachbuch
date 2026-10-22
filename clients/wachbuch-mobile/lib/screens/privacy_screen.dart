import 'package:flutter/material.dart';
import 'package:url_launcher/link.dart';

const _privacyPolicyUri =
    'https://github.com/Katschko-IT/Wachbuch-Client/'
    'blob/main/docs/PRIVACY-POLICY.md';
const _supportUri =
    'https://github.com/Katschko-IT/Wachbuch-Client/'
    'blob/main/docs/SUPPORT.md';

/// Store-facing privacy information that remains reachable before login.
///
/// The canonical, versioned policy lives in docs/PRIVACY-POLICY.md. This
/// screen intentionally contains the operational essentials and a real public
/// privacy-policy link so the store disclosure does not depend on a WebView.
class PrivacyScreen extends StatelessWidget {
  const PrivacyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final german = Localizations.localeOf(context).languageCode == 'de';
    final policy = german ? _de : _en;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: Text(policy.title)),
      body: SafeArea(
        child: SelectionArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              Text(
                policy.intro,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: 20),
              for (final section in policy.sections) ...[
                Text(
                  section.title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(section.body),
                const SizedBox(height: 18),
              ],
              Material(
                color: scheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        policy.canonicalTitle,
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 6),
                      const SelectableText(_privacyPolicyUri),
                      const SizedBox(height: 8),
                      Link(
                        uri: Uri.parse(_privacyPolicyUri),
                        target: LinkTarget.blank,
                        builder: (context, followLink) => OutlinedButton.icon(
                          key: const Key('open-privacy-policy'),
                          onPressed: followLink,
                          icon: const Icon(Icons.open_in_new),
                          label: Text(policy.openPolicy),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        policy.supportTitle,
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 6),
                      const SelectableText(_supportUri),
                      const SizedBox(height: 8),
                      Link(
                        uri: Uri.parse(_supportUri),
                        target: LinkTarget.blank,
                        builder: (context, followLink) => TextButton.icon(
                          key: const Key('open-support-page'),
                          onPressed: followLink,
                          icon: const Icon(Icons.support_agent_outlined),
                          label: Text(policy.openSupport),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PolicyCopy {
  const _PolicyCopy({
    required this.title,
    required this.intro,
    required this.sections,
    required this.canonicalTitle,
    required this.supportTitle,
    required this.openPolicy,
    required this.openSupport,
  });

  final String title;
  final String intro;
  final List<_PolicySection> sections;
  final String canonicalTitle;
  final String supportTitle;
  final String openPolicy;
  final String openSupport;
}

class _PolicySection {
  const _PolicySection(this.title, this.body);

  final String title;
  final String body;
}

const _de = _PolicyCopy(
  title: 'Datenschutz',
  intro:
      'Wachbuch ist ein Open-Source-Client für selbst gehostete '
      'Wachbuch-Server. Die App betreibt keine zentrale Wachbuch-Cloud und ist '
      'keine offizielle Behörden-, Notruf-, Einsatzleit-, Patientenakten- oder '
      'ePCR-App.',
  sections: [
    _PolicySection(
      'Lokale Daten',
      'Die App speichert die ausgewählte Serveradresse lokal. App-Token und '
          'server-/tokengebundene Offline-Snapshots werden über den sicheren '
          'Speicher des Betriebssystems geschützt. Beim Abmelden oder '
          'Serverwechsel werden Token und zugehöriger Offline-Cache entfernt.',
    ),
    _PolicySection(
      'Verbindung zum selbst gehosteten Server',
      'Anmeldung und Organisationsdaten wie Übergaben, Checklisten, Mängel, '
          'Geräte-/Fahrzeugstatus und Inventar werden nur an den Server '
          'übertragen, den Sie selbst eingerichtet haben. Ein Passwort für den '
          'Token-Austausch wird von der App nicht dauerhaft gespeichert.',
    ),
    _PolicySection(
      'Kamera und Fotos',
      'Beim QR-Scan werden Kameraframes nur zur Erkennung der Serveradresse '
          'verarbeitet und nicht als Foto hochgeladen. Ein Mängelfoto wird nur '
          'übertragen, wenn Sie es ausdrücklich aufnehmen oder aus der '
          'Fotomediathek auswählen. Patienten- oder Einsatzdaten gehören nicht '
          'in Mängelfotos.',
    ),
    _PolicySection(
      'Standort',
      'Ein optionaler ungefährer Standort wird ausschließlich lokal zur '
          'Berechnung von Sonnenaufgang und Sonnenuntergang für das '
          'Tag-/Nacht-Design verwendet und nach aktuellem App-Konzept nicht '
          'übertragen.',
    ),
    _PolicySection(
      'Werbung und Tracking',
      'Die App enthält keine Werbung, kein Werbe-SDK, kein Cross-App-Tracking '
          'und kein externes Analytics-/Crash-Tracking-SDK.',
    ),
    _PolicySection(
      'Konten und Löschung',
      'Benutzerkonten und serverseitige Daten werden vom Betreiber des '
          'verbundenen Wachbuch-Servers verwaltet. Auskunfts-, Berichtigungs- '
          'oder Löschanfragen zu diesen Daten sind an diesen Betreiber zu '
          'richten.',
    ),
  ],
  canonicalTitle: 'Vollständige Datenschutzerklärung',
  supportTitle: 'Support / Kontakt zur App',
  openPolicy: 'Datenschutzerklärung öffnen',
  openSupport: 'Support-Seite öffnen',
);

const _en = _PolicyCopy(
  title: 'Privacy',
  intro:
      'Wachbuch is an open-source client for self-hosted Wachbuch servers. '
      'The app does not operate a central Wachbuch cloud and is not an official '
      'government, emergency-calling, dispatch, patient-record or ePCR app.',
  sections: [
    _PolicySection(
      'Local data',
      'The selected server address is stored locally. App tokens and '
          'server/token-scoped offline snapshots are protected using operating '
          'system secure storage. Signing out or changing servers removes the '
          'associated token and offline cache.',
    ),
    _PolicySection(
      'Self-hosted server connection',
      'Authentication and organisational data such as handovers, checklists, '
          'defects, asset/vehicle status and inventory are sent only to the '
          'server you configured. A password used for token exchange is not '
          'persistently stored by the app.',
    ),
    _PolicySection(
      'Camera and photos',
      'QR camera frames are processed only to recognise the server address and '
          'are not uploaded as photos. A defect photo is transmitted only when '
          'you explicitly capture or select one. Patient or incident data '
          'should never be included in defect photos.',
    ),
    _PolicySection(
      'Location',
      'Optional approximate location is used locally only to calculate sunrise '
          'and sunset for the day/night theme and is not transmitted under the '
          'current app design.',
    ),
    _PolicySection(
      'Advertising and tracking',
      'The app contains no advertising, advertising SDK, cross-app tracking '
          'or external analytics/crash-tracking SDK.',
    ),
    _PolicySection(
      'Accounts and deletion',
      'User accounts and server-side data are managed by the operator of the '
          'Wachbuch server you connect to. Requests to access, correct or '
          'delete that data must be directed to that server operator.',
    ),
  ],
  canonicalTitle: 'Full privacy policy',
  supportTitle: 'App support / contact',
  openPolicy: 'Open privacy policy',
  openSupport: 'Open support page',
);
