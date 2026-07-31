"""Module de gestion des erreurs et du rollback.

Fournit une hiérarchie d'exceptions applicatives, une diffusion
best-effort vers plusieurs gestionnaires d'erreur (ErrorHandlerChain,
sans court-circuit sur échec), et un contexte de rollback LIFO pour
annuler une installation partiellement effectuée.

Exceptions:
- ApplicationError: Racine de la hiérarchie
- ConfigurationError, FileConfigurationError, ValidationError:
  Configuration/validation
- InstallationError, RollbackError, IntegrityError:
  Cycle de vie d'une installation
- SystemRequirementError, MissingDependencyError, AppPermissionError:
  Prérequis système
- CommandExecutionError: Échec d'une commande système (levée par identity)
- require_root: Fonction utilitaire — lève AppPermissionError si non-root

Gestionnaires d'erreur (diffusion best-effort — tous appelés, jamais
de court-circuit sur le premier échec):
- ErrorHandler: Interface abstraite (handle)
- ErrorHandlerChain: Diffuse une erreur à tous les handlers enregistrés
- ConsoleErrorHandler: Affiche l'erreur sur stderr
- LoggerErrorHandler: Journalise l'erreur via un Logger

Rollback:
- ErrorContext: Empile des actions de rollback, les exécute en LIFO

Exemple d'utilisation:
    from linuxtools.errors import (
        ErrorContext,
        ErrorHandlerChain,
        ConsoleErrorHandler,
        LoggerErrorHandler,
        InstallationError,
    )

    chain = ErrorHandlerChain(
        [ConsoleErrorHandler(), LoggerErrorHandler(logger)]
    )
    context = ErrorContext(logger=logger)
    context.add_rollback_action(
        lambda: shutil.rmtree(venv_dir), "Retrait du venv"
    )

    try:
        deployer.install()
    except InstallationError as exc:
        chain.handle(exc)
        context.execute_rollback()

Exemple d'utilisation (garde root):
    from linuxtools.errors import require_root

    require_root("Ce script doit être lancé avec sudo.")
"""

from linuxtools.errors.base import ErrorHandler, ErrorHandlerChain
from linuxtools.errors.console_handler import ConsoleErrorHandler
from linuxtools.errors.context import ErrorContext
from linuxtools.errors.exceptions import (
    ApplicationError,
    AppPermissionError,
    CommandExecutionError,
    ConfigurationError,
    FileConfigurationError,
    InstallationError,
    IntegrityError,
    MissingDependencyError,
    RollbackError,
    SystemRequirementError,
    ValidationError,
    require_root,
)
from linuxtools.errors.logger_handler import LoggerErrorHandler

__all__ = [
    "AppPermissionError",
    "ApplicationError",
    "CommandExecutionError",
    "ConfigurationError",
    "ConsoleErrorHandler",
    "ErrorContext",
    "ErrorHandler",
    "ErrorHandlerChain",
    "FileConfigurationError",
    "InstallationError",
    "IntegrityError",
    "LoggerErrorHandler",
    "MissingDependencyError",
    "require_root",
    "RollbackError",
    "SystemRequirementError",
    "ValidationError",
]
