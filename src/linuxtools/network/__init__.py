"""Module reseau pour la gestion des peripheriques.

Ce module fournit les outils pour scanner, inventorier et
gerer les peripheriques d'un reseau local.
"""

from typing import TYPE_CHECKING

from linuxtools._lazy import make_lazy_getattr
from linuxtools.network.base import (
    DeviceReporter,
    DeviceRepository,
    DhcpReservationManager,
    DnsManager,
    MacFilterManager,
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
    MacFilterStatus,
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

if TYPE_CHECKING:
    from linuxtools.network.router import (
        AsusRouterClient,
        AsusRouterDhcpManager,
        AsusRouterMacFilterManager,
        AsusRouterScanner,
        RouterAuthError,
        RouterConfig,
    )

# Noms dépendant de l'extra optionnel `network` (webapitools) : chargés au
# premier accès, pour que `import linuxtools.network` reste possible
# sans l'extra (CDC-20260910, Q-02 : l'échec n'a lieu qu'à l'usage).
_ROUTER_NOMS = (
    "AsusRouterClient",
    "AsusRouterDhcpManager",
    "AsusRouterMacFilterManager",
    "AsusRouterScanner",
    "RouterAuthError",
    "RouterConfig",
)
__getattr__ = make_lazy_getattr(
    __name__, dict.fromkeys(_ROUTER_NOMS, "linuxtools.network.router")
)

__all__ = [
    "AsusRouterClient",
    "AsusRouterDhcpManager",
    "AsusRouterMacFilterManager",
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
    "MacFilterManager",
    "MacFilterStatus",
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
