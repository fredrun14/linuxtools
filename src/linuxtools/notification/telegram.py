"""Notifier Telegram multi-destinataires.

Envoie chaque notification à N chats Telegram via un même bot
(POST /bot<token>/sendMessage), en stdlib uniquement.

Exemple d'usage : le token est chargé via ``CredentialManager`` (jamais
en dur), les ``chat_id`` viennent de la configuration::

    from pathlib import Path

    from linuxtools import CredentialManager
    from linuxtools.notification import Notification, TelegramNotifier

    manager = CredentialManager.from_dotenv(
        service="backup-nas",
        dotenv_path=Path("config/.env"),
    )
    notifier = TelegramNotifier(
        token=manager.require("TELEGRAM_BOT_TOKEN"),
        recipients={"alice": 111111111, "bob": 222222222},
    )
    notifier.send(Notification(title="✗ backup-nas — échec", message="..."))

Prérequis : chaque destinataire doit avoir DÉMARRÉ le bot (bouton
« Démarrer » ou commande /start). Un bot ne peut pas écrire le premier :
sans cela, Telegram répond 403 (bot bloqué ou jamais démarré) ou 400
(chat introuvable).

Confidentialité : par défaut (``include_message=False``), seul le titre
de la notification part chez Telegram ; le détail (machine, chemins,
messages d'erreur) reste sur les autres canaux. Le détail ne part chez
ce tiers qu'avec ``include_message=True``, et les messages d'un bot ne
sont pas chiffrés de bout en bout.

Comportement : les envois sont séquentiels (durée maximale d'un
``send`` : N destinataires × ``timeout``, hors résolution DNS), sans
aucun nouvel essai (un 429 est signalé comme les autres échecs). Si au
moins un destinataire échoue, les autres sont tout de même servis, puis
une seule ``NotificationSendError`` agrégée est levée ; elle ne cite que
les libellés et des raisons fixes, jamais le token, l'URL ni le
``chat_id``.
"""

import http.client
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from itertools import accumulate
from typing import Any

from linuxtools.logging.base import Logger
from linuxtools.notification.base import Notifier
from linuxtools.notification.exceptions import NotificationSendError
from linuxtools.notification.models import Notification

_MAX_UNITS = 4096
_ELLIPSIS = "…"
_HTTP_REASONS: dict[int, str] = {
    400: "requête refusée (chat introuvable ou bot jamais démarré ?)",
    401: "token invalide",
    403: "bot bloqué ou jamais démarré par le destinataire",
    404: "token ou méthode inconnus",
    429: "trop de messages (limite de débit)",
}
# Au-delà, socket.settimeout peut lever OverflowError (hors contrat de
# send) : 3600 s dépasse tout usage de notification.
_MAX_TIMEOUT = 3600.0
_API_BASE = "https://api.telegram.org"
_LABEL_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")
_TOKEN_PATTERN = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")


def _utf16_units(text: str) -> int:
    """Compte les unités UTF-16 d'un texte (unité de la limite).

    Args:
        text: Texte à mesurer.

    Returns:
        Nombre d'unités UTF-16 (une paire de substitution en vaut 2,
        un substitut isolé en vaut 1 : il ne lève aucune exception).
    """
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _is_valid_chat_id(value: object) -> bool:
    """Indique si la valeur est un chat_id acceptable.

    Args:
        value: Valeur à contrôler (le typage n'est pas fiable à
            l'exécution).

    Returns:
        True pour un entier non nul qui n'est pas un booléen.
    """
    return (
        isinstance(value, int) and not isinstance(value, bool) and value != 0
    )


def _is_valid_timeout(value: object) -> bool:
    """Indique si la valeur est un timeout acceptable.

    Args:
        value: Valeur à contrôler (le typage n'est pas fiable à
            l'exécution).

    Returns:
        True pour un int ou float non booléen dans ]0, 3600] ; NaN et
        l'infini sont rejetés par la comparaison.
    """
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and 0 < value <= _MAX_TIMEOUT
    )


def _truncate(text: str) -> str:
    """Borne le texte à 4096 unités UTF-16, suffixe « … » compris.

    La troncature se fait caractère par caractère : une paire de
    substitution n'est jamais coupée en deux. Un substitut isolé
    (`surrogateescape`) est toléré et compté pour 1 unité.

    Args:
        text: Texte à borner.

    Returns:
        Le texte inchangé s'il tient, sinon sa version tronquée.
    """
    if _utf16_units(text) <= _MAX_UNITS:
        return text
    budget = _MAX_UNITS - _utf16_units(_ELLIPSIS)
    totals = accumulate(_utf16_units(char) for char in text)
    # Le texte dépasse la limite : un caractère franchit forcément le
    # budget, next() ne peut donc pas épuiser le générateur.
    cut = next(i for i, total in enumerate(totals) if total > budget)
    return text[:cut] + _ELLIPSIS


