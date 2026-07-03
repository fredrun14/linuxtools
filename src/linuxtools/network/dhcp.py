"""Gestion des reservations DHCP statiques.

Ce module fournit l'implementation LinuxDhcpReservationManager
pour allouer des adresses IP fixes et exporter la configuration
dnsmasq.
"""


from linuxtools.logging.base import Logger
from linuxtools.network.base import (
    DhcpReservationManager,
)
from linuxtools.network.config import (
    DhcpRange,
    NetworkConfig,
)
from linuxtools.network.ip_utils import _allocate_fixed_ips
from linuxtools.network.models import NetworkDevice


class LinuxDhcpReservationManager(DhcpReservationManager):
    """Gestionnaire de reservations DHCP statiques.

    Attributes:
        _config: Configuration reseau.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        config: NetworkConfig,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le gestionnaire DHCP.

        Args:
            config: Configuration reseau.
            logger: Logger optionnel.
        """
        self._config = config
        self._logger = logger

    def generate_reservations(
        self, devices: list[NetworkDevice]
    ) -> list[NetworkDevice]:
        """Alloue des IP fixes aux peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Liste des peripheriques avec IP fixes.

        Raises:
            ValueError: Si la plage DHCP n'est pas configuree
                ou est epuisee.
        """
        if self._config.dhcp_range is None:
            raise ValueError(
                "Plage DHCP non configuree"
            )
        result = _allocate_fixed_ips(
            devices, self._config.dhcp_range
        )
        if self._logger:
            self._logger.log_info(
                f"Reservations DHCP : {len(result)} "
                f"peripherique(s)"
            )
        return result

    def export_reservations(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Exporte les reservations au format dnsmasq.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Configuration dnsmasq formatee.
        """
        lines = [
            "# Reservations DHCP statiques",
            "# Genere par scanNetHome",
        ]
        for device in devices:
            if device.fixed_ip is None:
                continue
            entry = f"dhcp-host={device.mac},{device.fixed_ip}"
            if device.hostname:
                entry += f",{device.hostname}"
            lines.append(entry)
        return "\n".join(lines) + "\n"
