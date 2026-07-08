"""Notifier push via un serveur Gotify auto-hébergé.

Envoie les notifications à l'API REST de Gotify
(POST /message) en stdlib uniquement (urllib).

Le token d'application ne doit pas être codé en dur : le charger
via le module credentials (CredentialChain) ou une variable
d'environnement.

Example:

    from linuxtools.notification import GotifyNotifier, Notification

    notifier = GotifyNotifier(
        base_url="https://gotify.example.lan",
        token=token,  # chargé via CredentialChain
    )
    notifier.send(Notification(title="Backup", message="Terminé"))
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from linuxtools.logging.base import Logger
from linuxtools.notification.base import Notifier
from linuxtools.notification.exceptions import NotificationSendError
from linuxtools.notification.models import Notification, Urgency

_GOTIFY_PRIORITIES: dict[Urgency, int] = {
    Urgency.LOW: 2,
    Urgency.NORMAL: 5,
    Urgency.CRITICAL: 8,
}


class GotifyNotifier(Notifier):
    """Envoie des notifications push via un serveur Gotify.

    Attributes:
        _base_url: URL de base du serveur (sans /message).
        _token: Token d'application Gotify.
        _timeout: Timeout HTTP en secondes.
        _opener: Fonction d'ouverture HTTP injectable (tests).
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 10,
        opener: Callable[..., Any] | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le notifier Gotify.

        Args:
            base_url: URL du serveur (http:// ou https://).
            token: Token d'application (non vide).
            timeout: Timeout HTTP en secondes.
            opener: Remplaçant injectable de urllib.request.urlopen.
            logger: Logger optionnel.

        Raises:
            ValueError: Si base_url n'est pas une URL http(s) ou
                si token est vide.
        """
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "base_url doit commencer par http:// ou https://"
            )
        if not token:
            raise ValueError("token est requis")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self._logger = logger

    def send(self, notification: Notification) -> None:
        """Envoie la notification au serveur Gotify.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si la requête HTTP échoue ou si
                le serveur répond avec un statut d'erreur.
        """
        payload = json.dumps(
            {
                "title": notification.title,
                "message": notification.message,
                "priority": _GOTIFY_PRIORITIES[notification.urgency],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self._base_url}/message",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Gotify-Key": self._token,
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            raise NotificationSendError(
                f"Gotify a refusé la notification (HTTP {exc.code})"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise NotificationSendError(
                f"Serveur Gotify injoignable : {exc}"
            ) from exc
        if status != 200:
            raise NotificationSendError(
                f"Réponse Gotify inattendue (HTTP {status})"
            )
        if self._logger:
            self._logger.log_info(
                f"Notification Gotify envoyée : {notification.title}"
            )
