"""Validateur de point de montage pour chemins réseau ou amovibles."""

import os
from pathlib import Path

from linuxtools.validation.base import Validator


class PathCheckerMountPoint(Validator):
    """Vérifie qu'un chemin est couvert par un point de montage actif.

    Remonte l'arborescence depuis le chemin donné jusqu'au premier
    point de montage. Lève ValueError si seule la racine / est
    trouvée (pas de montage réseau ou amovible).

    Utile pour valider que des destinations NFS, CIFS ou USB sont
    bien montées avant d'y écrire.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialise le validateur avec le chemin à vérifier.

        Args:
            path: Chemin à vérifier (peut être un sous-répertoire
                du point de montage).
        """
        self._path = Path(path)

    def validate(self) -> None:
        """Vérifie qu'un point de montage actif couvre le chemin.

        Raises:
            ValueError: Si aucun montage spécifique n'est trouvé
                entre le chemin et la racine du système de fichiers.
        """
        mount = self._nearest_mount_point(self._path)
        if mount == Path("/"):
            raise ValueError(
                f"Aucun point de montage actif pour : {self._path}"
            )

    def _nearest_mount_point(self, path: Path) -> Path:
        """Remonte l'arborescence jusqu'au premier point de montage.

        Args:
            path: Chemin de départ.

        Returns:
            Premier chemin (ou ancêtre) qui est un point de montage.
        """
        current = path
        while not os.path.ismount(current):
            parent = current.parent
            if parent == current:
                return current
            current = parent
        return current
