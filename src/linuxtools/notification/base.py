"""Interface abstraite pour l'envoi de notifications."""

from abc import ABC, abstractmethod

from linuxtools.notification.models import Notification


class Notifier(ABC):
    """Interface pour l'envoi d'une notification via un canal.

    Chaque implémentation concrète cible un canal de diffusion
    (desktop, Gotify, email, journald…). Les erreurs d'envoi sont
    signalées via NotificationSendError ; NotifierChain permet de
    diffuser en best-effort sur plusieurs canaux.
    """

    @abstractmethod
    def send(self, notification: Notification) -> None:
        """Envoie une notification sur le canal.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si l'envoi échoue.
        """
        ...
