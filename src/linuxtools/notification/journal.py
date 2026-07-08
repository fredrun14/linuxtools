"""Notifier journald via le socket natif du journal systemd.

Écrit directement sur /run/systemd/journal/socket (datagramme
AF_UNIX) sans dépendance externe. Les champs multilignes sont
sérialisés au format binaire du protocole journald (nom, saut de
ligne, taille little-endian 64 bits, données).

Consultation : ``journalctl -t <app_name>``.

Example:

    from linuxtools.notification import JournaldNotifier, Notification

    notifier = JournaldNotifier(app_name="backup-nas")
    notifier.send(Notification(title="Backup", message="Terminé"))
"""

import socket

from linuxtools.logging.base import Logger
from linuxtools.notification.base import Notifier
from linuxtools.notification.exceptions import NotificationSendError
from linuxtools.notification.models import Notification, Urgency

_JOURNAL_SOCKET = "/run/systemd/journal/socket"

_JOURNAL_PRIORITIES: dict[Urgency, int] = {
    Urgency.LOW: 6,  # info
    Urgency.NORMAL: 5,  # notice
    Urgency.CRITICAL: 3,  # err
}


class JournaldNotifier(Notifier):
    """Écrit des notifications dans le journal systemd.

    Attributes:
        _app_name: Identifiant syslog (SYSLOG_IDENTIFIER).
        _socket_path: Chemin du socket journald (injectable pour
            les tests).
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        app_name: str,
        socket_path: str = _JOURNAL_SOCKET,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le notifier journald.

        Args:
            app_name: Identifiant syslog (non vide).
            socket_path: Chemin du socket datagramme journald.
            logger: Logger optionnel.

        Raises:
            ValueError: Si app_name est vide.
        """
        if not app_name:
            raise ValueError("app_name est requis")
        self._app_name = app_name
        self._socket_path = socket_path
        self._logger = logger

    def send(self, notification: Notification) -> None:
        """Écrit la notification dans le journal systemd.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si le socket journald est
                indisponible ou refuse le datagramme.
        """
        priority = _JOURNAL_PRIORITIES[notification.urgency]
        payload = b"".join(
            (
                self._encode_field("MESSAGE", notification.message),
                self._encode_field("PRIORITY", str(priority)),
                self._encode_field(
                    "SYSLOG_IDENTIFIER", self._app_name
                ),
                self._encode_field(
                    "NOTIFICATION_TITLE", notification.title
                ),
            )
        )
        try:
            with socket.socket(
                socket.AF_UNIX, socket.SOCK_DGRAM
            ) as sock:
                sock.sendto(payload, self._socket_path)
        except OSError as exc:
            raise NotificationSendError(
                f"Écriture journald impossible"
                f" ({self._socket_path}) : {exc}"
            ) from exc

    @staticmethod
    def _encode_field(name: str, value: str) -> bytes:
        """Sérialise un champ au format datagramme journald.

        Les valeurs sans saut de ligne utilisent la forme simple
        ``NAME=value\\n`` ; les valeurs multilignes utilisent la
        forme binaire avec taille little-endian 64 bits.

        Args:
            name: Nom du champ (majuscules).
            value: Valeur du champ.

        Returns:
            Champ sérialisé en octets.
        """
        data = value.encode("utf-8")
        if b"\n" in data:
            return (
                name.encode("ascii")
                + b"\n"
                + len(data).to_bytes(8, "little")
                + data
                + b"\n"
            )
        return name.encode("ascii") + b"=" + data + b"\n"
