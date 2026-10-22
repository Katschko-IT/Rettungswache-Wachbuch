/// Offline [WachbuchApi] backed by [DemoProfile] sample data.
library;

import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:wachbuch_mobile/models/crew_notice.dart';
import 'package:wachbuch_mobile/api/api_cache.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/models/checkliste.dart';
import 'package:wachbuch_mobile/models/defect.dart';
import 'package:wachbuch_mobile/models/defect_attachment.dart';
import 'package:wachbuch_mobile/models/handover_ack.dart';
import 'package:wachbuch_mobile/models/inventory_item.dart';
import 'package:wachbuch_mobile/models/kaffeekasse.dart';
import 'package:wachbuch_mobile/models/kalender_entry.dart';
import 'package:wachbuch_mobile/models/pinboard_note.dart';
import 'package:wachbuch_mobile/models/report_stats.dart';
import 'package:wachbuch_mobile/models/station_asset.dart';
import 'package:wachbuch_mobile/api/server_trust.dart';

const demoTokenPrefix = 'wb_demo_';
const _maxAttachmentBytes = 2 * 1024 * 1024;
const _maxAttachmentsPerDefect = 8;
const _maxAttachmentTotalBytes = 12 * 1024 * 1024;

/// Returns a demo API when [baseUrl] matches a [DemoService] host.
/// Real authenticated sessions receive a token-bound encrypted read cache.
WachbuchApi createWachbuchApi(String baseUrl, {String? token}) {
  final service = DemoService.fromServerUrl(baseUrl);
  if (service != null) {
    return DemoWachbuchApi(
      profile: demoProfileFor(service),
      token: token ?? '$demoTokenPrefix${service.id}',
    );
  }
  return WachbuchApi(
    baseUrl: baseUrl,
    token: token,
    // Lokales Zertifikat (Fingerabdruck aus dem Verbindungs-QR) oder System-TLS.
    client: ServerTrust.clientFor(baseUrl),
    cache: token == null || token.isEmpty
        ? null
        : SecureApiCache.forSession(baseUrl: baseUrl, token: token),
  );
}

/// Drop-in [WachbuchApiFactory] that routes demo hosts to [DemoWachbuchApi].
WachbuchApi demoAwareApiFactory(String baseUrl) => createWachbuchApi(baseUrl);

class _NoopClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    throw UnsupportedError('Demo API performs no network I/O.');
  }
}

List<PinboardNote> _demoPinboard() {
  final now = DateTime.now();
  return [
    PinboardNote(
      id: 2,
      title: 'Teamabend am Freitag',
      body: 'Gemeinsames Grillen ab 19 Uhr hinter der Wache. Bitte kurz eintragen.',
      category: 'event',
      isPinned: true,
      authorName: 'Demo',
      updatedAt: now.subtract(const Duration(hours: 3)),
    ),
    PinboardNote(
      id: 1,
      title: 'Neue Kaffeemaschine',
      body: 'Die neue Maschine steht im Aufenthaltsraum. Kurzanleitung hängt daneben.',
      category: 'info',
      isPinned: false,
      authorName: 'Demo',
      updatedAt: now.subtract(const Duration(days: 1)),
    ),
  ];
}


class DemoWachbuchApi extends WachbuchApi {
  DemoWachbuchApi({
    required this.profile,
    String? token,
    List<Defect>? defects,
    List<StationAsset>? assets,
    List<InventoryItem>? inventory,
    Map<int, List<HandoverAck>>? acks,
    Map<int, List<DefectAttachment>>? attachments,
    Map<int, Uint8List>? attachmentBytes,
    Set<int>? completedChecklists,
    List<PinboardNote>? pinboard,
  })  : _pinboard = List<PinboardNote>.from(pinboard ?? _demoPinboard()),
        _defects = List<Defect>.from(defects ?? profile.defects),
        _assets = List<StationAsset>.from(assets ?? profile.assets),
        _inventory = List<InventoryItem>.from(inventory ?? profile.inventory),
        _acks = {
          for (final entry in (acks ?? const <int, List<HandoverAck>>{}).entries)
            entry.key: List<HandoverAck>.from(entry.value),
        },
        _attachments = {
          for (final entry in
              (attachments ?? const <int, List<DefectAttachment>>{}).entries)
            entry.key: List<DefectAttachment>.from(entry.value),
        },
        _attachmentBytes = Map<int, Uint8List>.from(
          attachmentBytes ?? const <int, Uint8List>{},
        ),
        _completedChecklists = Set<int>.from(completedChecklists ?? const <int>{}),
        super(
          baseUrl: profile.service.serverUrl,
          token: token ?? '$demoTokenPrefix${profile.service.id}',
          client: _NoopClient(),
        );

