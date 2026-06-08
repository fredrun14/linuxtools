"""
Module contenant les exceptions communes.

Ce module suit le principe SRP en isolant la gestion des exceptions.
"""


class ApplicationError(Exception):
    """Exception de base pour toutes les applications."""


class ConfigurationError(ApplicationError):
    """Exception de base pour toutes les Configurations."""


class FileConfigurationError(ConfigurationError):
    """Exception de base pour tous les fichiers de configurations."""


class SystemRequirementError(ApplicationError):
    """Exception de base pour tous les systèmes de dépendances."""


class MissingDependencyError(SystemRequirementError):
    """Exception de base pour toutes les dépendances manquantes."""


class ValidationError(ApplicationError):
    """Exception de base pour toutes les validations."""


class InstallationError(ApplicationError):
    """Exception de base pour toutes les installations."""


class AppPermissionError(ApplicationError):
    """Exception de base pour toutes les permissions applicatives."""


class RollbackError(ApplicationError):
    """Exception de base pour toutes les Rollback."""


class IntegrityError(ApplicationError):
    """Exception levée lors d'un échec de vérification d'intégrité."""


class CommandExecutionError(ApplicationError):
    """Exception levée quand une commande système retourne un code non nul."""
