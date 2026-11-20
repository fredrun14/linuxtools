"""Tests de comportement complémentaires pour le module logging."""

import io
import logging
from pathlib import Path

import pytest

from linuxtools.logging import RotatingFileLogger, TeeStream, build_logger
from linuxtools.logging.base import Logger


class _LoggerMinimal(Logger):
    """Logger concret qui mémorise les messages reçus."""

    def __init__(self) -> None:
        """Initialise la liste des messages d'information."""
        self.infos: list[str] = []

    def log_info(self, message: str) -> None:
        """Mémorise un message d'information."""
        self.infos.append(message)

    def log_warning(self, message: str) -> None:
        """Ignore les avertissements."""

    def log_error(self, message: str) -> None:
        """Ignore les erreurs."""


def test_log_success_par_defaut_delegue_a_log_info() -> None:
    """Un logger qui ne redéfinit pas log_success reçoit un message d'info."""
    logger = _LoggerMinimal()

    logger.log_success("ok")

    assert logger.infos == ["ok"]


def test_build_logger_fichier_applique_le_format_demande(tmp_path: Path) -> None:
    """Le format fourni dans la config se retrouve dans le fichier de log."""
    fichier = tmp_path / "app.log"
    logger = build_logger(
        {"type": "file", "file": str(fichier), "format": "MARQUE %(message)s"}
    )

    logger.log_info("bonjour")

    assert "MARQUE bonjour" in fichier.read_text(encoding="utf-8")


@pytest.mark.parametrize("coloree", [False, True])
def test_rotating_logger_ecrit_aussi_sur_la_console(
    tmp_path: Path, *, coloree: bool
) -> None:
    """Avec console_output, le message va au fichier et à la console."""
    fichier = tmp_path / f"rot-{coloree}.log"
    flux = io.StringIO()
    logger = RotatingFileLogger(fichier, console_output=True, colored_console=coloree)
    console = logger.logger.handlers[1]
    assert isinstance(console, logging.StreamHandler)
    console.setStream(flux)

    logger.log_info("bonjour")

    assert "bonjour" in fichier.read_text(encoding="utf-8")
    assert "bonjour" in flux.getvalue()
    logger.logger.handlers.clear()


def test_tee_close_ignore_un_fichier_deja_ferme(tmp_path: Path) -> None:
    """Fermer un tee dont le fichier est déjà fermé ne lève rien."""
    with (tmp_path / "tee.log").open("w", encoding="utf-8") as log_fh:
        tee = TeeStream(io.StringIO(), log_fh)
    assert log_fh.closed

    tee.close()


def test_rotating_logger_reutilise_le_handler_d_un_logger_existant(
    tmp_path: Path,
) -> None:
    """Deux instances sur le même fichier partagent le même handler."""
    fichier = tmp_path / "partage.log"
    premier = RotatingFileLogger(fichier)
    second = RotatingFileLogger(fichier)

    second.log_info("bonjour")

    assert second.handler is premier.handler
    assert "bonjour" in fichier.read_text(encoding="utf-8")
    premier.logger.handlers.clear()
