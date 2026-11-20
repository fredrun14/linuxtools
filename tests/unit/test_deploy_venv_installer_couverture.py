"""Tests de comportement complémentaires pour deploy.venv_installer."""

from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.venv_installer import VenvInstaller
from tests.unit.couverture_helpers import cmd_result


def test_restauration_sans_venv_en_place_copie_le_backup_sans_garde_fou() -> None:
    """Sans venv à remplacer, le backup est copié sans mv ni rm de garde-fou."""
    executor = MagicMock(spec=CommandExecutor)
    executor.run.side_effect = [
        cmd_result(success=False),  # test -d : le venv n'existe pas
        cmd_result(success=True),  # cp -a du backup
    ]

    ok = VenvInstaller(executor).restore_venv(
        Path("/opt/app/venv"), Path("/opt/app/venv.bak-1")
    )

    assert ok is True
    commandes = [c.args[0] for c in executor.run.call_args_list]
    assert commandes == [
        ["test", "-d", "/opt/app/venv"],
        ["cp", "-a", "/opt/app/venv.bak-1", "/opt/app/venv"],
    ]


def test_restauration_sans_venv_en_place_echoue_si_la_copie_echoue() -> None:
    """Sans venv à remettre en place, un échec de copie renvoie False."""
    executor = MagicMock(spec=CommandExecutor)
    executor.run.side_effect = [
        cmd_result(success=False),  # test -d : le venv n'existe pas
        cmd_result(success=False),  # cp -a échoue
    ]

    ok = VenvInstaller(executor).restore_venv(
        Path("/opt/app/venv"), Path("/opt/app/venv.bak-1")
    )

    assert ok is False
    assert executor.run.call_count == 2
