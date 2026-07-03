"""Module reseau pour la gestion des peripheriques.

Ce module fournit les outils pour scanner, inventorier et
gerer les peripheriques d'un reseau local.
"""

from linuxtools.network.base import (
    DeviceReporter,
    DeviceRepository,
    DhcpReservationManager,
    DnsManager,
    NetworkScanner,
    RouterDhcpManager,
)
from linuxtools.network.config import (
    DhcpRange,
    DnsConfig,
    NetworkConfig,
)
from linuxtools.network.dhcp import (
    LinuxDhcpReservationManager,
)
from linuxtools.network.dns import (
    LinuxDnsmasqConfigGenerator,
    LinuxHostsFileManager,
)
from linuxtools.network.models import (
    NetworkDevice,
)
from linuxtools.network.reporter import (
    ConsoleTableReporter,
    CsvReporter,
    DiffReporter,
    JsonReporter,
)
from linuxtools.network.repository import (
    JsonDeviceRepository,
)
from linuxtools.network.router import (
    AsusRouterClient,
    AsusRouterDhcpManager,
    AsusRouterScanner,
    RouterAuthError,
    RouterConfig,
)
from linuxtools.network.scanner import (
    LinuxArpScanner,
    LinuxNmapScanner,
)
from linuxtools.network.validators import (
    validate_cidr,
    validate_hostname,
    validate_ipv4,
    validate_mac,
)

__all__ = [
    "AsusRouterClient",
    "AsusRouterDhcpManager",
    "AsusRouterScanner",
    "ConsoleTableReporter",
    "CsvReporter",
    "DeviceReporter",
    "DeviceRepository",
    "DhcpRange",
    "DhcpReservationManager",
    "DiffReporter",
    "DnsConfig",
    "DnsManager",
    "JsonDeviceRepository",
    "JsonReporter",
    "LinuxArpScanner",
    "LinuxDhcpReservationManager",
    "LinuxDnsmasqConfigGenerator",
    "LinuxHostsFileManager",
    "LinuxNmapScanner",
    "NetworkConfig",
    "NetworkDevice",
    "NetworkScanner",
    "RouterAuthError",
    "RouterConfig",
    "RouterDhcpManager",
    "validate_cidr",
    "validate_hostname",
    "validate_ipv4",
    "validate_mac",
]
