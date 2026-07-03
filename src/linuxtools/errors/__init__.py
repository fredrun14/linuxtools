"""Module de gestion des erreurs."""

from linuxtools.errors.base import ErrorHandler, ErrorHandlerChain
from linuxtools.errors.console_handler import ConsoleErrorHandler
from linuxtools.errors.context import ErrorContext
from linuxtools.errors.exceptions import (
    AppPermissionError,
    ApplicationError,
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
