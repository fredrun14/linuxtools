"""Tests de comportement complémentaires pour le module commands."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands import AnsiCommandFormatter, LinuxCommandExecutor
from linuxtools.logging.base import Logger


class _FauxFlux:
    """Flux de sortie minimal dont ``isatty`` renvoie une valeur imposée."""

    def __init__(self, *, tty: bool) -> None:
        """Mémorise la réponse de ``isatty``."""
        self._tty = tty

    def isatty(self) -> bool:
        """Indique si le flux se prétend un terminal."""
        return self._tty


def test_le_formateur_ansi_detecte_un_terminal_interactif(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le formateur ANSI se déclare TTY quand stdout en est un."""
    monkeypatch.setattr(sys, "stdout", _FauxFlux(tty=True))
    assert AnsiCommandFormatter()._is_tty() is True


def test_le_formateur_ansi_ne_detecte_pas_de_terminal_sur_une_redirection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le formateur ANSI ne se déclare pas TTY quand stdout est redirigé."""
    monkeypatch.setattr(sys, "stdout", _FauxFlux(tty=False))
    assert AnsiCommandFormatter()._is_tty() is False


@patch("linuxtools.commands.runner.subprocess.Popen")
def test_ctrl_c_tue_le_process_qui_ne_termine_pas_apres_terminate(
    mock_popen: MagicMock,
) -> None:
    """Sur Ctrl-C, un process sourd à terminate() est tué, l'interruption remonte."""
    proc = MagicMock()
    proc.__enter__.return_value = proc
    proc.__exit__.return_value = False
    proc.communicate.side_effect = KeyboardInterrupt()
    proc.wait.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=5)
    mock_popen.return_value = proc
    executor = LinuxCommandExecutor(logger=MagicMock(spec=Logger))

    with pytest.raises(KeyboardInterrupt):
        executor.run(["sleep", "100"])

    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


@patch("linuxtools.commands.runner.subprocess.Popen")
def test_run_streaming_commande_introuvable_renvoie_un_echec(
    mock_popen: MagicMock,
) -> None:
    """Une erreur système au lancement donne un résultat en échec, loggé."""
    mock_popen.side_effect = FileNotFoundError("inexistant")
    logger = MagicMock(spec=Logger)
    executor = LinuxCommandExecutor(logger=logger)

    result = executor.run_streaming(["inexistant"])

    assert result.success is False
    assert result.return_code == -1
    assert "inexistant" in result.stderr
    logger.log_error.assert_called_once()
