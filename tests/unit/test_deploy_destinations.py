"""Tests pour le module deploy.destinations."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.destinations import (
    LocalDestination,
    RemoteDestination,
    destination_for,
)
from linuxtools.deploy.models import DeployTarget


def _result(success: bool = True, stderr: str = "") -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout="",
        stderr=stderr,
        success=success,
        duration=0.01,
    )


class TestLocalDestination:
    """Tests de LocalDestination.write (TOCTOU-safe, write_text_secure)."""

    def test_local_ecrit_le_contenu_et_les_permissions_cas_nominal(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : le fichier est écrit avec le bon contenu/mode."""
        # Arrange
        dest_path = tmp_path / "config.toml"
        destination = LocalDestination()

        # Act
        outcome = destination.write(dest_path, "clef = 1\n", 0o640)

        # Assert
        assert outcome.success is True
        assert dest_path.read_text(encoding="utf-8") == "clef = 1\n"
        assert oct(os.stat(dest_path).st_mode)[-3:] == "640"
        assert destination.label == "local"

    def test_local_sur_symlink_leve_oserror(self, tmp_path: Path) -> None:
        """Vecteur TOCTOU : dest_path est un symlink -> OSError
        (O_NOFOLLOW)."""
        # Arrange : la cible réelle est en dehors de tmp_path/dest_path
        real_target = tmp_path / "ailleurs.txt"
        real_target.write_text("original")
        dest_path = tmp_path / "config.toml"
        dest_path.symlink_to(real_target)
        destination = LocalDestination()

        # Act / Assert
        with pytest.raises(OSError):
            destination.write(dest_path, "contenu malveillant", 0o644)
        # La cible réelle n'a pas été altérée
        assert real_target.read_text(encoding="utf-8") == "original"


class TestRemoteDestination:
    """Tests de RemoteDestination.write (executor.run install -m -T)."""

    def test_remote_ecrit_via_install_cas_nominal(self) -> None:
        """Cas nominal : un seul appel `install -m <mode> -T
        /dev/stdin <dest>`, contenu par stdin."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True)]
        destination = RemoteDestination(executor)

        # Act
        outcome = destination.write(dest_path, "contenu distant", 0o640)

        # Assert
        assert outcome.success is True
        assert executor.run.call_args_list == [
            (
                (
                    [
                        "install",
                        "-m",
                        "640",
                        "-T",
                        "/dev/stdin",
                        str(dest_path),
                    ],
                ),
                {"stdin": "contenu distant"},
            ),
        ]
        assert destination.label == "distant"

    @pytest.mark.parametrize(
        "mode,expected",
        [
            (0o600, "600"),
            (0o644, "644"),
            (0o755, "755"),
            (0o400, "400"),
        ],
    )
    def test_remote_formate_le_mode_pour_install(
        self, mode: int, expected: str
    ) -> None:
        """Le mode POSIX est formaté en octal 3 chiffres pour `-m`."""
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True)]
        destination = RemoteDestination(executor)

        destination.write(Path("/tmp/x"), "x", mode)

        install_call = executor.run.call_args_list[0]
        assert install_call.args[0][2] == expected

    def test_remote_echec_install_retourne_outcome_echec(self) -> None:
        """L'échec d'`install` retourne un outcome en échec."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(
            success=False, stderr="permission denied"
        )
        destination = RemoteDestination(executor)

        # Act
        outcome = destination.write(dest_path, "contenu", 0o644)

        # Assert
        assert outcome.success is False
        assert "permission denied" in outcome.detail
        executor.run.assert_called_once()


class TestDestinationFor:
    """Tests de la fabrique destination_for."""

    def test_destination_for_retourne_local_si_cible_locale(self) -> None:
        """Cible locale (host=None) -> LocalDestination."""
        target = DeployTarget()
        executor = MagicMock(spec=CommandExecutor)

        destination = destination_for(target, executor)

        assert isinstance(destination, LocalDestination)

    def test_destination_for_retourne_remote_portant_l_executor(self) -> None:
        """Cible distante -> RemoteDestination portant l'executor fourni."""
        target = DeployTarget(host="serveur.example.com")
        executor = MagicMock(spec=CommandExecutor)

        destination = destination_for(target, executor)

        assert isinstance(destination, RemoteDestination)
        assert destination.executor is executor
