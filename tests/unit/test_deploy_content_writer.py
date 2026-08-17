"""Tests pour le module deploy.content_writer."""

import os
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.content_writer import deposit_content


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


class TestDepositContentLocal:
    """Tests du dépôt local (TOCTOU-safe, write_text_secure)."""

    def test_depot_local_nominal_ecrit_le_contenu_et_les_permissions(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : le fichier est écrit avec le bon contenu/mode."""
        # Arrange
        dest_path = tmp_path / "config.toml"
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        # Act
        result = deposit_content(
            executor,
            "clef = 1\n",
            dest_path,
            0o640,
            is_remote=False,
            logger=logger,
        )

        # Assert
        assert result is True
        assert dest_path.read_text(encoding="utf-8") == "clef = 1\n"
        assert oct(os.stat(dest_path).st_mode)[-3:] == "640"
        executor.run.assert_not_called()
        logger.log_info.assert_called_once()
        assert str(dest_path) in logger.log_info.call_args.args[0]

    def test_depot_local_sans_logger_ne_leve_pas(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : logger=None n'entraîne aucune exception."""
        dest_path = tmp_path / "config.toml"
        executor = MagicMock(spec=CommandExecutor)

        result = deposit_content(
            executor,
            "contenu",
            dest_path,
            0o644,
            is_remote=False,
            logger=None,
        )

        assert result is True
        assert dest_path.read_text(encoding="utf-8") == "contenu"

    def test_depot_local_sur_symlink_leve_oserror(
        self, tmp_path: Path
    ) -> None:
        """Vecteur TOCTOU : dest_path est un symlink -> OSError (O_NOFOLLOW)."""
        # Arrange : la cible réelle est en dehors de tmp_path/dest_path
        real_target = tmp_path / "ailleurs.txt"
        real_target.write_text("original")
        dest_path = tmp_path / "config.toml"
        dest_path.symlink_to(real_target)
        executor = MagicMock(spec=CommandExecutor)

        # Act / Assert
        with pytest.raises(OSError):
            deposit_content(
                executor,
                "contenu malveillant",
                dest_path,
                0o644,
                is_remote=False,
                logger=None,
            )
        # La cible réelle n'a pas été altérée
        assert real_target.read_text(encoding="utf-8") == "original"


class TestDepositContentRemote:
    """Tests du dépôt distant (executor.run tee + chmod)."""

    def test_depot_distant_nominal_ecrit_puis_chmod(self) -> None:
        """Cas nominal : tee puis chmod réussissent."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(success=True), _result(success=True)]
        logger = MagicMock()

        # Act
        result = deposit_content(
            executor,
            "contenu distant",
            dest_path,
            0o640,
            is_remote=True,
            logger=logger,
        )

        # Assert
        assert result is True
        assert executor.run.call_args_list == [
            call(["tee", str(dest_path)], stdin="contenu distant"),
            call(["chmod", "640", str(dest_path)]),
        ]
        logger.log_info.assert_called_once()
        assert str(dest_path) in logger.log_info.call_args.args[0]

    @pytest.mark.parametrize(
        "mode,expected",
        [
            (0o600, "600"),
            (0o644, "644"),
            (0o400, "400"),
        ],
    )
    def test_depot_distant_formate_le_mode_chmod(
        self, mode: int, expected: str
    ) -> None:
        """Le mode POSIX est formaté en octal 3 chiffres pour chmod."""
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(success=True), _result(success=True)]

        deposit_content(
            executor,
            "x",
            Path("/tmp/x"),
            mode,
            is_remote=True,
            logger=None,
        )

        chmod_call = executor.run.call_args_list[1]
        assert chmod_call.args[0][1] == expected

    def test_depot_distant_echec_tee_retourne_false_et_logue(self) -> None:
        """L'échec de tee arrête avant tout chmod."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(
            success=False, stderr="permission denied"
        )
        logger = MagicMock()

        # Act
        result = deposit_content(
            executor,
            "contenu",
            dest_path,
            0o644,
            is_remote=True,
            logger=logger,
        )

        # Assert
        assert result is False
        executor.run.assert_called_once()
        logger.log_error.assert_called_once()
        assert "permission denied" in logger.log_error.call_args.args[0]

    def test_depot_distant_echec_chmod_retourne_false_et_logue(self) -> None:
        """tee réussit mais chmod échoue -> False, message loggé."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [
            _result(success=True),
            _result(success=False, stderr="chmod: not permitted"),
        ]
        logger = MagicMock()

        # Act
        result = deposit_content(
            executor,
            "contenu",
            dest_path,
            0o644,
            is_remote=True,
            logger=logger,
        )

        # Assert
        assert result is False
        assert executor.run.call_count == 2
        logger.log_error.assert_called_once()
        assert "chmod: not permitted" in logger.log_error.call_args.args[0]

    def test_depot_distant_sans_logger_ne_leve_pas_en_cas_d_echec_tee(
        self,
    ) -> None:
        """Cas limite : échec du tee distant sans logger n'entraîne
        aucune exception."""
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(success=False, stderr="boom")

        result = deposit_content(
            executor,
            "contenu",
            Path("/tmp/x"),
            0o644,
            is_remote=True,
            logger=None,
        )

        assert result is False

    def test_depot_distant_sans_logger_ne_leve_pas_en_cas_d_echec_chmod(
        self,
    ) -> None:
        """Cas limite : échec du chmod distant sans logger n'entraîne
        aucune exception (tee réussi, chmod en échec)."""
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [
            _result(success=True),
            _result(success=False, stderr="chmod boom"),
        ]

        result = deposit_content(
            executor,
            "contenu",
            Path("/tmp/x"),
            0o644,
            is_remote=True,
            logger=None,
        )

        assert result is False
