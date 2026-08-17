"""Gestionnaire de filtre MAC Wi-Fi pour routeur ASUS."""

from webapitools import AsusRouterClient
from webapitools.core.exceptions import AuthError

from linuxtools.logging.base import Logger
from linuxtools.network.base import MacFilterManager
from linuxtools.network.models import (
    MacFilterStatus,
    NetworkDevice,
)
from linuxtools.network.router.client import (
    RouterAuthError,
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
        # logger non transmis au client webapitools : son parametre
        # `logger` attend un logging.Logger (stdlib), incompatible
        # avec l'ABC linuxtools.logging.base.Logger. Le logging propre
        # a cet adaptateur (self._logger) reste inchange ci-dessous.
        self._client = client or AsusRouterClient(
            router_config.url,
            router_config.username,
            router_config.password,
            verify_tls=router_config.verify_tls,
            timeout=router_config.timeout,
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
        try:
            self._client.login()
        except AuthError as exc:
            raise RouterAuthError(str(exc)) from exc
        try:
            macs = [d.mac for d in devices]
            self._client.set_mac_filter(mode, macs, bands)
        finally:
            self._client.logout()
        if self._logger:
            self._logger.log_info(
                f"Filtre MAC applique : {len(devices)} "
                f"appareil(s), mode={mode}"
            )

    def read_mac_filter(self, bands: list[int]) -> list[MacFilterStatus]:
        """Lit la config du filtre MAC depuis le routeur.

        Args:
            bands: Bandes a lire.

        Returns:
            Liste de MacFilterStatus, une entree par bande.

        Raises:
            RouterAuthError: Si l'authentification echoue.
        """
        try:
            self._client.login()
        except AuthError as exc:
            raise RouterAuthError(str(exc)) from exc
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
            mode = nvram.get(f"wl{band}_macmode", "disabled")
            raw_macs = nvram.get(f"wl{band}_maclist_x", "")
            macs = tuple(m.lower() for m in raw_macs.split() if m)
            result.append(MacFilterStatus(band=band, mode=mode, macs=macs))
        return result
