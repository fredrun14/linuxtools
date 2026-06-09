"""
Module contenant les exceptions communes.

Ce module suit le principe SRP en isolant la gestion des exceptions.
"""

import os


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
    """Exception levée lors d'un échec de vérification d'intégrité."""


class CommandExecutionError(ApplicationError):
    """Exception levée quand une commande système retourne un code non nul."""


def require_root() -> None:
    """Lève AppPermissionError si le processus courant n'est pas root.

    Raises:
        AppPermissionError: Si os.getuid() != 0.
    """
    if os.getuid() != 0:
        raise AppPermissionError(
            "Cette opération nécessite les droits root."
        )
