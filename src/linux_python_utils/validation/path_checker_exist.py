"""Validateur d'existence de répertoires parents de chemins."""

from pathlib import Path

from linux_python_utils.validation.base import Validator


class PathChecker(Validator):
    """Vérifie que les répertoires parents des chemins existent.

    Résout les chemins (.resolve()) pour prévenir les traversées de chemin
    (path traversal — OWASP A03) avant toute vérification.

    Lève des exceptions standard (ValueError) pour rester générique.
    Le consommateur peut les wrapper vers ses propres exceptions métier.
    """

    def __init__(self, paths: list[str]) -> None:
        """Initialise le validateur avec une liste de chemins.

        Args:
            paths: Liste de chemins de fichiers à valider.
        """
        self.paths = paths

    def validate(self) -> None:
        """Valide que tous les répertoires parents existent.

        Raises:
            ValueError: Si un répertoire parent n'existe pas ou n'est pas
                un répertoire.
        """
        for path in self.paths:
            self._validate_path(path)

    def _validate_path(self, path: str) -> None:
        """Valide l'existence du répertoire parent d'un chemin.

        Args:
            path: Chemin du fichier à valider.
        """
        parent = Path(path).resolve().parent

        if not parent.exists():
            raise ValueError(
                f"Le répertoire {parent} n'existe pas."
            )

        if not parent.is_dir():
            raise ValueError(
                f"Le chemin {parent} n'est pas un répertoire."
            )
