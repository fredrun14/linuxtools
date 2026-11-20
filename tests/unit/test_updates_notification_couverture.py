"""Tests de comportement complémentaires : updates.checker et notification."""

import smtplib
import urllib.request
from collections.abc import Callable
from typing import Literal, Self
from unittest.mock import MagicMock

import pytest
from webapitools.apps.forgejo import ForgejoClient
from webapitools.core.exceptions import ApiError

from linuxtools.logging.base import Logger
from linuxtools.notification import (
    DesktopNotifier,
    GotifyNotifier,
    Notification,
    NotificationSendError,
    SmtpEmailNotifier,
)
from linuxtools.updates.checker import check_for_update
from tests.unit.couverture_helpers import cmd_result

# --- updates.checker ---


@pytest.fixture
def version_installee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixe la version installée du paquet testé à 1.0.0."""
    monkeypatch.setattr("linuxtools.updates.checker.version", lambda _p: "1.0.0")


def test_forgejo_injoignable_sans_logger_renvoie_un_resultat_non_verifie(
    version_installee: None,
) -> None:
    """Sans logger, une API injoignable donne un résultat non vérifié."""
    client = MagicMock(spec=ForgejoClient)
    client.get_latest_release.side_effect = ApiError("timeout")

    resultat = check_for_update("outil", "fred", "outil", client)

    assert resultat.checked is False
    assert "injoignable" in resultat.detail


def test_aucune_release_est_journalisee(version_installee: None) -> None:
    """Sans release publiée, l'absence est tracée en avertissement."""
    client = MagicMock(spec=ForgejoClient)
    client.get_latest_release.return_value = None
    logger = MagicMock(spec=Logger)

    resultat = check_for_update("outil", "fred", "outil", client, logger=logger)

    assert resultat.checked is False
    logger.log_warning.assert_called_once_with(resultat.detail)


def test_version_distante_illisible_est_journalisee(version_installee: None) -> None:
    """Une étiquette de version inconnue est tracée en avertissement."""
    client = MagicMock(spec=ForgejoClient)
    client.get_latest_release.return_value = {"tag_name": "pas-une-version"}
    logger = MagicMock(spec=Logger)

    resultat = check_for_update("outil", "fred", "outil", client, logger=logger)

    assert resultat.checked is False
    assert "format de version non reconnu" in resultat.detail
    logger.log_warning.assert_called_once_with(resultat.detail)


# --- DesktopNotifier ---


NOTIF = Notification(title="T", message="M")


def _sessions_ouvertes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fait croire que chaque bus D-Bus utilisateur existe."""
    monkeypatch.setattr(
        "linuxtools.notification.desktop.Path.is_socket", lambda _self: True
    )


def test_desktop_loginctl_en_echec_leve_une_erreur(executeur: MagicMock) -> None:
    """Un échec de loginctl est remonté en NotificationSendError."""
    executeur.run.side_effect = [cmd_result(success=False, stderr="pas de loginctl")]
    notifier = DesktopNotifier("app", all_users=True, executor=executeur)

    with pytest.raises(NotificationSendError, match="loginctl a échoué"):
        notifier.send(NOTIF)


def test_desktop_ignore_les_lignes_loginctl_incompletes(
    executeur: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une ligne loginctl à un seul champ est ignorée, pas de runuser pour elle."""
    _sessions_ouvertes(monkeypatch)
    executeur.run.side_effect = [
        cmd_result(stdout="1000\n1001 alice\n"),
        cmd_result(),
    ]
    notifier = DesktopNotifier("app", all_users=True, executor=executeur)

    notifier.send(NOTIF)

    commandes = [c.args[0] for c in executeur.run.call_args_list]
    assert [c[2] for c in commandes if c[0] == "runuser"] == ["alice"]


