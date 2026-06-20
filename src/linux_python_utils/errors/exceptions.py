"""
Module contenant les exceptions communes.

Ce module suit le principe SRP en isolant la gestion des exceptions.
"""

import os
from pathlib import Path


class ApplicationError(Exception):
    """Exception de base pour toutes les erreurs applicatives."""


class ConfigurationError(ApplicationError):
    """Exception levée lors d'une erreur de configuration."""


class FileConfigurationError(ConfigurationError):
    """Exception levée lors d'une erreur dans un fichier de configuration."""


class SystemRequirementError(ApplicationError):
    """Exception levée quand un prérequis système est manquant."""


class MissingDependencyError(SystemRequirementError):
    """Exception levée quand une dépendance requise est absente."""


class ValidationError(ApplicationError):
    """Exception levée lors d'un échec de validation."""


class InstallationError(ApplicationError):
    """Exception levée lors d'un échec d'installation."""


class AppPermissionError(ApplicationError):
    """Exception levée en cas de permissions insuffisantes."""


class RollbackError(ApplicationError):
    """Exception levée quand une ou plusieurs actions de rollback échouent."""


class IntegrityError(ApplicationError):
    """Exception levée lors d'un échec de vérification d'intégrité.

    Attributes:
        path: Chemin du fichier dont l'intégrité est compromise.
        expected: Checksum attendu (None si fichier manquant).
        actual: Checksum calculé (None si fichier manquant).
    """

    def __init__(
        self,
        path: str | Path,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        """Initialise l'erreur d'intégrité.

        Args:
            path: Chemin du fichier concerné.
            expected: Checksum attendu (source).
            actual: Checksum obtenu (destination).
        """
        self.path = path
        self.expected = expected
        self.actual = actual
        if expected and actual:
            msg = (
                f"Intégrité compromise : {path} "
                f"(attendu={expected[:8]}…, obtenu={actual[:8]}…)"
            )
        else:
            msg = f"Intégrité compromise : {path}"
        super().__init__(msg)


class CommandExecutionError(ApplicationError):
    """Exception levée quand une commande système retourne un code non nul."""


def require_root(message: str | None = None) -> None:
    """Lève AppPermissionError si le processus courant n'est pas root.

    Args:
        message: Message d'erreur personnalisé. Si None, utilise le
            message par défaut.

    Raises:
        AppPermissionError: Si os.geteuid() != 0.
    """
    if os.geteuid() != 0:
        raise AppPermissionError(
            message or "Cette opération nécessite les droits root."
        )
