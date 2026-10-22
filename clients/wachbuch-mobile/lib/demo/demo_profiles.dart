/// Local demo profiles for RD, Feuerwehr, FFW and Polizei.
/// Offline-only sample data — never used against a real server.
library;

import 'package:wachbuch_mobile/models/defect.dart';
import 'package:wachbuch_mobile/models/inventory_item.dart';
import 'package:wachbuch_mobile/models/station_asset.dart';

enum DemoService {
  rettungsdienst,
  feuerwehr,
  ffw,
  polizei;

  String get id => name;

  String get host => 'demo-$name.wachbuch.local';

  /// Persisted origin used by [SessionStore] / [WachbuchApi.baseUrl].
  String get serverUrl => 'https://$host';

  static DemoService? fromServerUrl(String url) {
    final host = Uri.tryParse(url)?.host;
    if (host == null) return null;
    for (final service in DemoService.values) {
      if (host == service.host) return service;
    }
    return null;
  }

  static bool isDemoUrl(String url) => fromServerUrl(url) != null;
}

class DemoProfile {
  const DemoProfile({
    required this.service,
    required this.stationName,
    required this.roleLabel,
    required this.username,
    required this.tagline,
    required this.handovers,
    required this.calendar,
    required this.coffee,
    required this.checklists,
    this.defects = const [],
    this.assets = const [],
    this.inventory = const [],
  });

  final DemoService service;
  final String stationName;
  final String roleLabel;
  final String username;
  final String tagline;
  final List<Map<String, dynamic>> handovers;
  final List<Map<String, dynamic>> calendar;
  final Map<String, dynamic> coffee;
  final List<Map<String, dynamic>> checklists;
  final List<Defect> defects;
  final List<StationAsset> assets;
  final List<InventoryItem> inventory;

  Map<String, dynamic> get me => {
        'username': username,
        'user': {'username': username},
        'membership': {
          'role_label': roleLabel,
          'station': {
            'name': stationName,
            'modules': {
              'calendar': true,
              'coffee': true,
              'checklists': true,
              'birthdays': true,
              'defects': true,
              'assets': true,
              'inventory': true,
            },
          },
        },
      };
}

DemoProfile demoProfileFor(DemoService service) {
  return switch (service) {
    DemoService.rettungsdienst => _rettungsdienst,
    DemoService.feuerwehr => _feuerwehr,
    DemoService.ffw => _ffw,
    DemoService.polizei => _polizei,
  };
}

final _now = DateTime.now();

String _iso(DateTime dt) => dt.toUtc().toIso8601String();

