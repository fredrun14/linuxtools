"""Interface abstraite pour la gestion des fichiers."""

from abc import ABC, abstractmethod


class FileManager(ABC):
    """Interface pour la gestion des fichiers."""

    @abstractmethod
    def create_file(self, file_path: str, content: str) -> bool:
        """
        Crée un fichier avec le contenu spécifié.

        Args:
            file_path: Chemin du fichier à créer
            content: Contenu du fichier

        Returns:
            True si succès, False sinon
        """
        pass

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """Vérifie si un fichier existe.

        Args:
            file_path: Chemin du fichier.

        Returns:
            True si le fichier existe, False sinon.
        """

    @abstractmethod
    def read_file(self, file_path: str) -> str:
        """Lit le contenu d'un fichier.

        Args:
            file_path: Chemin du fichier.

        Returns:
            Contenu du fichier.

        Raises:
            OSError: Si le fichier est inaccessible.
        """

    @abstractmethod
    def delete_file(self, file_path: str) -> bool:
        """Supprime un fichier.

        Args:
            file_path: Chemin du fichier.

        Returns:
            True si succès, False sinon.
        """
