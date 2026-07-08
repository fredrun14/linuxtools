"""Chaîne de diffusion de notifications multi-canaux.

NotifierChain transmet chaque notification à tous les notifiers
enregistrés en best-effort, sur le modèle d'ErrorHandlerChain :
l'échec d'un canal n'empêche pas les suivants.

Example:

    from linuxtools.notification import (
        DesktopNotifier,
        GotifyNotifier,
        NotifierChain,
    )

    chain = NotifierChain(logger=logger)
    chain.add_notifier(GotifyNotifier(base_url=url, token=token))
    chain.add_notifier(DesktopNotifier(app_name="backup-nas"))

    report.finish()
    chain.send_report(report)
"""

from linuxtools.logging.base import Logger
from linuxtools.notification.base import Notifier
from linuxtools.notification.models import ExecutionReport, Notification


class NotifierChain:
    """Diffuse les notifications à tous les notifiers enregistrés.

    Chaque notifier est invoqué en best-effort : si un envoi
    échoue, l'erreur est journalisée et la diffusion continue
    sur les canaux suivants.

    Attributes:
        _notifiers: Notifiers dans l'ordre d'ajout.
        _logger: Logger optionnel.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise la chaîne avec une liste vide de notifiers.

        Args:
            logger: Logger optionnel pour tracer les échecs.
        """
        self._notifiers: list[Notifier] = []
        self._logger = logger

    def add_notifier(self, notifier: Notifier) -> None:
        """Ajoute un notifier à la chaîne.

        Args:
            notifier: Le notifier à ajouter.
        """
        self._notifiers.append(notifier)

    def send(self, notification: Notification) -> bool:
        """Diffuse la notification sur tous les canaux.

        Args:
            notification: La notification à diffuser.

        Returns:
            True si au moins un canal a réussi, False sinon.
        """
        delivered = False
        for notifier in self._notifiers:
            channel = type(notifier).__name__
            try:
                notifier.send(notification)
                delivered = True
                if self._logger:
                    self._logger.log_info(
                        f"Notification envoyée via {channel}"
                    )
            except Exception as exc:
                if self._logger:
                    self._logger.log_error(
                        f"Échec de l'envoi via {channel} : {exc}"
                    )
        return delivered

    def send_report(
        self,
        report: ExecutionReport,
        icon_success: str = "emblem-default",
        icon_failure: str = "dialog-error",
    ) -> bool:
        """Diffuse le compte rendu d'exécution sur tous les canaux.

        Args:
            report: Le rapport d'exécution à diffuser.
            icon_success: Icône desktop en cas de succès.
            icon_failure: Icône desktop en cas d'échec.

        Returns:
            True si au moins un canal a réussi, False sinon.
        """
        notification = report.to_notification(
            icon_success=icon_success,
            icon_failure=icon_failure,
        )
        return self.send(notification)
