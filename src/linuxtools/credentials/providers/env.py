"""Provider de credentials depuis les variables d'environnement.

Ce module fournit EnvCredentialProvider qui lit les credentials
depuis os.environ sans aucune dependance externe.
"""

import os

from linuxtools.credentials.base import CredentialProvider
from linuxtools.logging.base import Logger


class EnvCredentialProvider(CredentialProvider):
    """Lit les credentials depuis os.environ.

    La cle cherchee est le parametre key en majuscules.
    Exemple : key="ASUS_ROUTER_PASSWORD"
    -> os.environ.get("ASUS_ROUTER_PASSWORD")

    Attributes:
        _logger: Logger optionnel pour le suivi des operations.
    """

    def __init__(
        self,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le provider de variables d'environnement.

        Args:
            logger: Logger optionnel (injection de dependance).
        """
        self._logger = logger

    def get(
        self,
        service: str,
        key: str,
    ) -> str | None:
        """Lit os.environ[key.upper()] ou None si absent.

        Args:
            service: Nom du service (non utilise, pour
                compatibilite avec l'interface).
            key: Nom de la variable d'environnement.

        Returns:
            Valeur de la variable ou None.
        """
        value = os.environ.get(key.upper())
        return value if value else None

    def is_available(self) -> bool:
        """Indique si ce provider est operationnel.

        Returns:
            Toujours True (os.environ est toujours disponible).
        """
        return True

    @property
    def source_name(self) -> str:
        """Nom court de la source.

        Returns:
            "env"
        """
        return "env"