def test_desktop_refus_d_un_utilisateur_sans_logger_n_empeche_pas_la_diffusion(
    executeur: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans logger, le refus d'un utilisateur ne bloque pas les suivants."""
    _sessions_ouvertes(monkeypatch)
    executeur.run.side_effect = [
        cmd_result(stdout="1000 fred\n1001 alice\n"),
        cmd_result(success=False, stderr="refusé"),
        cmd_result(),
    ]
    notifier = DesktopNotifier("app", all_users=True, executor=executeur)

    notifier.send(NOTIF)

    assert executeur.run.call_count == 3


def test_desktop_refus_d_un_utilisateur_est_journalise(
    executeur: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un refus pour un utilisateur est tracé ; l'autre est notifié."""
    _sessions_ouvertes(monkeypatch)
    executeur.run.side_effect = [
        cmd_result(stdout="1000 fred\n1001 alice\n"),
        cmd_result(success=False, stderr="refusé\n"),
        cmd_result(),
    ]
    logger = MagicMock(spec=Logger)
    notifier = DesktopNotifier("app", all_users=True, executor=executeur, logger=logger)

    notifier.send(NOTIF)

    logger.log_warning.assert_called_once()
    message = logger.log_warning.call_args.args[0]
    assert "fred" in message
    assert "refusé" in message


# --- SmtpEmailNotifier ---


def test_email_refuse_un_hote_vide() -> None:
    """Un hôte SMTP vide est refusé à la construction."""
    with pytest.raises(ValueError, match="host est requis"):
        SmtpEmailNotifier(host="", sender="a@b.c", recipients=["d@e.f"])


def test_email_refuse_un_expediteur_vide() -> None:
    """Un expéditeur vide est refusé à la construction."""
    with pytest.raises(ValueError, match="sender est requis"):
        SmtpEmailNotifier(host="smtp", sender="", recipients=["d@e.f"])


def test_email_envoye_est_journalise() -> None:
    """Un envoi réussi est tracé avec le titre de la notification."""
    fabrique = MagicMock()
    smtp = fabrique.return_value.__enter__.return_value
    logger = MagicMock(spec=Logger)
    notifier = SmtpEmailNotifier(
        host="smtp",
        sender="a@b.c",
        recipients=["d@e.f"],
        use_tls=False,
        smtp_factory=fabrique,
        logger=logger,
    )

    notifier.send(NOTIF)

    smtp.send_message.assert_called_once()
    logger.log_info.assert_called_once_with("Notification email envoyée : T")


def test_email_smtp_en_erreur_leve_notification_send_error() -> None:
    """Une erreur SMTP est convertie en NotificationSendError."""
    fabrique = MagicMock()
    fabrique.return_value.__enter__.return_value.send_message.side_effect = (
        smtplib.SMTPException("boum")
    )
    notifier = SmtpEmailNotifier(
        host="smtp",
        sender="a@b.c",
        recipients=["d@e.f"],
        use_tls=False,
        smtp_factory=fabrique,
    )

    with pytest.raises(NotificationSendError, match="boum"):
        notifier.send(NOTIF)


# --- GotifyNotifier ---


class _Reponse:
    """Réponse HTTP factice, utilisable comme gestionnaire de contexte."""

    def __init__(self, status: int) -> None:
        """Mémorise le statut HTTP."""
        self.status = status

    def __enter__(self) -> Self:
        """Retourne la réponse."""
        return self

    def __exit__(self, *args: object) -> Literal[False]:
        """Ne supprime aucune exception."""
        return False


def _opener(status: int) -> Callable[..., _Reponse]:
    """Fabrique un opener qui répond toujours avec ce statut."""

    def _ouvre(_requete: urllib.request.Request, timeout: float = 0) -> _Reponse:
        return _Reponse(status)

    return _ouvre


def test_gotify_statut_inattendu_leve_une_erreur() -> None:
    """Un statut 2xx autre que 200 est traité comme une réponse inattendue."""
    notifier = GotifyNotifier("https://nas", "token", opener=_opener(204))

    with pytest.raises(NotificationSendError, match="HTTP 204"):
        notifier.send(NOTIF)


def test_gotify_envoi_reussi_est_journalise() -> None:
    """Un envoi réussi est tracé avec le titre de la notification."""
    logger = MagicMock(spec=Logger)
    notifier = GotifyNotifier(
        "https://nas", "token", opener=_opener(200), logger=logger
    )

    notifier.send(NOTIF)

    logger.log_info.assert_called_once_with("Notification Gotify envoyée : T")
