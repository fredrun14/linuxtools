"""Validateur des permissions d'écriture sur les répertoires parents."""

import os

from linux_python_utils.validation.base import Validator


class PathCheckerPermission(Validator):
    """Vérifie les permissions d'écriture sur les répertoires parents.

    Résout les chemins (.resolve()) pour prévenir les traversées de chemin
    (path traversal — OWASP A03) avant toute vérification.

    Vérifie préalablement l'existence du répertoire pour fournir un message
    d'erreur précis : une absence de répertoire ne doit pas être confondue
    avec un refus de permission.

    Lève des exceptions standard (ValueError, PermissionError)
    pour rester générique. Le consommateur peut les wrapper
    vers ses propres exceptions métier.
    """

    def __init__(self, paths: list[str]) -> None:
        """Initialise le validateur avec une liste de chemins.

        Args:
            paths: Liste de chemins de fichiers à valider.
        """
        self.paths = paths

    def validate(self) -> None:
        """Valide les permissions d'écriture de tous les chemins.

        Raises:
            ValueError: Si un répertoire parent n'existe pas.
            PermissionError: Si un répertoire parent n'est pas accessible
                en écriture.
        """
        for path in self.paths:
            self._validate_permission(path)

    def _validate_permission(self, path: str) -> None:
        """Valide les permissions d'écriture d'un chemin spécifique.

        Args:
            path: Chemin du fichier à valider.
        """
        parent = self._resolve_parent(path)

        # os.access est un check préventif (UX) : non atomique, ignore les ACL.
        # Ne pas l'utiliser comme garde de sécurité sur des chemins sensibles.
        if not os.access(parent, os.W_OK):
            raise PermissionError(
                f"Permissions insuffisantes pour écrire dans {parent}."
            )
