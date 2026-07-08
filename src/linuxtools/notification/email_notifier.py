"""Notifier email via SMTP (smtplib, stdlib).

Envoie le compte rendu par email avec STARTTLS par défaut.
Le mot de passe ne doit pas être codé en dur : le charger via
le module credentials (CredentialChain) ou une variable
d'environnement.

Example:

    from linuxtools.notification import (
        Notification,
        SmtpEmailNotifier,
    )

    notifier = SmtpEmailNotifier(
        host="smtp.example.com",
        sender="nas@example.com",
        recipients=["admin@example.com"],
        username="nas@example.com",
        password=password,  # chargé via CredentialChain
    )
    notifier.send(Notification(title="Backup", message="Terminé"))
"""

import smtplib
import ssl
from collections.abc import Callable, Sequence
from email.message import EmailMessage

from linuxtools.logging.base import Logger
from linuxtools.notification.base import Notifier
from linuxtools.notification.exceptions import NotificationSendError
from linuxtools.notification.models import Notification

SmtpFactory = Callable[..., smtplib.SMTP]


class SmtpEmailNotifier(Notifier):
    """Envoie des notifications par email via SMTP.

    Attributes:
        _host: Hôte SMTP.
        _port: Port SMTP.
        _sender: Adresse expéditeur.
        _recipients: Adresses destinataires.
        _username: Identifiant SMTP optionnel.
        _password: Mot de passe SMTP optionnel.
        _use_tls: Active STARTTLS.
        _timeout: Timeout réseau en secondes.
        _smtp_factory: Fabrique de client SMTP injectable (tests).
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        host: str,
        sender: str,
        recipients: Sequence[str],
        port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        timeout: int = 30,
        smtp_factory: SmtpFactory | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le notifier email.

        Args:
            host: Hôte SMTP (non vide).
            sender: Adresse expéditeur (non vide).
            recipients: Au moins une adresse destinataire.
            port: Port SMTP (défaut : 587).
            username: Identifiant SMTP (vide = pas d'auth).
            password: Mot de passe SMTP.
            use_tls: Si True, négocie STARTTLS avant l'envoi.
            timeout: Timeout réseau en secondes.
            smtp_factory: Remplaçant injectable de smtplib.SMTP.
            logger: Logger optionnel.

        Raises:
            ValueError: Si host ou sender est vide, ou si
                recipients est vide.
        """
        if not host:
            raise ValueError("host est requis")
        if not sender:
            raise ValueError("sender est requis")
        if not recipients:
            raise ValueError("au moins un destinataire est requis")
        self._host = host
        self._port = port
        self._sender = sender
        self._recipients = list(recipients)
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout = timeout
        self._smtp_factory = smtp_factory or smtplib.SMTP
        self._logger = logger

    def send(self, notification: Notification) -> None:
        """Envoie la notification par email.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si la connexion, l'authentification
                ou l'envoi SMTP échoue.
        """
        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message.set_content(notification.message)
        try:
            with self._smtp_factory(
                self._host, self._port, timeout=self._timeout
            ) as smtp:
                if self._use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationSendError(
                f"Envoi email échoué via {self._host} : {exc}"
            ) from exc
        if self._logger:
            self._logger.log_info(
                f"Notification email envoyée : {notification.title}"
            )
