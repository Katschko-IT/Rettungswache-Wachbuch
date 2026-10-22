class ReportOwnerCount {
  const ReportOwnerCount({required this.owner, required this.count});

  factory ReportOwnerCount.fromJson(Map<String, dynamic> json) => ReportOwnerCount(
        owner: (json['owner'] ?? '').toString(),
        count: _readInt(json['count']),
      );

  final String owner;
  final int count;
}

class WachalltagReport {
  const WachalltagReport({
    required this.openDefects,
    required this.overdueDefects,
    required this.overdueChecks,
    required this.assetsTotal,
    required this.assetsReady,
    required this.assetReadyPercent,
    required this.inventoryOut,
    required this.unacknowledgedActiveHandovers,
    required this.oldestOpenDays,
    this.defectsByOwner = const [],
  });

  factory WachalltagReport.fromJson(Map<String, dynamic> json) {
    final owners = json['defects_by_owner'];
    return WachalltagReport(
      openDefects: _readInt(json['open_defects']),
      overdueDefects: _readInt(json['overdue_defects']),
      overdueChecks: _readInt(json['overdue_checks']),
      assetsTotal: _readInt(json['assets_total']),
      assetsReady: _readInt(json['assets_ready']),
      assetReadyPercent: _readInt(json['asset_ready_percent']),
      inventoryOut: _readInt(json['inventory_out']),
      unacknowledgedActiveHandovers: _readInt(json['unacknowledged_active_handovers']),
      oldestOpenDays: _readInt(json['oldest_open_days']),
      defectsByOwner: owners is List
          ? owners
              .whereType<Map>()
              .map((row) => ReportOwnerCount.fromJson(Map<String, dynamic>.from(row)))
              .toList(growable: false)
          : const [],
    );
  }

  final int openDefects;
  final int overdueDefects;
  final int overdueChecks;
  final int assetsTotal;
  final int assetsReady;
  final int assetReadyPercent;
  final int inventoryOut;
  final int unacknowledgedActiveHandovers;
  final int oldestOpenDays;
  final List<ReportOwnerCount> defectsByOwner;
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
