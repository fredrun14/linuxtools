"""Module de gestion des erreurs."""

from linux_python_utils.errors.base import ErrorHandler, ErrorHandlerChain
from linux_python_utils.errors.console_handler import ConsoleErrorHandler
from linux_python_utils.errors.context import ErrorContext
from linux_python_utils.errors.exceptions import (
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
)
from linux_python_utils.errors.logger_handler import LoggerErrorHandler

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
    "RollbackError",
    "SystemRequirementError",
    "ValidationError",
]
