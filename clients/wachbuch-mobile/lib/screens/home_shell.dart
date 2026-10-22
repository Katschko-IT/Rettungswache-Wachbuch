import 'package:flutter/material.dart';
import 'package:wachbuch_mobile/api/client.dart';
import 'package:wachbuch_mobile/demo/demo_api.dart';
import 'package:wachbuch_mobile/demo/demo_profiles.dart';
import 'package:wachbuch_mobile/l10n/generated/app_localizations.dart';
import 'package:wachbuch_mobile/models/handover_ack.dart';
import 'package:wachbuch_mobile/models/station_asset.dart';
import 'package:wachbuch_mobile/screens/assets_screen.dart';
import 'package:wachbuch_mobile/screens/chat_screen.dart';
import 'package:wachbuch_mobile/screens/checklisten_screen.dart';
import 'package:wachbuch_mobile/screens/defects_screen.dart';
import 'package:wachbuch_mobile/screens/groups_screen.dart';
import 'package:wachbuch_mobile/screens/kaffeekasse_screen.dart';
import 'package:wachbuch_mobile/screens/kalender_screen.dart';
import 'package:wachbuch_mobile/screens/pinnwand_screen.dart';
import 'package:wachbuch_mobile/screens/reports_screen.dart';
import 'package:wachbuch_mobile/services/connectivity_service.dart';
import 'package:wachbuch_mobile/state/auth_state.dart';
import 'package:wachbuch_mobile/state/handover_state.dart';
import 'package:wachbuch_mobile/ui/asset_status_board.dart';
import 'package:wachbuch_mobile/ui/demo_banner.dart';
import 'package:wachbuch_mobile/ui/error_banner.dart';
import 'package:wachbuch_mobile/ui/handover_filter.dart';
import 'package:wachbuch_mobile/ui/layout.dart';
import 'package:wachbuch_mobile/ui/offline_banner.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    required this.api,
    required this.onLogout,
    required this.onChangeServer,
  });

  final WachbuchApi api;
  final Future<void> Function() onLogout;
  final Future<void> Function() onChangeServer;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;
  int _reloadGeneration = 0;
  late final HandoverState _handoverState;
  late final AuthState _authState;
  late final ConnectivityService _connectivity;
  late final Listenable _listenable;
  bool _wasOffline = false;

  @override
  void initState() {
    super.initState();
    _handoverState = HandoverState(api: widget.api);
    _authState = AuthState(api: widget.api);
    _connectivity = ConnectivityService();
    _listenable = Listenable.merge([_handoverState, _authState, _connectivity]);
    _connectivity.start();
    _connectivity.addListener(_onConnectivityChanged);
    _reload();
  }

  void _onConnectivityChanged() {
    if (_connectivity.isOnline && _wasOffline && mounted) {
      _wasOffline = false;
      _reload();
    } else if (_connectivity.isOffline) {
      _wasOffline = true;
    }
  }

  Future<void> _reload() async {
    final generation = ++_reloadGeneration;
    await Future.wait([
      _authState.reload(),
      _handoverState.reload(),
    ]);
    if (!mounted || generation != _reloadGeneration) {
      return;
    }
    final isUnauthorized =
        _authState.lastError?.statusCode == 401 ||
        _handoverState.lastError?.statusCode == 401;
    if (isUnauthorized) {
      await widget.onLogout();
    }
  }

  bool get _loading => _authState.loading || _handoverState.loading;

  bool get _offline =>
      !_connectivity.isOnline ||
      _authState.lastError?.statusCode == 0 ||
      _handoverState.lastError?.statusCode == 0;

  bool get _isDemo =>
      widget.api is DemoWachbuchApi || DemoService.isDemoUrl(widget.api.baseUrl);

  String? _demoServiceLabel(AppLocalizations l10n) {
    final service = widget.api is DemoWachbuchApi
        ? (widget.api as DemoWachbuchApi).profile.service
        : DemoService.fromServerUrl(widget.api.baseUrl);
    return switch (service) {
      DemoService.rettungsdienst => l10n.demoBannerRettungsdienst,
      DemoService.feuerwehr => l10n.demoBannerFeuerwehr,
      DemoService.ffw => l10n.demoBannerFfw,
      DemoService.polizei => l10n.demoBannerPolizei,
      null => null,
    };
  }

  String? _displayError(AppLocalizations l10n) {
    for (final error in [_authState.lastError, _handoverState.lastError]) {
      if (error == null) continue;
      if (error.statusCode == 401) return l10n.sessionExpiredError;
      return error.message;
    }
    return _authState.error ?? _handoverState.error;
  }

  @override
  void dispose() {
    _connectivity.removeListener(_onConnectivityChanged);
    _connectivity.dispose();
    _handoverState.dispose();
    _authState.dispose();
    widget.api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    final tablet = AppLayout.isTablet(width);

    return ListenableBuilder(
      listenable: _listenable,
      builder: (context, _) {
        final stationName = _authState.stationName(l.stationFallback);
        final error = _displayError(l);
        final loading = _loading;
        final offline = _offline;

        final pages = IndexedStack(
          index: _tab,
          children: [
            _OverviewTab(
              api: widget.api,
              stationName: stationName,
              roleLabel: _authState.roleLabel,
              modules: _authState.modules,
              handovers: _handoverState.items,
              loading: loading,
              hasData: _authState.hasData,
              error: error,
              onRefresh: _reload,
            ),
            _HandoversTab(
              api: widget.api,
              handoverState: _handoverState,
              currentUsername: _authState.username,
              error: error,
              onRefresh: _reload,
            ),
            _AccountTab(
              me: _authState.me,
              serverUrl: widget.api.baseUrl,
              loading: loading,
              onLogout: widget.onLogout,
              onChangeServer: widget.onChangeServer,
              onRefresh: _reload,
            ),
          ],
        );

        final appBar = AppBar(
          title: Text(
            stationName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          actions: [
            IconButton(
              tooltip: l.refreshTooltip,
              onPressed: loading ? null : _reload,
              icon: const Icon(Icons.refresh),
            ),
          ],
        );

        final offlineBanner = OfflineBanner(
          visible: offline && !_isDemo,
          onRetry: loading ? () {} : _reload,
        );
        final demoBanner = DemoBanner(
          visible: _isDemo,
          label: l.demoBannerLabel,
          serviceLabel: _demoServiceLabel(l),
        );

        if (tablet) {
          return Scaffold(
            appBar: appBar,
            body: Column(
              children: [
                demoBanner,
                offlineBanner,
                Expanded(
                  child: Row(
                    children: [
                      NavigationRail(
                        selectedIndex: _tab,
                        onDestinationSelected: (index) =>
                            setState(() => _tab = index),
                        labelType: width >= AppLayout.wideBreakpoint
                            ? NavigationRailLabelType.all
                            : NavigationRailLabelType.selected,
                        destinations: [
                          NavigationRailDestination(
                            icon: const Icon(Icons.home_outlined),
                            selectedIcon: const Icon(Icons.home),
                            label: Text(l.navOverview),
                          ),
                          NavigationRailDestination(
                            icon: const Icon(Icons.assignment_outlined),
                            selectedIcon: const Icon(Icons.assignment),
                            label: Text(l.navHandovers),
                          ),
                          NavigationRailDestination(
                            icon: const Icon(Icons.person_outline),
                            selectedIcon: const Icon(Icons.person),
                            label: Text(l.navAccount),
                          ),
                        ],
                      ),
                      const VerticalDivider(width: 1),
                      Expanded(child: pages),
                    ],
                  ),
                ),
              ],
            ),
          );
        }

        return Scaffold(
          appBar: appBar,
          body: Column(
            children: [demoBanner, offlineBanner, Expanded(child: pages)],
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _tab,
            onDestinationSelected: (index) => setState(() => _tab = index),
            destinations: [
              NavigationDestination(
                icon: const Icon(Icons.home_outlined),
                label: l.navOverview,
              ),
              NavigationDestination(
                icon: const Icon(Icons.assignment_outlined),
                label: l.navHandovers,
              ),
              NavigationDestination(
                icon: const Icon(Icons.person_outline),
                label: l.navAccount,
              ),
            ],
          ),
        );
      },
    );
  }
}