final _rettungsdienst = DemoProfile(
  service: DemoService.rettungsdienst,
  stationName: 'Rettungswache Musterstadt',
  roleLabel: 'Schichtleitung',
  username: 'demo-schicht',
  tagline: 'Schichtübergabe, Material und Wachalltag für den Rettungsdienst.',
  handovers: [
    {
      'id': 1,
      'title': '[Demo] RTW 1 – Defibrillator-Akku tauschen',
      'description':
          'Akku zeigt unter 40 %. Ersatzakku aus dem Materiallager entnehmen und Gerät neu kalibrieren.',
      'status': 'open',
      'priority': 'urgent',
      'category': 'material',
      'author': 'demo-schicht',
      'updated_at': _iso(_now.subtract(const Duration(minutes: 25))),
      'version': 2,
    },
    {
      'id': 2,
      'title': '[Demo] Funkgerät Wachzimmer knackt',
      'description':
          'Kanal 4 mit Störgeräusch. IT informiert; bis dahin Ersatzgerät aus Spind B nutzen.',
      'status': 'in_progress',
      'priority': 'important',
      'category': 'station',
      'author': 'demo-mitglied',
      'updated_at': _iso(_now.subtract(const Duration(hours: 2))),
      'version': 1,
    },
    {
      'id': 3,
      'title': '[Demo] Kühlschrank Medikamente – Temperaturlog fehlt',
      'description': 'Bitte heutige Temperaturwerte nachtragen und Kühlkette dokumentieren.',
      'status': 'open',
      'priority': 'normal',
      'category': 'task',
      'author': 'demo-admin',
      'updated_at': _iso(_now.subtract(const Duration(hours: 5))),
      'version': 1,
    },
    {
      'id': 4,
      'title': '[Demo] Kaffeekasse – Nachzahlung Schicht A',
      'description': 'Schicht A hat Nachzahlung erledigt. Beleg liegt in der Kasse.',
      'status': 'done',
      'priority': 'normal',
      'category': 'station',
      'author': 'demo-kasse',
      'updated_at': _iso(_now.subtract(const Duration(days: 1))),
      'version': 3,
    },
  ],
  assets: const [
    StationAsset(id: 'rtw-1', label: 'RTW 1', kind: 'vehicle', status: 'limited', note: 'Defi-Akku schwach'),
    StationAsset(id: 'rtw-2', label: 'RTW 2', kind: 'vehicle', status: 'ready'),
    StationAsset(id: 'ktw-1', label: 'KTW 1', kind: 'vehicle', status: 'ready'),
    StationAsset(id: 'funk-wache', label: 'Funk Wachzimmer', kind: 'device', status: 'limited', note: 'Kanal 4'),
  ],
  inventory: const [
    InventoryItem(id: 'funk-a', label: 'Funkgerät A', kind: 'device'),
    InventoryItem(
      id: 'funk-b',
      label: 'Funkgerät B',
      kind: 'device',
      holder: 'demo-mitglied',
      sinceLabel: 'heute 06:10',
    ),
  ],
  defects: [
    Defect(
      id: 101,
      title: 'Defi-Akku RTW 1 unter 40 %',
      description: 'Ersatz aus Materiallager, Gerät kalibrieren.',
      assetRef: 'RTW 1',
      priority: 'urgent',
      status: 'open',
      owner: 'demo-schicht',
      dueLabel: 'heute 14:00',
      category: 'material',
    ),
    Defect(
      id: 102,
      title: 'Kühlschrank-Temperaturlog fehlt',
      description: 'Heutige Werte nachtragen.',
      assetRef: 'Medikamentenkühlung',
      priority: 'important',
      status: 'open',
      owner: 'demo-mitglied',
      dueLabel: 'heute 18:00',
      category: 'facility',
    ),
    Defect(
      id: 103,
      title: 'Funkgerät Wachzimmer',
      description: 'IT informiert, Ersatzgerät Spind B.',
      assetRef: 'Funk Wachzimmer',
      priority: 'important',
      status: 'in_progress',
      owner: 'demo-admin',
      dueLabel: 'morgen',
      category: 'device',
    ),
  ],
  calendar: [
    {
      'id': 1,
      'title': 'Geräteprüfung RTW',
      'description': 'Wöchentliche Sicht- und Funktionsprüfung',
      'start': _iso(_now.add(const Duration(hours: 3))),
      'end': _iso(_now.add(const Duration(hours: 4))),
      'all_day': false,
      'location': 'Fahrzeughalle',
    },
    {
      'id': 2,
      'title': 'Teambesprechung Hygiene',
      'start': _iso(_now.add(const Duration(days: 1, hours: 9))),
      'end': _iso(_now.add(const Duration(days: 1, hours: 10))),
      'all_day': false,
      'location': 'Wachzimmer',
    },
  ],
  coffee: {
    'balance': '42.50',
    'currency': 'EUR',
    'payment_hint': 'Bitte bar in die Kasse oder per Überweisung an die Wache.',
    'ledger': [
      {
        'id': 1,
        'amount': '-12.00',
        'description': 'Milch & Filterkaffee',
        'created_at': _iso(_now.subtract(const Duration(days: 1))),
        'user': 'demo-kasse',
      },
      {
        'id': 2,
        'amount': '20.00',
        'description': 'Nachzahlung Schicht A',
        'created_at': _iso(_now.subtract(const Duration(days: 1, hours: 2))),
        'user': 'demo-mitglied',
      },
    ],
  },
  checklists: [
    {
      'id': 1,
      'title': 'Fahrzeugcheck RTW 1',
      'completed': false,
      'interval': 'daily',
      'due_next': _iso(_now),
      'overdue': false,
      'items': [
        {'id': 1, 'text': 'Sauerstoffflasche voll', 'checked': true},
        {'id': 2, 'text': 'Trage gereinigt', 'checked': true},
        {'id': 3, 'text': 'Medikamentenschrank inventiert', 'checked': false},
      ],
    },
    {
      'id': 2,
      'title': 'Wachabschluss',
      'completed': false,
      'interval': 'daily',
      'due_next': _iso(_now.subtract(const Duration(days: 1))),
      'overdue': true,
      'items': [
        {'id': 4, 'text': 'Müll entsorgt', 'checked': false},
        {'id': 5, 'text': 'Schlüsselübergabe', 'checked': false},
      ],
    },
  ],
);