  final DemoProfile profile;
  final Set<int> _completedChecklists;
  final List<PinboardNote> _pinboard;
  final List<Defect> _defects;
  final List<StationAsset> _assets;
  final List<InventoryItem> _inventory;
  final Map<int, List<HandoverAck>> _acks;
  final Map<int, List<DefectAttachment>> _attachments;
  final Map<int, Uint8List> _attachmentBytes;
  int _nextAttachmentId = 1;

  bool get isDemo => true;

  // Demo-Profile haben keine Fahrzeugsperren und keinen Posteingang.
  @override
  Future<List<VehicleLock>> vehicleLocks() async => const [];

  @override
  Future<List<CrewNotice>> crewNotices() async => const [];

  @override
  Future<void> markCrewNoticeRead(int id) async {}

  @override
  Future<Map<String, dynamic>> discover() async {
    return {
      'ok': true,
      'api_version': 'v1',
      'name': 'Wachbuch Demo',
      'demo': true,
      'service': profile.service.id,
      'capabilities': {
        'defects': true,
        'assets': true,
        'inventory': true,
        'handover_ack': true,
        'defect_attachments': true,
        'checklist_schedules': true,
        'reports': true,
      },
      'endpoints': {
        'token': '/api/v1/token/',
        'me': '/api/v1/me/',
        'handovers': '/api/v1/handovers/',
        'defects': '/api/v1/defects/',
        'assets': '/api/v1/assets/',
        'inventory': '/api/v1/inventory/',
        'reports': '/api/v1/reports/',
      },
    };
  }

  @override
  Future<AuthToken> obtainToken({
    required String username,
    required String password,
    String label = 'Mobile App',
  }) async {
    return AuthToken(
      value: '$demoTokenPrefix${profile.service.id}',
      expiresAt: DateTime.now().add(const Duration(days: 7)),
    );
  }

  @override
  Future<void> revokeCurrentToken() async {}

  @override
  Future<Map<String, dynamic>> me() async => Map<String, dynamic>.from(profile.me);

  @override
  Future<List<Map<String, dynamic>>> handovers() async {
    return profile.handovers
        .map((entry) => Map<String, dynamic>.from(entry))
        .toList(growable: false);
  }

  @override
  Future<Map<String, dynamic>> handoverDetail(int id) async {
    for (final entry in profile.handovers) {
      if (entry['id'] == id) {
        return Map<String, dynamic>.from(entry);
      }
    }
    throw ApiException(404, 'Übergabe nicht gefunden.');
  }

  @override
  Future<List<KalenderEntry>> kalender() async {
    return profile.calendar
        .map(KalenderEntry.fromJson)
        .toList(growable: false);
  }

  @override
  Future<Kaffeekasse> kaffeekasse() async {
    return Kaffeekasse.fromJson(Map<String, dynamic>.from(profile.coffee));
  }

  @override
  Future<List<Checklist>> checklisten() async {
    return profile.checklists.map((raw) {
      final id = raw['id'] as int? ?? 0;
      final completed =
          _completedChecklists.contains(id) || raw['completed'] == true;
      return Checklist.fromJson({...raw, 'completed': completed});
    }).toList(growable: false);
  }

  @override
  Future<Checklist> checklisteAbschluss(int id) async {
    _completedChecklists.add(id);
    final match = profile.checklists.cast<Map<String, dynamic>?>().firstWhere(
          (entry) => entry?['id'] == id,
          orElse: () => null,
        );
    if (match == null) {
      return Checklist(id: id, title: '', completed: true);
    }
    return Checklist.fromJson({...match, 'completed': true});
  }

  @override
  Future<List<PinboardNote>> pinboard() async =>
      List<PinboardNote>.unmodifiable(_pinboard);

  @override
  Future<PinboardNote> createPinboardNote({
    required String title,
    required String body,
    String category = 'info',
  }) async {
    final note = PinboardNote(
      id: (_pinboard.isEmpty
              ? 0
              : _pinboard.map((n) => n.id).reduce((a, b) => a > b ? a : b)) +
          1,
      title: title,
      body: body,
      category: category,
      authorName: 'Demo',
      updatedAt: DateTime.now(),
    );
    _pinboard.insert(0, note);
    return note;
  }

  @override
  Future<List<Defect>> defects() async => List<Defect>.unmodifiable(_defects);

