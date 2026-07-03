"""Provider de credentials depuis un fichier .env.

Ce module fournit DotEnvCredentialProvider qui charge un fichier
.env via python-dotenv (dépendance optionnelle) et lit les
credentials depuis un dictionnaire interne, sans polluer os.environ.
"""

import stat
from pathlib import Path

from linuxtools.credentials.base import CredentialProvider
from linuxtools.logging.base import Logger


class DotEnvCredentialProvider(CredentialProvider):
    """Charge un fichier .env et expose les credentials via un dict interne.

    N'injecte rien dans os.environ : les secrets restent invisibles
    pour les sous-processus (contrairement à load_dotenv).

    Les clés sont normalisées en majuscules (key.upper()).

    Si python-dotenv n'est pas installé, is_available() retourne
    False et get() retourne toujours None (dégradation gracieuse).

    Attributes:
        _dotenv_path: Chemin vers le fichier .env.
        _logger: Logger optionnel.
        _values: Dictionnaire clé → valeur issu de dotenv_values().
        _loaded: True si le fichier a été chargé avec succès.
    """

    def __init__(
        self,
        dotenv_path: str | Path,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le provider de fichier .env.

        Args:
            dotenv_path: Chemin vers le fichier .env.
            logger: Logger optionnel (injection de dépendance).
        """
        self._dotenv_path = Path(dotenv_path)
        self._logger = logger
        self._loaded: bool = False
        self._values: dict[str, str | None] = {}

    def _check_permissions(self) -> None:
        """Avertit si le .env est lisible par groupe ou autres utilisateurs."""
        mode = self._dotenv_path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            if self._logger:
                self._logger.log_warning(
                    f"{self._dotenv_path} accessible par d'autres "
                    f"utilisateurs (permissions trop larges)."
                )

    def load(self) -> bool:
        """Charge le fichier .env dans le dict interne.

        Ne modifie pas os.environ.

        Returns:
            True si le fichier a été chargé avec succès.
        """
        try:
            from dotenv import dotenv_values
        except ImportError:
            return False
        if not self._dotenv_path.exists():
            if self._logger:
                self._logger.log_warning(
                    f"Fichier .env introuvable : "
                    f"{self._dotenv_path}"
                )
            return False
        self._check_permissions()
        self._values = dotenv_values(self._dotenv_path)
        self._loaded = True
        return True

    def get(
        self,
        service: str,
        key: str,
    ) -> str | None:
        """Charge le .env si nécessaire puis lit la clé depuis le dict interne.

        Les clés sont normalisées en majuscules (key.upper()).

        Args:
            service: Nom du service (non utilisé, pour compatibilité
                avec l'interface).
            key: Nom de la variable (normalisée en majuscules).

        Returns:
            Valeur de la variable ou None si absente ou vide.
        """
        if not self._loaded:
            self.load()
        value = self._values.get(key.upper())
        return value if value else None

    def is_available(self) -> bool:
        """Indique si ce provider est opérationnel.

        Returns:
            True si python-dotenv est installé et le fichier existe.
        """
        try:
            import dotenv  # noqa: F401
        except ImportError:
            return False
        return self._dotenv_path.exists()

    @property
    def source_name(self) -> str:
        """Nom court de la source.

        Returns:
            "dotenv"
        """
        return "dotenv"
