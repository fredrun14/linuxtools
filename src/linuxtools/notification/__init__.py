"""Module de gestion des notifications pour systèmes Linux.

Centralise l'envoi de comptes rendus de fin d'exécution de scripts
(backup, post-install…) via plusieurs canaux : desktop (notify-send),
Gotify (push), email (SMTP) et journald.

Conserve également NotificationConfig, le générateur de code bash
notify-send historique.
"""

from linuxtools.notification.base import Notifier
from linuxtools.notification.chain import NotifierChain
from linuxtools.notification.config import NotificationConfig
from linuxtools.notification.desktop import DesktopNotifier
from linuxtools.notification.email_notifier import SmtpEmailNotifier
from linuxtools.notification.exceptions import (
    NotificationError,
    NotificationSendError,
)
from linuxtools.notification.gotify import GotifyNotifier
from linuxtools.notification.journal import JournaldNotifier
from linuxtools.notification.models import (
    ExecutionReport,
    Notification,
    StepResult,
    Urgency,
)

__all__ = [
    "DesktopNotifier",
    "ExecutionReport",
    "GotifyNotifier",
    "JournaldNotifier",
    "Notification",
    "NotificationConfig",
    "NotificationError",
    "NotificationSendError",
    "Notifier",
    "NotifierChain",
    "SmtpEmailNotifier",
    "StepResult",
    "Urgency",
]