class TelegramNotifier(Notifier):
    """Envoie les notifications à N chats Telegram via un même bot.

    Chaque destinataire est identifié par un libellé (utilisé dans les
    logs et les erreurs) et un ``chat_id`` entier. Il doit avoir démarré
    le bot au préalable (/start), sinon son envoi échoue en 403 ou 400.

    Par défaut seul le titre est envoyé (``include_message=False``) ;
    ``include_message=True`` ajoute le détail, qui transite alors en
    clair (non chiffré de bout en bout) par un tiers. Les envois sont
    séquentiels et sans nouvel essai ; les échecs sont isolés par
    destinataire puis agrégés dans une seule ``NotificationSendError``
    qui ne contient ni token, ni URL, ni ``chat_id``. Le token reste dans
    un attribut privé : ``repr()`` ne l'expose pas.

    Exemple :
        >>> notifier = TelegramNotifier(  # doctest: +SKIP
        ...     token=manager.require("TELEGRAM_BOT_TOKEN"),
        ...     recipients={"alice": 111111111},
        ... )
    """

    def __init__(
        self,
        token: str,
        recipients: Mapping[str, int],
        timeout: float = 10.0,
        include_message: bool = False,
        opener: Callable[..., Any] | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le notifier.

        Args:
            token: Token du bot.
            recipients: Libellé vers chat_id.
            timeout: Délai HTTP par destinataire, en secondes, dans
                ]0, 3600] (int ou float, pas un booléen).
            include_message: Joindre le détail au titre (un vrai
                booléen : "false" ou 0 d'un .env sont refusés).
            opener: Remplaçant injectable de urlopen.
            logger: Logger optionnel.

        Raises:
            ValueError: Si un paramètre est invalide (dont un timeout
                non numérique, booléen, ≤ 0, NaN, infini ou > 3600, ou un
                include_message qui n'est pas un bool).
        """
        if not _TOKEN_PATTERN.fullmatch(token):
            raise ValueError("token invalide")
        if not recipients:
            raise ValueError("au moins un destinataire est requis")
        for label in recipients:
            if not _LABEL_PATTERN.fullmatch(label):
                raise ValueError("libellé invalide")
        seen: set[int] = set()
        for label, chat_id in recipients.items():
            if not _is_valid_chat_id(chat_id):
                raise ValueError(f"chat_id invalide pour {label}")
            if chat_id in seen:
                raise ValueError("chat_id en double")
            seen.add(chat_id)
        if not _is_valid_timeout(timeout):
            raise ValueError("timeout doit être dans ]0, 3600] secondes")
        if not isinstance(include_message, bool):
            raise ValueError("include_message doit être un booléen")
        self._token = token
        self._recipients = dict(recipients)
        self._timeout = timeout
        self._include_message = include_message
        self._opener = opener or urllib.request.urlopen
        self._logger = logger

    def _send_one(self, chat_id: int, text: str) -> str | None:
        """Envoie le texte à un chat et classe l'échec éventuel.

        Ne reprend jamais le texte des exceptions : l'URL (donc le
        token) peut y figurer.

        Args:
            chat_id: Identifiant du chat destinataire.
            text: Texte déjà borné à envoyer.

        Returns:
            None en cas de succès, sinon une raison fixe d'échec.
        """
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=f"{_API_BASE}/bot{self._token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            exc.close()
            return _HTTP_REASONS.get(exc.code, f"HTTP {exc.code}")
        except urllib.error.URLError as exc:
            return f"serveur injoignable ({type(exc.reason).__name__})"
        except http.client.HTTPException:
            return "réponse invalide"
        except OSError as exc:
            return f"erreur réseau ({type(exc).__name__})"
        if status != 200:
            return f"réponse inattendue (HTTP {status})"
        return None

    def send(self, notification: Notification) -> None:
        """Envoie la notification à tous les destinataires.

        Chaque destinataire est tenté, sans nouvel essai, même si un
        précédent a échoué.

        Args:
            notification: La notification à envoyer.

        Raises:
            NotificationSendError: Si au moins un envoi échoue. Le
                message ne cite que les libellés et des raisons fixes.
        """
        text = notification.title
        if self._include_message:
            text = f"{text}\n\n{notification.message}"
        text = _truncate(text)
        failures: list[str] = []
        for label, chat_id in self._recipients.items():
            reason = self._send_one(chat_id, text)
            if reason is None:
                if self._logger:
                    self._logger.log_info(f"Telegram : envoyé à {label}")
            else:
                failures.append(f"{label} ({reason})")
                if self._logger:
                    self._logger.log_warning(
                        f"Telegram : échec pour {label} ({reason})"
                    )
        if failures:
            raise NotificationSendError(
                "Échec Telegram : " + ", ".join(failures)
            )
