"""Chaine de priorite de providers de credentials.

Ce module implemente le pattern Chain of Responsibility pour
parcourir une liste ordonnee de providers jusqu'a trouver
un credential.
"""

from pathlib import Path

from linuxtools.credentials.base import CredentialProvider
from linuxtools.credentials.models import Credential
from linuxtools.credentials.providers.dotenv import (
    DotEnvCredentialProvider,
)
from linuxtools.credentials.providers.env import (
    EnvCredentialProvider,
)
from linuxtools.credentials.providers.keyring import (
    KeyringCredentialProvider,
)
from linuxtools.logging.base import Logger


class CredentialChain(CredentialProvider):
    """Parcourt une liste ordonnee de providers jusqu'au premier succes.

    Exemple de chaine pour scanNetHome :

        chain = CredentialChain([
            EnvCredentialProvider(),
            DotEnvCredentialProvider(path),
            KeyringCredentialProvider(),
        ])
        password = chain.get("scannethome", "ASUS_ROUTER_PASSWORD") or ""

    Attributes:
        _providers: Liste ordonnee de providers (priorite decroissante).
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        providers: list[CredentialProvider],
        logger: Logger | None = None,
    ) -> None:
        """Initialise la chaine de providers.

        Args:
            providers: Liste ordonnee de providers.
            logger: Logger optionnel (injection de dependance).
        """
        self._providers = providers
        self._logger = logger

    def _find(
        self,
        service: str,
        key: str,
    ) -> "tuple[CredentialProvider, str] | tuple[None, None]":
        """Retourne le premier (provider, valeur) trouvé, sinon (None, None).

        Parcourt les providers disponibles dans l'ordre. Log les escalades.

        Args:
            service: Nom du service applicatif.
            key: Nom de la clé.

        Returns:
            Tuple (provider, valeur) du premier succès, ou (None, None).
        """
        for provider in self._providers:
            if not provider.is_available():
                continue
            value = provider.get(service, key)
            if value:
                return provider, value
            if self._logger:
                self._logger.log_info(
                    f"Credential absent de {provider.source_name!r} : "
                    f"service={service!r}, key={key!r} — escalade"
                )
        return None, None

    def get(
        self,
        service: str,
        key: str,
    ) -> str | None:
        """Retourne le premier credential trouvé dans la chaîne.

        Les providers indisponibles (is_available() == False)
        sont ignorés silencieusement.

        Args:
            service: Nom du service applicatif.
            key: Nom de la clé.

        Returns:
            Valeur du credential ou None si absent de tous les
            providers.
        """
        provider, value = self._find(service, key)
        if value is not None:
            if self._logger:
                self._logger.log_info(
                    f"Credential trouvé via {provider.source_name!r} : "
                    f"service={service!r}, key={key!r}"
                )
            return value
        return None

    def get_with_source(
        self,
        service: str,
        key: str,
    ) -> Credential | None:
        """Retourne le credential avec la source d'origine.

        Args:
            service: Nom du service applicatif.
            key: Nom de la clé.

        Returns:
            Instance de Credential avec source renseignée,
            ou None si absent de tous les providers.
        """
        provider, value = self._find(service, key)
        if value is None:
            return None
        return Credential(
            service=service,
            key=key,
            value=value,
            source=provider.source_name,
        )

    def is_available(self) -> bool:
        """Indique si au moins un provider est disponible.

        Returns:
            True si au moins un provider est operationnel.
        """
        return any(
            p.is_available() for p in self._providers
        )

    @property
    def source_name(self) -> str:
        """Nom court de la source.

        Returns:
            "chain"
        """
        return "chain"

    @classmethod
    def default(
        cls,
        dotenv_path: str | Path | None = None,
        logger: Logger | None = None,
    ) -> "CredentialChain":
        """Cree la chaine standard env -> dotenv -> keyring.

        Args:
            dotenv_path: Chemin optionnel vers un fichier .env.
                Si None, le provider dotenv est omis de la chaine.
            logger: Logger optionnel partage entre les providers.

        Returns:
            Instance de CredentialChain avec les providers
            standards dans l'ordre de priorite.
        """
        providers: list[CredentialProvider] = [
            EnvCredentialProvider(logger=logger),
        ]
        if dotenv_path is not None:
            providers.append(
                DotEnvCredentialProvider(
                    dotenv_path=dotenv_path,
                    logger=logger,
                )
            )
        providers.append(
            KeyringCredentialProvider(logger=logger)
        )
        return cls(providers=providers, logger=logger)