class _OverviewTab extends StatelessWidget {
  const _OverviewTab({
    required this.api,
    required this.stationName,
    required this.roleLabel,
    required this.modules,
    required this.handovers,
    required this.loading,
    required this.hasData,
    required this.error,
    required this.onRefresh,
  });

  final WachbuchApi api;
  final String stationName;
  final String roleLabel;
  final Map<String, dynamic> modules;
  final List<Map<String, dynamic>> handovers;
  final bool loading;
  final bool hasData;
  final String? error;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    if (loading && !hasData) {
      return const Center(child: CircularProgressIndicator());
    }
    final l = AppLocalizations.of(context)!;
    final languageCode = Localizations.localeOf(context).languageCode;
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);
    final openCount = handovers
        .where((item) => item['status'] == 'open')
        .length;
    final inProgressCount = handovers
        .where((item) => item['status'] == 'in_progress')
        .length;
    final urgentCount = handovers
        .where((item) => item['priority'] == 'urgent')
        .length;

    return RefreshIndicator(
      onRefresh: onRefresh,
      child: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxW),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _StationHero(stationName: stationName, roleLabel: roleLabel),
              const SizedBox(height: 16),
              if (error != null) ...[
                ErrorBanner(message: error!),
                const SizedBox(height: 16),
              ],
              _SectionTitle(
                icon: Icons.monitor_heart_outlined,
                title: l.overviewActiveHandovers,
              ),
              const SizedBox(height: 12),
              LayoutBuilder(
                builder: (context, constraints) {
                  final textScale =
                      MediaQuery.textScalerOf(context).scale(14) / 14;
                  final columns = constraints.maxWidth < 360 || textScale > 1.3
                      ? 2
                      : 3;
                  final metricWidth =
                      (constraints.maxWidth - (8 * (columns - 1))) / columns;
                  return Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _DashboardMetric(
                        key: const Key('overview-stat-open'),
                        width: metricWidth,
                        icon: Icons.inbox_outlined,
                        value: openCount,
                        label: l.metricOpen,
                      ),
                      _DashboardMetric(
                        key: const Key('overview-stat-progress'),
                        width: metricWidth,
                        icon: Icons.pending_actions_outlined,
                        value: inProgressCount,
                        label: l.metricInProgress,
                      ),
                      _DashboardMetric(
                        key: const Key('overview-stat-urgent'),
                        width: metricWidth,
                        icon: Icons.priority_high_rounded,
                        value: urgentCount,
                        label: l.metricUrgent,
                        urgent: urgentCount > 0,
                      ),
                    ],
                  );
                },
              ),
              if (modules['assets'] == true) ...[
                const SizedBox(height: 24),
                _OverviewAssetBoard(api: api),
              ],
              const SizedBox(height: 24),
              _SectionTitle(
                icon: Icons.dashboard_customize_outlined,
                title: l.overviewModulesTitle,
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                // Nur echte Modulschalter; Zusatzangaben wie `holiday_state`
                // (Bundesland) sind keine An/Aus-Werte.
                children: modules.entries
                    .where((entry) => entry.value is bool)
                    .map((entry) {
                  final on = entry.value == true;
                  return Chip(
                    avatar: Icon(
                      on ? Icons.check_circle : Icons.remove_circle_outline,
                      size: 18,
                    ),
                    label: Text(
                      moduleLabel(entry.key, languageCode: languageCode),
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 24),
              _ModuleTiles(api: api, modules: modules),
              const SizedBox(height: 24),
              Material(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.info_outline,
                        color: Theme.of(context).colorScheme.onPrimaryContainer,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          l.overviewModulesHint,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(
                                color: Theme.of(
                                  context,
                                ).colorScheme.onPrimaryContainer,
                              ),
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

class _StationHero extends StatelessWidget {
  const _StationHero({required this.stationName, required this.roleLabel});

  final String stationName;
  final String roleLabel;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.primary,
      borderRadius: BorderRadius.circular(18),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: scheme.onPrimary.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(
                Icons.local_hospital_outlined,
                color: scheme.onPrimary,
                size: 30,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    stationName,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(
                      context,
                    ).textTheme.titleLarge?.copyWith(color: scheme.onPrimary),
                  ),
                  if (roleLabel.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      roleLabel,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: scheme.onPrimary.withValues(alpha: 0.88),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(icon, size: 24, color: scheme.primary),
        const SizedBox(width: 8),
        Expanded(
          child: Text(title, style: Theme.of(context).textTheme.titleMedium),
        ),
      ],
    );
  }
}

class _DashboardMetric extends StatelessWidget {
  const _DashboardMetric({
    super.key,
    required this.width,
    required this.icon,
    required this.value,
    required this.label,
    this.urgent = false,
  });

  final double width;
  final IconData icon;
  final int value;
  final String label;
  final bool urgent;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final background = urgent ? scheme.errorContainer : scheme.surface;
    final foreground = urgent ? scheme.onErrorContainer : scheme.onSurface;
    final accent = urgent ? scheme.error : scheme.primary;
    return SizedBox(
      width: width,
      child: Card(
        color: background,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 24, color: accent),
              const SizedBox(height: 10),
              Text(
                '$value $label',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: foreground,
                  height: 1.25,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModuleTiles extends StatelessWidget {
  const _ModuleTiles({required this.api, required this.modules});

  final WachbuchApi api;
  final Map<String, dynamic> modules;

  /// Module key -> list of tiles to render when the module is enabled.
  /// `chat` renders two tiles (chat + groups); `assets` also matches `inventory`.
  static const _moduleTiles = <_ModuleTileSpec>[
    _ModuleTileSpec(['calendar'], 'module-tile-calendar', Icons.event_outlined),
    _ModuleTileSpec(['coffee'], 'module-tile-coffee', Icons.coffee_outlined),
    _ModuleTileSpec(['checklists'], 'module-tile-checklists', Icons.checklist_outlined),
    _ModuleTileSpec(['defects'], 'module-tile-defects', Icons.report_problem_outlined),
    _ModuleTileSpec(['assets', 'inventory'], 'module-tile-assets', Icons.directions_car_outlined),
    _ModuleTileSpec(['reports'], 'module-tile-reports', Icons.insights_outlined),
    _ModuleTileSpec(['chat'], 'module-tile-chat', Icons.forum_outlined),
    _ModuleTileSpec(['chat'], 'module-tile-groups', Icons.groups_outlined),
    _ModuleTileSpec(['pinboard'], 'module-tile-pinboard', Icons.push_pin_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final destinations = [
      for (final spec in _moduleTiles)
        if (spec.keys.any((key) => modules[key] == true))
          _ModuleDestination(
            key: spec.tileKey,
            icon: spec.icon,
            title: _tileTitle(spec.tileKey, l),
            subtitle: _tileSubtitle(spec.tileKey, l),
          ),
    ];
    if (destinations.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionTitle(
          icon: Icons.apps_outlined,
          title: l.quickAccessTitle,
        ),
        const SizedBox(height: 12),
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 600 ? 3 : 2;
            final tileWidth =
                (constraints.maxWidth - (8 * (columns - 1))) / columns;
            return Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final destination in destinations)
                  _ModuleTile(
                    key: Key(destination.key),
                    width: tileWidth,
                    destination: destination,
                    onTap: () => _open(context, destination),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }

  static String _tileTitle(String key, AppLocalizations l) {
    return switch (key) {
      'module-tile-calendar' => l.moduleCalendarTitle,
      'module-tile-coffee' => l.moduleCoffeeTitle,
      'module-tile-checklists' => l.moduleChecklistsTitle,
      'module-tile-defects' => l.moduleDefectsTitle,
      'module-tile-assets' => l.moduleAssetsTitle,
      'module-tile-reports' => l.moduleReportsTitle,
      'module-tile-chat' => l.chatTitle,
      'module-tile-groups' => l.groupsTitle,
      'module-tile-pinboard' => l.pinboardTitle,
      _ => key,
    };
  }

  static String _tileSubtitle(String key, AppLocalizations l) {
    return switch (key) {
      'module-tile-calendar' => l.moduleCalendarSubtitle,
      'module-tile-coffee' => l.moduleCoffeeSubtitle,
      'module-tile-checklists' => l.moduleChecklistsSubtitle,
      'module-tile-defects' => l.moduleDefectsSubtitle,
      'module-tile-assets' => l.moduleAssetsSubtitle,
      'module-tile-reports' => l.moduleReportsSubtitle,
      'module-tile-chat' => l.chatSubtitle,
      'module-tile-groups' => l.groupsSubtitle,
      'module-tile-pinboard' => l.pinboardSubtitle,
      _ => '',
    };
  }

  void _open(BuildContext context, _ModuleDestination destination) {
    final Widget screen;
    switch (destination.key) {
      case 'module-tile-calendar':
        screen = KalenderScreen(api: api);
      case 'module-tile-coffee':
        screen = KaffeekasseScreen(api: api);
      case 'module-tile-checklists':
        screen = ChecklistenScreen(api: api);
      case 'module-tile-defects':
        screen = DefectsScreen(api: api);
      case 'module-tile-assets':
        screen = AssetsScreen(api: api);
      case 'module-tile-reports':
        screen = ReportsScreen(api: api);
      case 'module-tile-chat':
        screen = ChatScreen(api: api);
      case 'module-tile-groups':
        screen = GroupsScreen(api: api);
      case 'module-tile-pinboard':
        screen = PinnwandScreen(api: api);
      default:
        return;
    }
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
  }
}

/// Loads station assets for the overview board; hides on 501 / empty.
class _OverviewAssetBoard extends StatefulWidget {
  const _OverviewAssetBoard({required this.api});

  final WachbuchApi api;

  @override
  State<_OverviewAssetBoard> createState() => _OverviewAssetBoardState();
}

class _OverviewAssetBoardState extends State<_OverviewAssetBoard> {
  List<StationAsset> _assets = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant _OverviewAssetBoard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.api != widget.api) {
      _load();
    }
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    List<StationAsset> assets = const [];
    try {
      assets = await widget.api.assets();
    } catch (_) {
      // Module optional: hide on any error instead of breaking the overview.
    }
    if (!mounted) return;
    setState(() {
      _assets = assets;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _assets.isEmpty) {
      return const SizedBox(
        height: 48,
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      );
    }
    return AssetStatusBoard(assets: _assets);
  }
}

class _ModuleTileSpec {
  const _ModuleTileSpec(this.keys, this.tileKey, this.icon);

  final List<String> keys;
  final String tileKey;
  final IconData icon;
}

class _ModuleDestination {
  const _ModuleDestination({
    required this.key,
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final String key;
  final IconData icon;
  final String title;
  final String subtitle;
}

class _ModuleTile extends StatelessWidget {
  const _ModuleTile({
    super.key,
    required this.width,
    required this.destination,
    required this.onTap,
  });

  final double width;
  final _ModuleDestination destination;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      width: width,
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(destination.icon, size: 28, color: scheme.primary),
                const SizedBox(height: 10),
                Text(
                  destination.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const SizedBox(height: 2),
                Text(
                  destination.subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _HandoversTab extends StatefulWidget {
  const _HandoversTab({
    required this.api,
    required this.handoverState,
    required this.currentUsername,
    required this.error,
    required this.onRefresh,
  });

  final WachbuchApi api;
  final HandoverState handoverState;
  final String? currentUsername;
  final String? error;
  final Future<void> Function() onRefresh;

  @override
  State<_HandoversTab> createState() => _HandoversTabState();
}

class _HandoversTabState extends State<_HandoversTab> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _showDetails(Map<String, dynamic> item) async {
    final rawId = item['id'];
    final id = rawId is int ? rawId : int.tryParse(rawId?.toString() ?? '');
    if (id == null) {
      return;
    }
    final detailFuture = widget.api.handoverDetail(id);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => _HandoverDetailSheet(
        api: widget.api,
        handoverId: id,
        currentUsername: widget.currentUsername,
        future: detailFuture,
        fallback: item,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.handoverState;
    final items = state.items;
    if (state.loading && items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    final l = AppLocalizations.of(context)!;
    final width = MediaQuery.sizeOf(context).width;
    final cols = AppLayout.handoverColumns(width);
    final maxW = AppLayout.contentMaxWidth(width);
    final filtered = state.filteredItems;
    final availableStatuses = _orderedValues(
      [
        ...items.map((item) => item['status']?.toString() ?? ''),
        ...state.statuses,
      ],
      const ['open', 'in_progress', 'done'],
    );
    final availablePriorities = _orderedValues(
      [
        ...items.map((item) => item['priority']?.toString() ?? ''),
        ...state.priorities,
      ],
      const ['urgent', 'important', 'normal'],
    );

    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxW),
        child: Column(
          children: [
            if (items.isNotEmpty) ...[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                child: SearchBar(
                  key: const Key('handover-search'),
                  controller: _searchController,
                  hintText: l.handoverSearchHint,
                  leading: const Icon(Icons.search),
                  trailing: [
                    if (_searchController.text.isNotEmpty)
                      IconButton(
                        tooltip: l.handoverSearchClear,
                        onPressed: () {
                          _searchController.clear();
                          state.setSearchQuery('');
                        },
                        icon: const Icon(Icons.close),
                      ),
                  ],
                  onChanged: (text) => state.setSearchQuery(text),
                ),
              ),
              _FilterSection(
                title: l.filterStatus,
                values: availableStatuses,
                selected: state.statuses,
                label: (value) => handoverStatusLabel(value, l),
                keyPrefix: 'status-filter',
                onChanged: (value, selected) =>
                    state.toggleStatus(value, selected: selected),
              ),
              _FilterSection(
                title: l.filterPriority,
                values: availablePriorities,
                selected: state.priorities,
                label: (value) => handoverPriorityLabel(value, l),
                keyPrefix: 'priority-filter',
                onChanged: (value, selected) =>
                    state.togglePriority(value, selected: selected),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 6),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    l.handoversCount(filtered.length, items.length),
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ),
              ),
            ],
            Expanded(
              child: RefreshIndicator(
                onRefresh: widget.onRefresh,
                child: _HandoverResults(
                  items: filtered,
                  allItemsEmpty: items.isEmpty,
                  error: widget.error,
                  columns: cols,
                  onOpen: _showDetails,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterSection extends StatelessWidget {
  const _FilterSection({
    required this.title,
    required this.values,
    required this.selected,
    required this.label,
    required this.keyPrefix,
    required this.onChanged,
  });

  final String title;
  final List<String> values;
  final Set<String> selected;
  final String Function(Object?) label;
  final String keyPrefix;
  final void Function(String value, bool selected) onChanged;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    if (values.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 0, 2),
      child: Semantics(
        container: true,
        label: l.filterSectionLabel(title),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 6),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.only(right: 16),
              child: Row(
                children: [
                  for (final value in values)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        key: Key('$keyPrefix-$value'),
                        label: Text(label(value)),
                        selected: selected.contains(value),
                        showCheckmark: true,
                        onSelected: (active) => onChanged(value, active),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HandoverResults extends StatelessWidget {
  const _HandoverResults({
    required this.items,
    required this.allItemsEmpty,
    required this.error,
    required this.columns,
    required this.onOpen,
  });

  final List<Map<String, dynamic>> items;
  final bool allItemsEmpty;
  final String? error;
  final int columns;
  final void Function(Map<String, dynamic> item) onOpen;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    if (error != null && allItemsEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [ErrorBanner(message: error!)],
      );
    }
    if (allItemsEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [Text(l.handoversNoneActive)],
      );
    }
    if (items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [Text(l.handoversNoneForFilter)],
      );
    }
    if (columns == 1) {
      return ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 16),
        itemCount: items.length,
        separatorBuilder: (_, _) => const SizedBox(height: 4),
        itemBuilder: (context, index) =>
            _HandoverCard(item: items[index], onOpen: onOpen),
      );
    }
    return GridView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 16),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        mainAxisExtent: _handoverCardExtent(context),
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) =>
          _HandoverCard(item: items[index], onOpen: onOpen),
    );
  }
}

class _HandoverCard extends StatelessWidget {
  const _HandoverCard({required this.item, required this.onOpen});

  final Map<String, dynamic> item;
  final void Function(Map<String, dynamic> item) onOpen;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final title = item['title']?.toString().trim();
    return Semantics(
      button: true,
      label: l.handoverOpenSemantics(
        title?.isNotEmpty == true ? title! : l.handoverUntitled,
      ),
      child: SizedBox(
        height: _handoverCardExtent(context),
        child: Card(
          margin: const EdgeInsets.all(4),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: () => onOpen(item),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  width: 5,
                  color: _priorityColors(context, item['priority']).foreground,
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title?.isNotEmpty == true ? title! : l.handoverFallback,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 6),
                        Text(
                          handoverCategoryLabel(item['category'], l),
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(
                                color: Theme.of(
                                  context,
                                ).colorScheme.onSurfaceVariant,
                              ),
                        ),
                        const Spacer(),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            _HandoverChip(
                              label: handoverStatusLabel(item['status'], l),
                              colors: _statusColors(context, item['status']),
                            ),
                            _HandoverChip(
                              label: handoverPriorityLabel(item['priority'], l),
                              colors: _priorityColors(
                                context,
                                item['priority'],
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _HandoverChip extends StatelessWidget {
  const _HandoverChip({required this.label, required this.colors});

  final String label;
  final ({Color background, Color foreground}) colors;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: colors.background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: colors.foreground,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _HandoverDetailSheet extends StatefulWidget {
  const _HandoverDetailSheet({
    required this.api,
    required this.handoverId,
    required this.currentUsername,
    required this.future,
    required this.fallback,
  });

  final WachbuchApi api;
  final int handoverId;
  final String? currentUsername;
  final Future<Map<String, dynamic>> future;
  final Map<String, dynamic> fallback;

  @override
  State<_HandoverDetailSheet> createState() => _HandoverDetailSheetState();
}

class _HandoverDetailSheetState extends State<_HandoverDetailSheet> {
  List<HandoverAck> _acks = const [];
  bool _acksSupported = true;
  bool _acking = false;
  bool _creatingDefect = false;
  String? _ackError;

  @override
  void initState() {
    super.initState();
    _loadAcks();
  }

  Future<void> _loadAcks() async {
    try {
      final acks = await widget.api.handoverAcks(widget.handoverId);
      if (!mounted) return;
      setState(() {
        _acks = acks;
        _acksSupported = true;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (WachbuchApi.isModuleUnavailable(error)) {
        setState(() => _acksSupported = false);
        return;
      }
      setState(() => _ackError = error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _acksSupported = false);
    }
  }

  Future<void> _acknowledge(AppLocalizations l) async {
    setState(() {
      _acking = true;
      _ackError = null;
    });
    try {
      final ack = await widget.api.acknowledgeHandover(widget.handoverId);
      if (!mounted) return;
      setState(() {
        _acks = [
          ..._acks.where((item) => item.by != ack.by),
          ack,
        ];
        _acking = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _acking = false;
        _ackError = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _acking = false;
        _ackError = l.handoverAckFailed;
      });
    }
  }

  Future<void> _createDefectFromHandover(
    AppLocalizations l,
    Map<String, dynamic> item,
  ) async {
    if (_creatingDefect) return;
    setState(() => _creatingDefect = true);
    final rawTitle = item['title']?.toString().trim() ?? '';
    final title = rawTitle.isNotEmpty ? rawTitle : l.handoverFallback;
    final details = item['details']?.toString().trim() ?? '';
    try {
      await widget.api.createDefect(
        title: title,
        description: details,
        priority: _mapHandoverPriority(item['priority']),
        category: 'task',
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${l.moduleDefectsTitle}: $title')),
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.defectCreateFailed)),
      );
    } finally {
      if (mounted) setState(() => _creatingDefect = false);
    }
  }

  String _mapHandoverPriority(Object? value) {
    final raw = value?.toString().trim().toLowerCase() ?? '';
    return switch (raw) {
      'urgent' || 'high' => 'urgent',
      'important' || 'medium' => 'important',
      _ => 'normal',
    };
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    return SafeArea(
      child: FutureBuilder<Map<String, dynamic>>(
        future: widget.future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const SizedBox(
              height: 240,
              child: Center(child: CircularProgressIndicator()),
            );
          }
          if (snapshot.hasError) {
            final message = snapshot.error is ApiException
                ? (snapshot.error! as ApiException).message
                : l.detailsLoadFailed;
            return Padding(
              padding: const EdgeInsets.all(24),
              child: ErrorBanner(message: message),
            );
          }
          final item = {...widget.fallback, ...?snapshot.data};
          final rawAuthor = item['author'];
          final author = rawAuthor is Map ? rawAuthor : null;
          final authorName = author?['display_name']?.toString();
          final details = item['details']?.toString().trim();
          final version = item['version'];
          final me = widget.currentUsername ??
              (widget.api is DemoWachbuchApi
                  ? (widget.api as DemoWachbuchApi).profile.username
                  : null);
          final alreadyAcked =
              me != null && _acks.any((ack) => ack.by == me);
          return SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(
              24,
              0,
              24,
              24 + MediaQuery.viewInsetsOf(context).bottom,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item['title']?.toString() ?? l.handoverFallback,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _HandoverChip(
                      label: handoverCategoryLabel(item['category'], l),
                      colors: (
                        background: Theme.of(
                          context,
                        ).colorScheme.surfaceContainerHighest,
                        foreground: Theme.of(context).colorScheme.onSurface,
                      ),
                    ),
                    _HandoverChip(
                      label: handoverStatusLabel(item['status'], l),
                      colors: _statusColors(context, item['status']),
                    ),
                    _HandoverChip(
                      label: handoverPriorityLabel(item['priority'], l),
                      colors: _priorityColors(context, item['priority']),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                Text(
                  details?.isNotEmpty == true
                      ? details!
                      : l.detailsNoFurtherInfo,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: 20),
                if (authorName?.isNotEmpty == true)
                  _DetailRow(icon: Icons.person_outline, value: authorName!),
                if (item['updated_at'] != null)
                  _DetailRow(
                    icon: Icons.update,
                    value: l.detailsUpdatedAt(
                      _formatTimestamp(item['updated_at']),
                    ),
                  ),
                if (version != null)
                  _DetailRow(
                    icon: Icons.history,
                    value: l.detailsVersion(version.toString()),
                  ),
                if (_acksSupported) ...[
                  const SizedBox(height: 16),
                  Text(
                    l.handoverAckListTitle,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  if (_acks.isEmpty)
                    Text(
                      l.handoverAckEmpty,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Theme.of(context)
                                .colorScheme
                                .onSurfaceVariant,
                          ),
                    )
                  else
                    ..._acks.map(
                      (ack) => _DetailRow(
                        icon: Icons.verified_outlined,
                        value:
                            '${ack.by} · ${_formatTimestamp(ack.at.toIso8601String())}',
                      ),
                    ),
                  if (_ackError != null) ...[
                    const SizedBox(height: 8),
                    ErrorBanner(message: _ackError!),
                  ],
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _acking || alreadyAcked
                        ? null
                        : () => _acknowledge(l),
                    icon: _acking
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.done_all),
                    label: Text(
                      alreadyAcked ? l.handoverAckDone : l.handoverAckButton,
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  key: const Key('handover-to-defect'),
                  onPressed: _creatingDefect
                      ? null
                      : () => _createDefectFromHandover(l, item),
                  icon: _creatingDefect
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.report_problem_outlined),
                  label: Text(l.defectAdd),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.icon, required this.value});

  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(icon, size: 24, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 8),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

List<String> _orderedValues(Iterable<String> values, List<String> order) {
  final available = values.where((value) => value.isNotEmpty).toSet();
  final result = order.where(available.remove).toList();
  final unknown = available.toList()..sort();
  return [...result, ...unknown];
}

double _handoverCardExtent(BuildContext context) {
  final scale = MediaQuery.textScalerOf(context).scale(1);
  final extraScale = (scale - 1).clamp(0.0, 2.0);
  return 196 + (190 * extraScale);
}

({Color background, Color foreground}) _statusColors(
  BuildContext context,
  Object? status,
) {
  final colors = Theme.of(context).colorScheme;
  return switch (status?.toString()) {
    'open' => (
      background: colors.primaryContainer,
      foreground: colors.onPrimaryContainer,
    ),
    'in_progress' => (
      background: colors.secondaryContainer,
      foreground: colors.onSecondaryContainer,
    ),
    'done' => (
      background: colors.surfaceContainerHighest,
      foreground: colors.onSurface,
    ),
    _ => (
      background: colors.surfaceContainerHigh,
      foreground: colors.onSurface,
    ),
  };
}

({Color background, Color foreground}) _priorityColors(
  BuildContext context,
  Object? priority,
) {
  final colors = Theme.of(context).colorScheme;
  return switch (priority?.toString()) {
    'urgent' => (
      background: colors.errorContainer,
      foreground: colors.onErrorContainer,
    ),
    'important' => (
      background: colors.tertiaryContainer,
      foreground: colors.onTertiaryContainer,
    ),
    _ => (
      background: colors.surfaceContainerHighest,
      foreground: colors.onSurface,
    ),
  };
}

String _formatTimestamp(Object? value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  if (parsed == null) {
    return value?.toString() ?? '—';
  }
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(parsed.day)}.${two(parsed.month)}.${parsed.year}, '
      '${two(parsed.hour)}:${two(parsed.minute)} Uhr';
}

class _AccountTab extends StatelessWidget {
  const _AccountTab({
    required this.me,
    required this.serverUrl,
    required this.loading,
    required this.onLogout,
    required this.onChangeServer,
    required this.onRefresh,
  });

  final Map<String, dynamic>? me;
  final String serverUrl;
  final bool loading;
  final Future<void> Function() onLogout;
  final Future<void> Function() onChangeServer;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final user = me?['user'] as Map?;
    final width = MediaQuery.sizeOf(context).width;
    final maxW = AppLayout.contentMaxWidth(width);

    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxW),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.accountLoggedInAs),
              subtitle: Text((user?['username'] as String?) ?? '—'),
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.accountServer),
              subtitle: Text(serverUrl),
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.accountLicense),
              subtitle: Text(l.accountLicenseValue),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: loading ? null : onRefresh,
              child: Text(l.accountRefreshProfile),
            ),
            const SizedBox(height: 8),
            FilledButton.tonal(
              onPressed: loading ? null : onLogout,
              child: Text(l.accountLogout),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: loading ? null : onChangeServer,
              child: Text(l.accountChangeServer),
            ),
          ],
        ),
      ),
    );
  }
}
