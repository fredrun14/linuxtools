"""Interface abstraite pour la gestion de configuration."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ConfigManager(ABC):
    """
    Interface abstraite pour la gestion de configuration.

    Définit le contrat pour les gestionnaires de configuration,
    permettant différentes implémentations (fichier, base de données,
    service distant, etc.) tout en respectant le principe DIP.
    """

    @abstractmethod
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Récupère une valeur par chemin pointé.

        Args:
            key_path: Chemin vers la clé (ex: "backup.rsync.options")
            default: Valeur par défaut si la clé n'existe pas

        Returns:
            La valeur trouvée ou la valeur par défaut
        """
        ...

    @abstractmethod
    def get_section(self, section: str) -> dict[str, Any]:
        """
        Récupère une section complète de la configuration.

        Args:
            section: Nom de la section

        Returns:
            Dictionnaire de la section ou dict vide
        """
        ...

    @abstractmethod
    def get_profile(self, profile_name: str) -> dict[str, Any]:
        """
        Récupère un profil de la configuration.

        Args:
            profile_name: Nom du profil

        Returns:
            Dictionnaire du profil

        Raises:
            ValueError: Si le profil n'existe pas
        """
        ...

    @abstractmethod
    def list_profiles(self) -> list[str]:
        """
        Liste tous les profils disponibles.

        Returns:
            Liste des noms de profils
        """
        ...

    @abstractmethod
    def create_default_config(
        self,
        output_path: Path | None = None
    ) -> None:
        """
        Crée un fichier de configuration par défaut.

        Args:
            output_path: Chemin de sortie

        Raises:
            ValueError: Si aucun chemin n'est spécifié
        """
        ...
