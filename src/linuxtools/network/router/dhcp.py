"""Gestionnaire DHCP avec push direct vers le routeur ASUS."""

import dataclasses

from linuxtools.logging.base import Logger
from linuxtools.network.base import RouterDhcpManager
from linuxtools.network.config import NetworkConfig
from linuxtools.network.ip_utils import _allocate_fixed_ips
from linuxtools.network.models import NetworkDevice
from linuxtools.network.router._nvram import (
    _parse_nvram_reservations,
)
from linuxtools.network.router.client import (
    AsusRouterClient,
    RouterConfig,
)


class AsusRouterDhcpManager(RouterDhcpManager):
    """Gestionnaire DHCP avec push direct vers le routeur ASUS.

    Attributes:
        _config: Configuration reseau.
        _router_config: Configuration routeur.
        _logger: Logger optionnel.
        _client: Client HTTP.
    """

    def __init__(
        self,
        config: NetworkConfig,
        router_config: RouterConfig,
        logger: Logger | None = None,
        client: AsusRouterClient | None = None,
    ) -> None:
        """Initialise le gestionnaire DHCP routeur.

        Args:
            config: Configuration reseau.
            router_config: Configuration de connexion.
            logger: Logger optionnel.
            client: Client HTTP optionnel (injection).
        """
        self._config = config
        self._router_config = router_config
        self._logger = logger
        self._client = client or AsusRouterClient(
            router_config, logger=logger
        )

    def generate_reservations(
        self, devices: list[NetworkDevice]
    ) -> list[NetworkDevice]:
        """Alloue des IP fixes depuis la plage DHCP.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Liste avec IP fixes assignees.

        Raises:
            ValueError: Si la plage DHCP manque ou est
                epuisee.
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
        """Exporte les reservations au format NVRAM ASUS.

        Format : <MAC>IP<MAC>IP...
        MAC en majuscules avec ':'.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Chaine dhcp_staticlist.
        """
        parts = []
        for device in devices:
            if device.fixed_ip is None:
                continue
            mac = device.mac.upper()
            parts.append(f"<{mac}>{device.fixed_ip}")
        return "".join(parts)

    def apply_reservations(
        self, devices: list[NetworkDevice]
    ) -> None:
        """Envoie les reservations DHCP vers le routeur.

        Lit la configuration DHCP actuelle du routeur avant
        d'envoyer pour eviter d'ecraser les autres parametres.

        Args:
            devices: Peripheriques avec fixed_ip.

        Raises:
            RouterAuthError: Si l'authentification echoue.
            RuntimeError: Si l'envoi echoue.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            dhcp_cfg = self._client.get_nvram(
                "dhcp_enable_x",
                "dhcp_start",
                "dhcp_end",
                "dhcp_lease",
                "dhcp_static_x",
            )
            static_list, hostnames = (
                self._build_nvram_strings(devices)
            )
            self._client.set_static_reservations(
                static_list, hostnames, dhcp_cfg
            )
        finally:
            self._client.logout()
        if self._logger:
            count = sum(
                1
                for d in devices
                if d.fixed_ip is not None
            )
            self._logger.log_info(
                f"{count} reservation(s) DHCP "
                f"appliquee(s) sur le routeur"
            )

    def read_reservations(self) -> list[NetworkDevice]:
        """Lit les reservations DHCP existantes du routeur.

        Returns:
            Liste de NetworkDevice avec ip et mac.

        Raises:
            RouterAuthError: Si l'authentification echoue.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            nvram = self._client.get_nvram(
                "dhcp_staticlist",
                "dhcp_hostnames",
            )
        finally:
            self._client.logout()
        return self._parse_nvram_staticlist(
            nvram.get("dhcp_staticlist", ""),
            nvram.get("dhcp_hostnames", ""),
        )

    def _build_nvram_strings(
        self, devices: list[NetworkDevice]
    ) -> tuple[str, str]:
        """Construit les chaines NVRAM dhcp_staticlist et
        dhcp_hostnames.

        Args:
            devices: Peripheriques avec fixed_ip.

        Returns:
            Tuple (static_list, hostnames).
        """
        static_parts: list[str] = []
        hostname_parts: list[str] = []
        for device in devices:
            if device.fixed_ip is None:
                continue
            mac = device.mac.upper()
            static_parts.append(
                f"<{mac}>{device.fixed_ip}"
            )
            name = device.hostname or device.dns_name
            if name:
                hostname_parts.append(f"<{mac}>{name}")
        return (
            "".join(static_parts),
            "".join(hostname_parts),
        )

    @staticmethod
    def _parse_nvram_staticlist(
        static_list: str,
        hostnames_str: str,
    ) -> list[NetworkDevice]:
        """Parse la chaine NVRAM dhcp_staticlist.

        Args:
            static_list: Chaine <MAC>IP<MAC>IP...
            hostnames_str: Chaine <MAC>hostname...

        Returns:
            Liste de NetworkDevice.
        """
        reservations = _parse_nvram_reservations(
            static_list, hostnames_str
        )
        devices: list[NetworkDevice] = []
        for mac, (ip, hostname) in reservations.items():
            try:
                devices.append(
                    NetworkDevice(
                        ip=ip,
                        mac=mac,
                        fixed_ip=ip,
                        hostname=hostname,
                    )
                )
            except ValueError:
                continue
        return devices
