"""Facade de gestion des credentials.

Ce module fournit CredentialManager, facade unifiee pour lire
et stocker des credentials via une chaine de providers.
"""

from pathlib import Path

from linuxtools.credentials.base import CredentialStore
from linuxtools.credentials.chain import CredentialChain
from linuxtools.credentials.exceptions import (
    CredentialNotFoundError,
    CredentialStoreError,
)
from linuxtools.credentials.providers.keyring import (
    KeyringCredentialProvider,
)
from linuxtools.logging.base import Logger


class CredentialManager:
    """Facade unifiee pour lire et stocker des credentials.

    Combine une CredentialChain pour la lecture et un
    CredentialStore optionnel pour l'ecriture.

    Usage typique :

        manager = CredentialManager.from_dotenv(
            service="scannethome",
            dotenv_path=Path("config/.env"),
        )
        password = manager.get("ASUS_ROUTER_PASSWORD")
        manager.store("ASUS_ROUTER_PASSWORD", new_password)

    Attributes:
        _service: Nom du service applicatif.
        _chain: Chaine de providers pour la lecture.
        _store: Store optionnel pour l'ecriture.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        service: str,
        chain: CredentialChain,
        store: CredentialStore | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le manager de credentials.

        Args:
            service: Nom du service applicatif (ex: "scannethome").
            chain: Chaine de providers pour la lecture.
            store: Store optionnel pour l'ecriture (ex:
                KeyringCredentialProvider).
            logger: Logger optionnel (injection de dependance).
        """
        self._service = service
        self._chain = chain
        self._store = store
        self._logger = logger

    def _require_store(self) -> CredentialStore:
        """Retourne le store ou lève si aucun n'est configuré.

        Returns:
            Le store configuré.

        Raises:
            CredentialStoreError: si aucun store n'est configuré.
        """
        if self._store is None:
            raise CredentialStoreError(
                "Aucun store de secrets configuré."
            )
        return self._store

    def get(
        self,
        key: str,
        default: str = "",
    ) -> str:
        """Lit un credential via la chaine de providers.

        Args:
            key: Nom de la cle.
            default: Valeur retournee si le credential est absent.

        Returns:
            Valeur du credential ou default.
        """
        value = self._chain.get(self._service, key)
        return value if value is not None else default

    def require(self, key: str) -> str:
        """Lit un credential en levant une erreur si absent.

        Args:
            key: Nom de la cle.

        Returns:
            Valeur du credential.

        Raises:
            CredentialNotFoundError: si le credential est absent
                de toute la chaine.
        """
        value = self._chain.get(self._service, key)
        if value is None:
            if self._logger:
                self._logger.log_warning(
                    f"Credential introuvable dans toute la chaine : "
                    f"service={self._service!r}, key={key!r}"
                )
            raise CredentialNotFoundError(
                f"Credential introuvable : "
                f"service={self._service!r}, key={key!r}"
            )
        return value

    def store(
        self,
        key: str,
        value: str,
    ) -> None:
        """Stocke un credential dans le store configure.

        Args:
            key: Nom de la cle.
            value: Valeur a stocker.

        Raises:
            CredentialStoreError: si aucun store n'est configure
                ou si l'operation echoue.
        """
        self._require_store().set(self._service, key, value)

    def delete(self, key: str) -> None:
        """Supprime un credential du store configure.

        Args:
            key: Nom de la cle.

        Raises:
            CredentialStoreError: si aucun store n'est configure.
        """
        self._require_store().delete(self._service, key)

    @classmethod
    def from_dotenv(
        cls,
        service: str,
        dotenv_path: str | Path | None = None,
        logger: Logger | None = None,
    ) -> "CredentialManager":
        """Cree un manager avec la chaine standard et le keyring store.

        Chaine : env -> dotenv (si dotenv_path fourni) -> keyring
        Store  : KeyringCredentialProvider

        Args:
            service: Nom du service applicatif.
            dotenv_path: Chemin optionnel vers un fichier .env.
            logger: Logger optionnel partage entre les composants.

        Returns:
            Instance de CredentialManager configuree.
        """
        chain = CredentialChain.default(
            dotenv_path=dotenv_path,
            logger=logger,
        )
        store = KeyringCredentialProvider(logger=logger)
        return cls(
            service=service,
            chain=chain,
            store=store,
            logger=logger,
        )
