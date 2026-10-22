class Kaffeekasse {
  const Kaffeekasse({
    required this.balance,
    required this.currency,
    this.ledger = const [],
    this.paymentHint = '',
  });

  /// Server (`GET /api/v1/kaffeekasse/`) liefert `balance_euros` und
  /// `results`; die übrigen Schlüssel bleiben als Rückfall erhalten.
  factory Kaffeekasse.fromJson(Map<String, dynamic> json) {
    final currency = (json['currency'] ?? 'EUR').toString();
    return Kaffeekasse(
      balance: _formatMoney(
        json['balance_euros'] ?? json['balance'] ?? json['saldo'],
        currency,
      ),
      currency: currency,
      ledger: _readLedger(
        json['results'] ?? json['ledger'] ?? json['transactions'] ?? const [],
      ),
      paymentHint:
          (json['payment_hint'] ?? json['payment'] ?? '').toString().trim(),
    );
  }

  final String balance;
  final String currency;
  final List<KaffeekasseEntry> ledger;
  final String paymentHint;

  bool get isNegative => _parseMoney(balance).isNegative;
}

class KaffeekasseEntry {
  const KaffeekasseEntry({
    required this.id,
    required this.amount,
    this.description = '',
    this.userName = '',
    this.createdAt,
  });

  factory KaffeekasseEntry.fromJson(Map<String, dynamic> json) {
    return KaffeekasseEntry(
      id: _readInt(json['id']),
      amount: _parseMoney(json['amount_euros'] ?? json['amount'] ?? json['value']),
      description:
          (json['reason'] ?? json['description'] ?? json['memo'] ?? '')
              .toString()
              .trim(),
      userName: _readUser(json['user'] ?? json['member']),
      createdAt: _readDate(json['created_at'] ?? json['date']),
    );
  }

  final int id;
  final num amount;
  final String description;
  final String userName;
  final DateTime? createdAt;

  bool get isNegative => amount < 0;

  String get formattedAmount => _formatSignedMoney(amount);
}

List<KaffeekasseEntry> _readLedger(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((entry) => KaffeekasseEntry.fromJson(Map<String, dynamic>.from(entry)))
      .toList(growable: false);
}

String _readUser(Object? value) {
  if (value is Map) {
    return (value['display_name'] ?? value['name'] ?? '').toString().trim();
  }
  return value?.toString().trim() ?? '';
}

num _parseMoney(Object? value) {
  if (value is num) return value;
  final raw = value?.toString().trim() ?? '';
  if (raw.isEmpty) return 0;
  var cleaned = raw.replaceAll(RegExp(r'[^0-9,.\-]'), '');
  final hasComma = cleaned.contains(',');
  final hasDot = cleaned.contains('.');
  if (hasComma && hasDot) {
    cleaned = cleaned.replaceAll('.', '').replaceAll(',', '.');
  } else if (hasComma) {
    cleaned = cleaned.replaceAll(',', '.');
  }
  return num.tryParse(cleaned) ?? 0;
}

String _currencySymbol(String currency) =>
    switch (currency.toUpperCase()) { 'EUR' => '€', 'USD' => r'$', _ => currency };

String _formatMoney(Object? value, String currency) {
  final amount = _parseMoney(value);
  final absolute = amount.abs().toStringAsFixed(2).replaceAll('.', ',');
  final sign = amount < 0 ? '-' : '';
  return '$sign$absolute ${_currencySymbol(currency)}';
}

String _formatSignedMoney(num amount) {
  final absolute = amount.abs().toStringAsFixed(2).replaceAll('.', ',');
  if (amount < 0) return '-$absolute €';
  if (amount > 0) return '+$absolute €';
  return '$absolute €';
}

DateTime? _readDate(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toLocal();
}

int _readInt(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
