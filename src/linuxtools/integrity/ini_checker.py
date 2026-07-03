"""Interface abstraite pour la vérification d'intégrité de sections INI."""

from abc import ABC, abstractmethod
from pathlib import Path


class IniSectionIntegrityChecker(ABC):
    """Vérifie qu'un fichier INI contient les valeurs d'une section attendue.

    Complète IntegrityChecker (comparaison source/destination) pour le cas
    spécifique où l'on compare un fichier INI contre un jeu de valeurs
    attendues représenté par un objet section.

    Ce ABC est indépendant de IntegrityChecker car la sémantique de
    verify() est différente : on compare un fichier contre un modèle,
    non deux chemins l'un contre l'autre.
    """

    @abstractmethod
    def verify(self, file_path: Path, section: object) -> bool:
        """Vérifie qu'un fichier INI contient les valeurs attendues.

        Args:
            file_path: Chemin du fichier INI à vérifier.
            section: Objet section portant les valeurs attendues.
                Doit exposer section_name() -> str et to_dict() -> dict.

        Returns:
            True si toutes les valeurs correspondent, False sinon.
        """
        ...