final _feuerwehr = DemoProfile(
  service: DemoService.feuerwehr,
  stationName: 'Feuerwehrwache Nord',
  roleLabel: 'Wachabteilungsführer',
  username: 'demo-waf',
  tagline: 'Gerätehaus, Fahrzeuge und Dienstübergabe für die Feuerwehr.',
  handovers: [
    {
      'id': 11,
      'title': '[Demo] HLF 20 – Atemschutzgerät 3 außer Betrieb',
      'description':
          'Druckminderer undicht. Gerät gekennzeichnet und Werkstatt informiert. Ersatz aus Reservehalle.',
      'status': 'open',
      'priority': 'urgent',
      'category': 'vehicle',
      'author': 'demo-waf',
      'updated_at': _iso(_now.subtract(const Duration(minutes: 40))),
      'version': 1,
    },
    {
      'id': 12,
      'title': '[Demo] Hydrantentest Strasse 12 verschoben',
      'description': 'Wegen Baustelle auf Donnerstag verlegt. Neue Liste liegt am Melder.',
      'status': 'in_progress',
      'priority': 'important',
      'category': 'task',
      'author': 'demo-mitglied',
      'updated_at': _iso(_now.subtract(const Duration(hours: 3))),
      'version': 2,
    },
    {
      'id': 13,
      'title': '[Demo] Schlauchturm – Beleuchtung defekt',
      'description': 'Obere Leuchte flackert. Elektrofirma angefragt.',
      'status': 'open',
      'priority': 'normal',
      'category': 'safety',
      'author': 'demo-admin',
      'updated_at': _iso(_now.subtract(const Duration(hours: 8))),
      'version': 1,
    },
    {
      'id': 14,
      'title': '[Demo] Übung Löschangriff abgeschlossen',
      'description': 'Protokoll unterschrieben, Material wieder einsatzklar.',
      'status': 'done',
      'priority': 'normal',
      'category': 'station',
      'author': 'demo-waf',
      'updated_at': _iso(_now.subtract(const Duration(days: 1))),
      'version': 1,
    },
  ],
  assets: const [
    StationAsset(id: 'hlf-20', label: 'HLF 20', kind: 'vehicle', status: 'limited', note: 'Atemschutz 3 OOB'),
    StationAsset(id: 'dlk', label: 'DLK', kind: 'vehicle', status: 'ready'),
    StationAsset(id: 'as-3', label: 'Atemschutz 3', kind: 'device', status: 'oob', note: 'Werkstatt'),
    StationAsset(id: 'as-4', label: 'Atemschutz 4', kind: 'device', status: 'ready', note: 'Ersatz'),
  ],
  inventory: const [
    InventoryItem(
      id: 'key-halle',
      label: 'Schlüssel Fahrzeughalle',
      kind: 'key',
      holder: 'demo-waf',
      sinceLabel: 'heute 06:00',
    ),
    InventoryItem(id: 'as-reserve', label: 'Atemschutz Reserve', kind: 'device'),
  ],
  defects: const [
    Defect(
      id: 111,
      title: 'Atemschutzgerät 3 undicht',
      description: 'Druckminderer, Werkstatt informiert.',
      assetRef: 'Atemschutz 3',
      priority: 'urgent',
      status: 'open',
      owner: 'demo-waf',
      dueLabel: 'heute',
      category: 'device',
    ),
    Defect(
      id: 112,
      title: 'Schlauchturm-Beleuchtung',
      description: 'Elektrofirma angefragt.',
      assetRef: 'Gerätehaus',
      priority: 'normal',
      status: 'waiting',
      owner: 'demo-admin',
      dueLabel: 'Freitag',
      category: 'facility',
    ),
  ],
  calendar: [
    {
      'id': 11,
      'title': 'Atemschutz-Übung',
      'description': 'Bahn 2 – Vollschutz',
      'start': _iso(_now.add(const Duration(hours: 5))),
      'end': _iso(_now.add(const Duration(hours: 7))),
      'all_day': false,
      'location': 'Übungsanlage',
    },
    {
      'id': 12,
      'title': 'Fahrzeugpflege DLK',
      'start': _iso(_now.add(const Duration(days: 2))),
      'end': _iso(_now.add(const Duration(days: 2, hours: 2))),
      'all_day': false,
      'location': 'Fahrzeughalle',
    },
  ],
  coffee: {
    'balance': '18.75',
    'currency': 'EUR',
    'payment_hint': 'Kaffeekasse Gerätehaus – Einwurf neben dem Melder.',
    'ledger': [
      {
        'id': 11,
        'amount': '-8.50',
        'description': 'Kaffee & Zucker',
        'created_at': _iso(_now.subtract(const Duration(days: 2))),
        'user': 'demo-kasse',
      },
    ],
  },
  checklists: [
    {
      'id': 11,
      'title': 'Fahrzeugcheck HLF 20',
      'completed': false,
      'interval': 'daily',
      'due_next': _iso(_now),
      'items': [
        {'id': 11, 'text': 'Pumpe Funktionstest', 'checked': true},
        {'id': 12, 'text': 'Atemschutz vollzählig', 'checked': false},
        {'id': 13, 'text': 'Funkprobe', 'checked': true},
      ],
    },
    {
      'id': 12,
      'title': 'Wochencheck Gerätehaus',
      'completed': false,
      'interval': 'weekly',
      'due_next': _iso(_now.subtract(const Duration(days: 2))),
      'overdue': true,
      'items': [
        {'id': 14, 'text': 'Notstromaggregat geprüft', 'checked': false},
        {'id': 15, 'text': 'Schlauchlager Ordnung', 'checked': false},
      ],
    },
  ],
);

