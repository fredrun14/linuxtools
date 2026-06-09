"""Interface abstraite pour la validation."""

from abc import ABC, abstractmethod
from pathlib import Path


class Validator(ABC):
    """Contrat commun pour tous les validateurs de préconditions système."""

    @abstractmethod
    def validate(self) -> None:
        """
        Exécute la validation.

        Raises:
            ValueError: Si une valeur est invalide
            PermissionError: Si les permissions sont insuffisantes
            Exception: Selon l'implémentation concrète
        """
        ...

    @staticmethod
    def _resolve_parent(path: str) -> Path:
        """Résout le répertoire parent et vérifie son existence.

        Args:
            path: Chemin du fichier à valider.

        Returns:
            Répertoire parent résolu.

        Raises:
            ValueError: Si le répertoire parent n'existe pas.
        """
        parent = Path(path).resolve().parent
        if not parent.exists():
            raise ValueError(
                f"Le répertoire {parent} n'existe pas."
            )
        return parent
