import 'package:app_links/app_links.dart';

abstract interface class ServerLinkSource {
  Future<Uri?> getInitialLink();

  Stream<Uri> get uriLinkStream;
}

class AppLinksServerLinkSource implements ServerLinkSource {
  AppLinksServerLinkSource({AppLinks? appLinks})
    : _appLinks = appLinks ?? AppLinks();

  final AppLinks _appLinks;

  @override
  Future<Uri?> getInitialLink() => _appLinks.getInitialLink();

  @override
  Stream<Uri> get uriLinkStream => _appLinks.uriLinkStream;
}

class NoopServerLinkSource implements ServerLinkSource {
  const NoopServerLinkSource();

  @override
  Future<Uri?> getInitialLink() async => null;

  @override
  Stream<Uri> get uriLinkStream => const Stream.empty();
}