final _ffw = DemoProfile(
  service: DemoService.ffw,
  stationName: 'FFW Musterdorf',
  roleLabel: 'Wehrführung',
  username: 'demo-wf',
  tagline: 'Gerätehaus-Alltag und asynchrone To-dos für die Freiwillige Feuerwehr.',
  handovers: [
    {
      'id': 31,
      'title': '[Demo] Gerätehaus – Heizung macht Geräusche',
      'description': 'Heizungstechniker für Samstag vormerken.',
      'status': 'open',
      'priority': 'important',
      'category': 'station',
      'author': 'demo-wf',
      'updated_at': _iso(_now.subtract(const Duration(days: 2))),
      'version': 1,
    },
    {
      'id': 32,
      'title': '[Demo] Übung Verkehrsabsicherung – Material fehlt',
      'description': '2 Leitkegel und 1 Warnweste nachbestellen.',
      'status': 'open',
      'priority': 'normal',
      'category': 'material',
      'author': 'demo-ausbilder',
      'updated_at': _iso(_now.subtract(const Duration(days: 2, hours: 4))),
      'version': 1,
    },
    {
      'id': 33,
      'title': '[Demo] Jugendfeuerwehr – Raum aufgeräumt',
      'description': 'Nach Gruppenstunde erledigt.',
      'status': 'done',
      'priority': 'normal',
      'category': 'station',
      'author': 'demo-jugend',
      'updated_at': _iso(_now.subtract(const Duration(days: 1))),
      'version': 1,
    },
  ],
  assets: const [
    StationAsset(id: 'lf-kat', label: 'LF-KatS', kind: 'vehicle', status: 'ready'),
    StationAsset(id: 'ts', label: 'TS', kind: 'vehicle', status: 'limited', note: 'Batterie schwach'),
    StationAsset(id: 'heizung', label: 'Heizung Gerätehaus', kind: 'device', status: 'limited', note: 'Geräusche'),
  ],
  inventory: const [
    InventoryItem(id: 'key-gh', label: 'Ersatzschlüssel Gerätehaus', kind: 'key'),
    InventoryItem(
      id: 'tablet-ausbildung',
      label: 'Ausbildungstablet',
      kind: 'device',
      holder: 'demo-ausbilder',
      sinceLabel: 'gestern',
    ),
  ],
  defects: const [
    Defect(
      id: 131,
      title: 'Heizung Gerätehaus',
      description: 'Techniker Samstag, Zugang klären.',
      assetRef: 'Heizung Gerätehaus',
      priority: 'important',
      status: 'open',
      owner: 'demo-wf',
      dueLabel: 'Samstag',
      category: 'facility',
    ),
    Defect(
      id: 132,
      title: 'Leitkegel / Warnwesten nachbestellen',
      description: 'Für Übung Verkehrsabsicherung.',
      assetRef: 'Materiallager',
      priority: 'normal',
      status: 'open',
      owner: 'demo-ausbilder',
      dueLabel: 'vor nächster Übung',
      category: 'material',
    ),
    Defect(
      id: 133,
      title: 'TS-Batterie prüfen',
      description: 'Laden und Messung dokumentieren.',
      assetRef: 'TS',
      priority: 'important',
      status: 'in_progress',
      owner: 'demo-mitglied',
      dueLabel: 'diese Woche',
      category: 'vehicle',
    ),
  ],
  calendar: [
    {
      'id': 31,
      'title': 'Übungsdienst',
      'start': _iso(_now.add(const Duration(days: 2, hours: 19))),
      'end': _iso(_now.add(const Duration(days: 2, hours: 22))),
      'all_day': false,
      'location': 'Gerätehaus',
    },
  ],
  coffee: {
    'balance': '9.40',
    'currency': 'EUR',
    'payment_hint': 'Kaffeekasse Gerätehaus.',
    'ledger': [
      {
        'id': 31,
        'amount': '-3.20',
        'description': 'Kaffee Übung',
        'created_at': _iso(_now.subtract(const Duration(days: 3))),
        'user': 'demo-kasse',
      },
    ],
  },
  checklists: [
    {
      'id': 31,
      'title': 'Gerätehaus-Wochenheck',
      'completed': false,
      'interval': 'weekly',
      'due_next': _iso(_now),
      'overdue': false,
      'items': [
        {'id': 31, 'text': 'Tore / Heizung ok', 'checked': false},
        {'id': 32, 'text': 'Notstrom Sichtprüfung', 'checked': false},
        {'id': 33, 'text': 'Fahrzeugbatterien', 'checked': true},
      ],
    },
  ],
);

