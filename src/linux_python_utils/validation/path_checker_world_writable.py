"""Validateur de sécurité pour fichiers world-writable."""

import os
import stat
from pathlib import Path

from linux_python_utils.validation.base import Validator


class PathCheckerWorldWritable(Validator):
    """Vérifie qu'un fichier n'est pas accessible en écriture par tous.

    Essentiel pour tout script exécuté en root chargeant un fichier
    de configuration : un fichier world-writable pourrait être modifié
    par un utilisateur non-privilégié (élévation de privilèges).

    Utilise ``os.lstat`` (TOCTOU-safe, ne suit PAS les liens symboliques)
    pour un contrôle atomique. Un lien symbolique est traité comme
    world-accessible et est donc rejeté.

    Lève des exceptions standard (FileNotFoundError, PermissionError)
    pour rester générique. Le consommateur peut les wrapper vers ses
    propres exceptions métier.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialise le validateur avec le chemin du fichier à vérifier.

        Le chemin n'est pas résolu (pas de suivi de lien symbolique)
        afin que ``validate()`` puisse inspecter le lien lui-même.

        Args:
            path: Chemin vers le fichier dont vérifier les permissions.
        """
        self._path = Path(path)

    def validate(self) -> None:
        """Vérifie que le fichier n'est pas world-writable.

        Utilise ``os.lstat`` (appel unique, TOCTOU-safe) pour obtenir
        les métadonnées sans suivre les liens symboliques.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            PermissionError: Si le fichier est modifiable par tous
                les utilisateurs (bit S_IWOTH positionné) ou s'il
                s'agit d'un lien symbolique (mode 0o777 sur Linux).
        """
        try:
            st = os.lstat(self._path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Fichier introuvable : {self._path}"
            ) from exc
        if st.st_mode & stat.S_IWOTH:
            raise PermissionError(
                f"Le fichier {self._path} est modifiable par tous "
                f"les utilisateurs (world-writable). "
                f"Corrigez avec : chmod o-w {self._path}"
            )
