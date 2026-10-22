import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

/// Information about an available update
class UpdateInfo {
  final bool hasUpdate;
  final String currentVersion;
  final String latestVersion;
  final int? versionCode;
  final String platform;
  final DateTime? releaseDate;
  final List<ChangelogEntry> changelog;
  final String? downloadUrl;
  final bool forceUpdate;
  final String? minRequiredVersion;

  const UpdateInfo({
    required this.hasUpdate,
    required this.currentVersion,
    required this.latestVersion,
    this.versionCode,
    required this.platform,
    this.releaseDate,
    required this.changelog,
    this.downloadUrl,
    this.forceUpdate = false,
    this.minRequiredVersion,
  });

  factory UpdateInfo.fromJson(Map<String, dynamic> json) {
    return UpdateInfo(
      hasUpdate: json['has_update'] as bool? ?? false,
      currentVersion: json['current_version'] as String? ?? '',
      latestVersion: json['latest_version'] as String? ?? '',
      versionCode: json['version_code'] as int?,
      platform: json['platform'] as String? ?? '',
      releaseDate: json['release_date'] != null
          ? DateTime.parse(json['release_date'] as String)
          : null,
      changelog: (json['changelog'] as List<dynamic>?)
          ?.map((e) => ChangelogEntry.fromJson(e as Map<String, dynamic>))
          .toList() ?? [],
      downloadUrl: json['download_url'] as String?,
      forceUpdate: json['force_update'] as bool? ?? false,
      minRequiredVersion: json['min_required_version'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
    'has_update': hasUpdate,
    'current_version': currentVersion,
    'latest_version': latestVersion,
    'version_code': versionCode,
    'platform': platform,
    'release_date': releaseDate?.toIso8601String(),
    'changelog': changelog.map((e) => e.toJson()).toList(),
    'download_url': downloadUrl,
    'force_update': forceUpdate,
    'min_required_version': minRequiredVersion,
  };
}

/// A single changelog entry for a version
class ChangelogEntry {
  final String version;
  final String date;
  final List<String> changes;

  const ChangelogEntry({
    required this.version,
    required this.date,
    required this.changes,
  });

  factory ChangelogEntry.fromJson(Map<String, dynamic> json) {
    return ChangelogEntry(
      version: json['version'] as String? ?? '',
      date: json['date'] as String? ?? '',
      changes: (json['changes'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList() ?? [],
    );
  }

  Map<String, dynamic> toJson() => {
    'version': version,
    'date': date,
    'changes': changes,
  };
}

/// Service for checking app updates
class UpdateService {
  static const String _checkUpdateUrl = '/api/v1/check-update/';
  static const String _lastUpdateCheckKey = 'last_update_check';
  static const String _ignoredVersionKey = 'ignored_update_version';
  static const Duration _updateCheckInterval = Duration(hours: 24);

  final String baseUrl;
  final http.Client client;

  UpdateService({
    required this.baseUrl,
    http.Client? client,
  }) : client = client ?? http.Client();

  /// Check if there's an update available
  Future<UpdateInfo?> checkForUpdates() async {
    try {
      // Get current app version
      final packageInfo = await PackageInfo.fromPlatform();
      final currentVersion = packageInfo.version;
      final platform = _getPlatform();

      // Rate limiting: at most one network check per interval.
      final prefs = await SharedPreferences.getInstance();
      final lastCheck = prefs.getString(_lastUpdateCheckKey);
      if (lastCheck != null) {
        final lastCheckDate = DateTime.parse(lastCheck);
        if (DateTime.now().difference(lastCheckDate) < _updateCheckInterval) {
          return null; // Too soon to check again
        }
      }

      // Make request to server
      final uri = Uri.parse(
        '$baseUrl$_checkUpdateUrl?current_version=$currentVersion&platform=$platform',
      );

      final response = await client.get(uri);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;

        if (data['ok'] as bool? ?? false) {
          final updateInfo = UpdateInfo.fromJson(data);

          // Save last check time
          await prefs.setString(_lastUpdateCheckKey, DateTime.now().toIso8601String());

          // Honour a previously ignored version. `ignoreUpdate()` stores the
          // *latest* (offered) version, so the comparison must be against the
          // version the server just reported — not the installed version.
          final ignoredVersion = prefs.getString(_ignoredVersionKey);
          if (ignoredVersion != null &&
              ignoredVersion.isNotEmpty &&
              ignoredVersion == updateInfo.latestVersion) {
            return null; // User ignored this version
          }

          return updateInfo;
        }
      }
    } catch (e) {
      debugPrint('Failed to check for updates: $e');
    }
    return null;
  }

  /// Mark an update as ignored by the user
  Future<void> ignoreUpdate(String version) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_ignoredVersionKey, version);
  }

  /// Check if the current version is below the minimum required version
  Future<bool> isVersionForced() async {
    try {
      final updateInfo = await checkForUpdates();
      if (updateInfo != null && updateInfo.forceUpdate) {
        return true;
      }
    } catch (e) {
      debugPrint('Failed to check forced update: $e');
    }
    return false;
  }

  /// Open the download URL in a browser.
  /// Only HTTPS URLs are accepted; the server controls the URL and must not
  /// be able to trigger arbitrary app schemes or plain-HTTP downloads.
  Future<bool> openDownloadUrl(UpdateInfo updateInfo) async {
    final raw = updateInfo.downloadUrl;
    if (raw == null || raw.isEmpty) return false;
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || uri.scheme != 'https') {
      return false;
    }
    if (await canLaunchUrl(uri)) {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    return false;
  }

  /// Get the current platform
  String _getPlatform() {
    if (Platform.isAndroid) {
      return 'android';
    } else if (Platform.isIOS) {
      return 'ios';
    } else {
      return 'web';
    }
  }
}