  @override
  Future<Defect> createDefect({
    required String title,
    String description = '',
    String assetRef = '',
    String priority = 'normal',
    String category = 'task',
    String? owner,
    DateTime? dueAt,
  }) async {
    final id = _defects.fold<int>(0, (maxId, item) => item.id > maxId ? item.id : maxId) + 1;
    final item = Defect.fromJson({
      'id': id,
      'title': title,
      'description': description,
      'asset_ref': assetRef,
      'priority': priority,
      'status': 'open',
      'owner': owner ?? profile.username,
      'due_at': dueAt?.toIso8601String(),
      'category': category,
    });
    _defects.insert(0, item);
    return item;
  }

  @override
  Future<Defect> updateDefectStatus(int id, String status) async {
    final index = _defects.indexWhere((defect) => defect.id == id);
    if (index < 0) throw ApiException(404, 'Mangel nicht gefunden.');
    final updated = Defect.fromJson({
      ..._defects[index].toJson(),
      'status': status,
    });
    _defects[index] = updated;
    return updated;
  }

  @override
  Future<List<DefectAttachment>> defectAttachments(int defectId) async {
    return List<DefectAttachment>.unmodifiable(
      _attachments[defectId] ?? const <DefectAttachment>[],
    );
  }

  @override
  Future<DefectAttachment> uploadDefectAttachment(
    int defectId, {
    required String filename,
    required String contentType,
    required Uint8List bytes,
  }) async {
    if (!_defects.any((item) => item.id == defectId)) {
      throw ApiException(404, 'Mangel nicht gefunden.');
    }
    if (bytes.isEmpty || bytes.length > _maxAttachmentBytes) {
      throw ApiException(413, 'Bild darf maximal 2 MiB groß sein.');
    }

    final normalizedType = contentType.toLowerCase() == 'image/jpg'
        ? 'image/jpeg'
        : contentType.toLowerCase();
    if (!_imageMatches(bytes, normalizedType)) {
      throw ApiException(415, 'Nur gültige JPEG-, PNG- oder WebP-Bilder sind erlaubt.');
    }

    final current = _attachments[defectId] ?? const <DefectAttachment>[];
    if (current.length >= _maxAttachmentsPerDefect) {
      throw ApiException(409, 'Maximal 8 Fotos pro Mangel sind erlaubt.');
    }
    final totalBytes = current.fold<int>(0, (sum, item) => sum + item.size);
    if (totalBytes + bytes.length > _maxAttachmentTotalBytes) {
      throw ApiException(413, 'Gesamtgröße der Fotos pro Mangel darf 12 MiB nicht überschreiten.');
    }

    final id = _nextAttachmentId++;
    final item = DefectAttachment(
      id: id,
      defectId: defectId,
      filename: filename,
      contentType: normalizedType,
      size: bytes.length,
      createdAt: DateTime.now(),
      uploadedBy: profile.username,
      downloadUrl: '/api/v1/attachments/$id/',
    );
    _attachments.putIfAbsent(defectId, () => <DefectAttachment>[]).add(item);
    _attachmentBytes[id] = Uint8List.fromList(bytes);
    return item;
  }

  bool _imageMatches(Uint8List bytes, String contentType) {
    if (contentType == 'image/jpeg') {
      return bytes.length >= 3 &&
          bytes[0] == 0xff &&
          bytes[1] == 0xd8 &&
          bytes[2] == 0xff;
    }
    if (contentType == 'image/png') {
      const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
      return bytes.length >= signature.length &&
          List.generate(signature.length, (i) => bytes[i])
              .asMap()
              .entries
              .every((entry) => entry.value == signature[entry.key]);
    }
    if (contentType == 'image/webp') {
      return bytes.length >= 12 &&
          String.fromCharCodes(bytes.sublist(0, 4)) == 'RIFF' &&
          String.fromCharCodes(bytes.sublist(8, 12)) == 'WEBP';
    }
    return false;
  }

  @override
  Future<Uint8List> downloadAttachment(int id) async {
    final bytes = _attachmentBytes[id];
    if (bytes == null) throw ApiException(404, 'Anhang nicht gefunden.');
    return Uint8List.fromList(bytes);
  }

  @override
  Future<List<StationAsset>> assets() async =>
      List<StationAsset>.unmodifiable(_assets);

  @override
  Future<StationAsset> createAsset({
    required String id,
    required String label,
    String kind = 'device',
  }) async {
    if (_assets.any((item) => item.id == id)) {
      throw ApiException(409, 'Asset-ID existiert bereits.');
    }
    final item = StationAsset(id: id, label: label, kind: kind);
    _assets.add(item);
    return item;
  }

