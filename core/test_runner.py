"""Test-Runner, der ausgehende Netzwerkverbindungen blockiert.

Tests dürfen nie echte externe Dienste (Wetter, Geocoding, Feeds, Push)
erreichen: Ergebnisse wären nicht reproduzierbar und würden bei WAN-Ausfall
oder in isolierten CI-Runnern zufällig fehlschlagen. Loopback bleibt erlaubt,
damit z. B. ein lokaler Redis/PostgreSQL-Testdienst nutzbar ist.
"""
from __future__ import annotations

import ipaddress
import socket

from django.test.runner import DiscoverRunner


class ExternalNetworkBlocked(OSError):
    """Ein Test hat versucht, einen externen Host zu kontaktieren."""


def _is_loopback(address) -> bool:
    if isinstance(address, tuple) and address:
        host = address[0]
    elif isinstance(address, (str, bytes)):
        # AF_UNIX-Sockets sind lokal.
        return True
    else:
        return False
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo


def _guarded_connect(self, address):
    if self.family != getattr(socket, "AF_UNIX", None) and not _is_loopback(address):
        raise ExternalNetworkBlocked(f"Externe Verbindung in Tests blockiert: {address!r}")
    return _original_connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family != getattr(socket, "AF_UNIX", None) and not _is_loopback(address):
        raise ExternalNetworkBlocked(f"Externe Verbindung in Tests blockiert: {address!r}")
    return _original_connect_ex(self, address)


def _is_ip_literal(host) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _guarded_getaddrinfo(host, *args, **kwargs):
    name = host.decode() if isinstance(host, bytes) else host
    # IP-Literale werden ohne DNS aufgelöst und bleiben daher erlaubt.
    if name is not None and not _is_ip_literal(name) and not _is_loopback((name,)):
        raise socket.gaierror(socket.EAI_NONAME, f"DNS in Tests blockiert: {host!r}")
    return _original_getaddrinfo(host, *args, **kwargs)


def block_external_network() -> None:
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.getaddrinfo = _guarded_getaddrinfo


def restore_network() -> None:
    socket.socket.connect = _original_connect
    socket.socket.connect_ex = _original_connect_ex
    socket.getaddrinfo = _original_getaddrinfo


class HermeticDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        block_external_network()
        super().setup_test_environment(**kwargs)

    def teardown_test_environment(self, **kwargs):
        super().teardown_test_environment(**kwargs)
        restore_network()
