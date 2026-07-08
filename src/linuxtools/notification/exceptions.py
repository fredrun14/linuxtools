"""Exceptions du module notification.

Rattachées à la hiérarchie applicative commune (ApplicationError)
pour rester compatibles avec ErrorHandlerChain.
"""

from linuxtools.errors.exceptions import ApplicationError


class NotificationError(ApplicationError):
    """Exception de base pour les erreurs de notification."""


class NotificationSendError(NotificationError):
    """Exception levée quand l'envoi d'une notification échoue."""