final _polizei = DemoProfile(
  service: DemoService.polizei,
  stationName: 'Polizeiwache Innenstadt',
  roleLabel: 'Dienstgruppenleitung',
  username: 'demo-dgl',
  tagline: 'Dienstübergabe, Material und Organisation für die Polizei.',
  handovers: [
    {
      'id': 21,
      'title': '[Demo] Streifenwagen 3 – Reifenprofil vorne links',
      'description':
          'Profil unter Grenzmaß. Werkstatttermin heute 14:00. Bis dahin Fahrzeug nur Notbetrieb.',
      'status': 'open',
      'priority': 'urgent',
      'category': 'vehicle',
      'author': 'demo-dgl',
      'updated_at': _iso(_now.subtract(const Duration(minutes: 15))),
      'version': 1,
    },
    {
      'id': 22,
      'title': '[Demo] Bodycam-Akkus nachladen',
      'description': 'Dock 2 und 4 leer. Bitte alle Cams nach Schichtende einstellen.',
      'status': 'in_progress',
      'priority': 'important',
      'category': 'material',
      'author': 'demo-mitglied',
      'updated_at': _iso(_now.subtract(const Duration(hours: 1))),
      'version': 1,
    },
    {
      'id': 23,
      'title': '[Demo] Schlüsselbrett Zellentür – Ersatzschlüssel fehlt',
      'description': 'Haken 7 leer. Schlüsselverwaltung informiert.',
      'status': 'open',
      'priority': 'normal',
      'category': 'safety',
      'author': 'demo-admin',
      'updated_at': _iso(_now.subtract(const Duration(hours: 6))),
      'version': 2,
    },
    {
      'id': 24,
      'title': '[Demo] Dienstübergabe Nachtschicht erledigt',
      'description': 'Offene Hinweise an Tagesdienst weitergegeben.',
      'status': 'done',
      'priority': 'normal',
      'category': 'station',
      'author': 'demo-dgl',
      'updated_at': _iso(_now.subtract(const Duration(hours: 10))),
      'version': 1,
    },
  ],
  assets: const [
    StationAsset(id: 'fustw-3', label: 'FuStW 3', kind: 'vehicle', status: 'limited', note: 'Reifen vorne links'),
    StationAsset(id: 'fustw-1', label: 'FuStW 1', kind: 'vehicle', status: 'ready'),
    StationAsset(id: 'body-dock', label: 'Bodycam-Dock', kind: 'device', status: 'limited', note: 'Dock 2/4 leer'),
  ],
  inventory: const [
    InventoryItem(
      id: 'key-zelle',
      label: 'Zellenschlüssel',
      kind: 'key',
      note: 'Rückgabe überfällig',
    ),
    InventoryItem(
      id: 'bodycam-7',
      label: 'Bodycam 7',
      kind: 'device',
      holder: 'demo-mitglied',
      sinceLabel: 'heute 05:50',
    ),
    InventoryItem(id: 'bodycam-8', label: 'Bodycam 8', kind: 'device'),
  ],
  defects: const [
    Defect(
      id: 121,
      title: 'FuStW 3 Reifenprofil',
      description: 'Werkstatt 14:00, bis dahin Notbetrieb.',
      assetRef: 'FuStW 3',
      priority: 'urgent',
      status: 'open',
      owner: 'demo-dgl',
      dueLabel: 'heute 14:00',
      category: 'vehicle',
    ),
    Defect(
      id: 122,
      title: 'Zellenschlüssel Haken 7 fehlt',
      description: 'Schlüsselverwaltung informiert.',
      assetRef: 'Schlüsselbrett',
      priority: 'important',
      status: 'open',
      owner: 'demo-admin',
      dueLabel: 'heute',
      category: 'key',
    ),
    Defect(
      id: 123,
      title: 'Bodycam-Docks nachladen',
      description: 'Dock 2 und 4.',
      assetRef: 'Bodycam-Dock',
      priority: 'important',
      status: 'in_progress',
      owner: 'demo-mitglied',
      dueLabel: 'Schichtende',
      category: 'device',
    ),
  ],
  calendar: [
    {
      'id': 21,
      'title': 'Lagebesprechung',
      'description': 'Wochenlage Innenstadt',
      'start': _iso(_now.add(const Duration(hours: 2))),
      'end': _iso(_now.add(const Duration(hours: 3))),
      'all_day': false,
      'location': 'Besprechungsraum',
    },
    {
      'id': 22,
      'title': 'Fahrzeugübergabe Fuhrpark',
      'start': _iso(_now.add(const Duration(days: 1, hours: 8))),
      'end': _iso(_now.add(const Duration(days: 1, hours: 9))),
      'all_day': false,
      'location': 'Hof',
    },
  ],
  coffee: {
    'balance': '31.00',
    'currency': 'EUR',
    'payment_hint': 'Kaffeekasse Wache – Liste am Kühlschrank.',
    'ledger': [
      {
        'id': 21,
        'amount': '15.00',
        'description': 'Einsammlung Dienstgruppe',
        'created_at': _iso(_now.subtract(const Duration(days: 3))),
        'user': 'demo-kasse',
      },
      {
        'id': 22,
        'amount': '-9.20',
        'description': 'Kapseln & Milch',
        'created_at': _iso(_now.subtract(const Duration(days: 1))),
        'user': 'demo-mitglied',
      },
    ],
  },
  checklists: [
    {
      'id': 21,
      'title': 'Fahrzeugcheck FuStW 3',
      'completed': false,
      'interval': 'daily',
      'due_next': _iso(_now),
      'items': [
        {'id': 21, 'text': 'Blaulicht / Folgetonhorn', 'checked': true},
        {'id': 22, 'text': 'Bodycams geladen', 'checked': false},
        {'id': 23, 'text': 'Erste-Hilfe-Set vollständig', 'checked': true},
      ],
    },
    {
      'id': 22,
      'title': 'Wachrundgang',
      'completed': false,
      'interval': 'daily',
      'due_next': _iso(_now.subtract(const Duration(days: 1))),
      'overdue': true,
      'items': [
        {'id': 24, 'text': 'Eingänge gesichert', 'checked': false},
        {'id': 25, 'text': 'Funkraum aufgeräumt', 'checked': false},
      ],
    },
  ],
);
