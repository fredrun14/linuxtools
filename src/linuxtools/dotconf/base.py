"""Interfaces abstraites pour la gestion de fichiers de configuration INI.

Ce module définit les contrats (ABC) pour :
- IniSection : représentation d'une section de fichier INI
- IniConfig : représentation d'un fichier INI complet
- IniConfigManager : gestion lecture/écriture de fichiers INI
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class IniSection(ABC):
    """Interface pour une section de fichier de configuration INI.

    Une section représente un bloc [nom_section] dans un fichier INI
    avec ses paires clé=valeur.
    """

    @staticmethod
    @abstractmethod
    def section_name() -> str:
        """Retourne le nom de la section dans le fichier INI.

        Returns:
            Nom de la section (ex: "commands", "main").
        """
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, str]:
        """Convertit la section en dictionnaire clé-valeur.

        Returns:
            Dictionnaire des paires clé=valeur de la section.
        """
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, str]) -> "IniSection":
        """Crée une instance de section depuis un dictionnaire.

        Args:
            data: Dictionnaire des paires clé=valeur.

        Returns:
            Instance de la section.
        """
        ...


class IniConfig(ABC):
    """Interface pour un fichier de configuration INI complet.

    Représente l'ensemble des sections d'un fichier INI.
    """

    @abstractmethod
    def sections(self) -> list[IniSection]:
        """Retourne toutes les sections de la configuration.

        Returns:
            Liste des sections IniSection.
        """
        ...

    @abstractmethod
    def to_ini(self) -> str:
        """Génère le contenu du fichier INI.

        Returns:
            Contenu formaté du fichier INI.
        """
        ...

    @classmethod
    @abstractmethod
    def from_file(cls, path: Path) -> "IniConfig":
        """Charge une configuration depuis un fichier INI.

        Args:
            path: Chemin du fichier INI à charger.

        Returns:
            Instance de la configuration.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si le fichier est mal formaté.
        """
        ...


class IniConfigManager(ABC):
    """Interface pour la gestion de fichiers de configuration INI.

    Gère les opérations de lecture, écriture et mise à jour
    de fichiers de configuration INI.
    """

    @abstractmethod
    def read(self, path: Path) -> dict[str, dict[str, str]]:
        """Lit un fichier INI et retourne son contenu.

        Args:
            path: Chemin du fichier INI.

        Returns:
            Dictionnaire imbriqué {section: {clé: valeur}}.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
        """
        ...

    @abstractmethod
    def write(self, path: Path, config: IniConfig) -> None:
        """Écrit une configuration dans un fichier INI.

        Args:
            path: Chemin du fichier de destination.
            config: Configuration à écrire.
        """
        ...

    @abstractmethod
    def update_section(
        self,
        path: Path,
        section: IniSection,
        validators: dict[str, Any] | None = None,
    ) -> bool:
        """Met à jour une section dans un fichier INI existant.

        Args:
            path: Chemin du fichier INI.
            section: Section avec les nouvelles valeurs.
            validators: Validateurs optionnels pour les valeurs.

        Returns:
            True si des modifications ont été effectuées, False sinon.

        Raises:
            ValueError: Si la validation échoue.
        """
        ...

    @abstractmethod
    def is_section_configured(
        self,
        path: Path,
        section: IniSection,
    ) -> bool:
        """Vérifie si une section est configurée avec les valeurs attendues.

        Compare uniquement les clés définies dans section.to_dict() avec
        les valeurs présentes dans le fichier. Les clés supplémentaires
        du fichier sont ignorées.

        Args:
            path: Chemin du fichier INI à vérifier.
            section: Section contenant les valeurs cibles.

        Returns:
            True si toutes les clés de la section ont déjà les valeurs
            attendues, False si le fichier est absent, si la section
            manque, ou si au moins une valeur diffère.
        """
        ...