  @override
  Future<StationAsset> updateAssetStatus(
    String id, {
    required String status,
    String note = '',
  }) async {
    final index = _assets.indexWhere((item) => item.id == id);
    if (index < 0) throw ApiException(404, 'Asset nicht gefunden.');
    final updated = _assets[index].copyWith(status: status, note: note);
    _assets[index] = updated;
    return updated;
  }

  @override
  Future<List<InventoryItem>> inventory() async =>
      List<InventoryItem>.unmodifiable(_inventory);

  @override
  Future<InventoryItem> createInventoryItem({
    required String id,
    required String label,
    String kind = 'device',
  }) async {
    if (_inventory.any((item) => item.id == id)) {
      throw ApiException(409, 'Inventar-ID existiert bereits.');
    }
    final item = InventoryItem(id: id, label: label, kind: kind);
    _inventory.add(item);
    return item;
  }

  @override
  Future<InventoryItem> inventoryCheckout(String id) async {
    final index = _inventory.indexWhere((item) => item.id == id);
    if (index < 0) throw ApiException(404, 'Inventar nicht gefunden.');
    if (_inventory[index].isOut && _inventory[index].holder != profile.username) {
      throw ApiException(409, 'Inventar ist bereits ausgegeben.');
    }
    final updated = _inventory[index].copyWith(
      holder: profile.username,
      since: DateTime.now(),
      sinceLabel: 'gerade eben',
    );
    _inventory[index] = updated;
    return updated;
  }

  @override
  Future<InventoryItem> inventoryCheckin(String id) async {
    final index = _inventory.indexWhere((item) => item.id == id);
    if (index < 0) throw ApiException(404, 'Inventar nicht gefunden.');
    final updated = _inventory[index].copyWith(clearHolder: true);
    _inventory[index] = updated;
    return updated;
  }

  @override
  Future<List<HandoverAck>> handoverAcks(int id) async {
    return List<HandoverAck>.unmodifiable(_acks[id] ?? const []);
  }

  @override
  Future<HandoverAck> acknowledgeHandover(int id) async {
    final exists = profile.handovers.any((entry) => entry['id'] == id);
    if (!exists) throw ApiException(404, 'Übergabe nicht gefunden.');
    final by = profile.username;
    final current = _acks.putIfAbsent(id, () => <HandoverAck>[]);
    final existing = current.where((ack) => ack.by == by);
    if (existing.isNotEmpty) return existing.first;
    final ack = HandoverAck(handoverId: id, by: by, at: DateTime.now());
    current.add(ack);
    return ack;
  }

  @override
  Future<WachalltagReport> reportStats() async {
    final now = DateTime.now();
    final open = _defects.where((item) => item.status != 'done').toList();
    final overdue = open
        .where((item) => item.dueAt != null && item.dueAt!.isBefore(now))
        .length;
    final owners = <String, int>{};
    for (final item in open) {
      final owner = item.owner;
      owners[owner] = (owners[owner] ?? 0) + 1;
    }
    final ready = _assets.where((item) => item.status == 'ready').length;
    return WachalltagReport(
      openDefects: open.length,
      overdueDefects: overdue,
      overdueChecks: profile.checklists.where((item) => item['overdue'] == true).length,
      assetsTotal: _assets.length,
      assetsReady: ready,
      assetReadyPercent: _assets.isEmpty ? 0 : ((ready / _assets.length) * 100).round(),
      inventoryOut: _inventory.where((item) => item.isOut).length,
      unacknowledgedActiveHandovers: profile.handovers
          .where((h) => h['status'] != 'done')
          .where((h) => !(_acks[h['id']] ?? const <HandoverAck>[])
              .any((ack) => ack.by == profile.username))
          .length,
      oldestOpenDays: 0,
      defectsByOwner: owners.entries
          .map((entry) => ReportOwnerCount(owner: entry.key, count: entry.value))
          .toList(growable: false),
    );
  }

  @override
  DemoWachbuchApi copyWithToken(String newToken) {
    return DemoWachbuchApi(
      profile: profile,
      token: newToken,
      defects: _defects,
      assets: _assets,
      inventory: _inventory,
      acks: _acks,
      attachments: _attachments,
      attachmentBytes: _attachmentBytes,
      completedChecklists: _completedChecklists,
    );
  }

  @override
  void close() {
    // Noop client — nothing to close.
  }
}
