"""Gestionnaire de filtre MAC Wi-Fi pour routeur ASUS."""

from linuxtools.logging.base import Logger
from linuxtools.network.base import MacFilterManager
from linuxtools.network.models import (
    MacFilterStatus,
    NetworkDevice,
)
from linuxtools.network.router.client import (
    AsusRouterClient,
    RouterConfig,
)


class AsusRouterMacFilterManager(MacFilterManager):
    """Gestionnaire de filtre MAC Wi-Fi pour routeur ASUS.

    Attributes:
        _router_config: Configuration routeur.
        _logger: Logger optionnel.
        _client: Client HTTP.
    """

    def __init__(
        self,
        router_config: RouterConfig,
        logger: Logger | None = None,
        client: AsusRouterClient | None = None,
    ) -> None:
        """Initialise le gestionnaire de filtre MAC.

        Args:
            router_config: Configuration de connexion.
            logger: Logger optionnel.
            client: Client HTTP optionnel (injection DI).
        """
        self._router_config = router_config
        self._logger = logger
        self._client = client or AsusRouterClient(
            router_config, logger=logger
        )

    def apply_mac_filter(
        self,
        devices: list[NetworkDevice],
        mode: str,
        bands: list[int],
    ) -> None:
        """Applique le filtre MAC sur le routeur ASUS.

        Args:
            devices: Peripheriques dont les MAC sont a
                filtrer.
            mode: 'allow', 'deny' ou 'disabled'.
            bands: Bandes Wi-Fi a configurer.

        Raises:
            ValueError: Si mode ou bands invalides.
            RouterAuthError: Si authentification echoue.
            RuntimeError: Si l'envoi echoue.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            macs = [d.mac for d in devices]
            self._client.set_mac_filter(
                mode, macs, bands
            )
        finally:
            self._client.logout()
        if self._logger:
            self._logger.log_info(
                f"Filtre MAC applique : {len(devices)} "
                f"appareil(s), mode={mode}"
            )

    def read_mac_filter(
        self, bands: list[int]
    ) -> list[MacFilterStatus]:
        """Lit la config du filtre MAC depuis le routeur.

        Args:
            bands: Bandes a lire.

        Returns:
            Liste de MacFilterStatus, une entree par bande.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            keys: list[str] = []
            for band in bands:
                keys.append(f"wl{band}_macmode")
                keys.append(f"wl{band}_maclist_x")
            nvram = self._client.get_nvram(*keys)
        finally:
            self._client.logout()
        result: list[MacFilterStatus] = []
        for band in bands:
            mode = nvram.get(
                f"wl{band}_macmode", "disabled"
            )
            raw_macs = nvram.get(
                f"wl{band}_maclist_x", ""
            )
            macs = tuple(
                m.lower()
                for m in raw_macs.split()
                if m
            )
            result.append(
                MacFilterStatus(
                    band=band, mode=mode, macs=macs
                )
            )
        return result
