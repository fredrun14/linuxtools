"""Notifier desktop Linux via notify-send.

Deux modes d'envoi :
    - Session courante (défaut) : notify-send direct, adapté aux
      scripts lancés depuis une session graphique.
    - all_users : diffusion à tous les utilisateurs connectés via
      loginctl + runuser, adapté aux scripts root / services et
      timers systemd (portage Python de la fonction bash générée
      par NotificationConfig).

Example:

    from linuxtools.notification import DesktopNotifier, Notification

    notifier = DesktopNotifier(app_name="backup-nas")
    notifier.send(Notification(title="Backup", message="Terminé"))
"""

from pathlib import Path

from linuxtools.commands.base import CommandExecutor
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.logging.base import Logger
from linuxtools.notification.base import Notifier
from linuxtools.notification.exceptions import NotificationSendError
from linuxtools.notification.models import Notification


class DesktopNotifier(Notifier):
    """Envoie des notifications desktop via notify-send.

    Attributes:
        _app_name: Nom d'application passé à notify-send (-a).
        _all_users: Diffusion à tous les utilisateurs connectés.
        _timeout: Timeout d'exécution des commandes en secondes.
        _executor: Exécuteur de commandes injecté.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        app_name: str,
        all_users: bool = False,
        timeout: int = 10,
        executor: CommandExecutor | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le notifier desktop.

        Args:
            app_name: Nom d'application affiché (non vide).
            all_users: Si True, notifie tous les utilisateurs
                connectés (nécessite root : loginctl + runuser).
            timeout: Timeout par commande en secondes.
            executor: Exécuteur de commandes (défaut :
                LinuxCommandExecutor).
            logger: Logger optionnel.

        Raises:
            ValueError: Si app_name est vide.
        """
        if not app_name:
            raise ValueError("app_name est requis")
        self._app_name = app_name
        self._all_users = all_users
        self._timeout = timeout
        self._executor = executor or LinuxCommandExecutor(logger=logger)
        self._logger = logger

    def send(self, notification: Notification) -> None:
        """Envoie la notification desktop.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si aucun envoi n'a abouti.
        """
        if self._all_users:
            self._send_all_users(notification)
        else:
            self._send_current_session(notification)

    def _notify_send_args(self, notification: Notification) -> list[str]:
        """Construit les arguments notify-send communs.

        Args:
            notification: La notification à envoyer.

        Returns:
            Liste d'arguments pour notify-send.
        """
        args = [
            "notify-send",
            "-u",
            notification.urgency.value,
            "-a",
            self._app_name,
        ]
        if notification.icon:
            args.extend(["-i", notification.icon])
        args.extend([notification.title, notification.message])
        return args

    def _send_current_session(self, notification: Notification) -> None:
        """Envoie via notify-send dans la session courante.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si notify-send échoue.
        """
        result = self._executor.run(
            self._notify_send_args(notification),
            timeout=self._timeout,
        )
        if not result.success:
            raise NotificationSendError(
                f"notify-send a échoué (code {result.return_code}) :"
                f" {result.stderr.strip()}"
            )

    def _send_all_users(self, notification: Notification) -> None:
        """Diffuse à tous les utilisateurs avec une session D-Bus.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si aucun utilisateur n'a pu
                être notifié.
        """
        delivered = 0
        for uid, name in self._connected_users():
            bus_path = Path(f"/run/user/{uid}/bus")
            if not bus_path.is_socket():
                continue
            command = [
                "runuser",
                "-u",
                name,
                "--",
                "env",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus_path}",
            ]
            command.extend(self._notify_send_args(notification))
            result = self._executor.run(command, timeout=self._timeout)
            if result.success:
                delivered += 1
            elif self._logger:
                self._logger.log_warning(
                    f"Notification desktop refusée pour {name} :"
                    f" {result.stderr.strip()}"
                )
        if delivered == 0:
            raise NotificationSendError(
                "Aucun utilisateur connecté n'a pu être notifié"
            )

    def _connected_users(self) -> list[tuple[str, str]]:
        """Liste les utilisateurs connectés via loginctl.

        Returns:
            Liste de tuples (uid, nom d'utilisateur).

        Raises:
            NotificationSendError: Si loginctl échoue.
        """
        result = self._executor.run(
            ["loginctl", "list-users", "--no-legend"],
            timeout=self._timeout,
        )
        if not result.success:
            raise NotificationSendError(
                f"loginctl a échoué : {result.stderr.strip()}"
            )
        users: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                users.append((parts[0], parts[1]))
        return users
