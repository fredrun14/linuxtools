"""Exceptions pour le module credentials.

Ce module definit les exceptions metier levees lors
d'operations sur les credentials. Toutes heritent de
ApplicationError pour s'integrer dans la chaine d'error
handlers (ConsoleErrorHandler, LoggerErrorHandler).
"""

from linuxtools.errors.exceptions import ApplicationError


class CredentialError(ApplicationError):
    """Exception de base pour toutes les erreurs credentials."""


class CredentialNotFoundError(CredentialError):
    """Levee quand un credential est absent de tous les providers."""


class CredentialStoreError(CredentialError):
    """Levee quand le stockage ou la suppression echoue."""


class CredentialProviderUnavailableError(CredentialError):
    """Levee quand un provider requis est indisponible."""
