"""Tests pour linuxtools.identity.group."""

from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands import LinuxCommandExecutor
from linuxtools.errors import CommandExecutionError
from linuxtools.identity.group import LinuxGroupManager
from linuxtools.logging.base import Logger


def _result_ok() -> MagicMock:
    r = MagicMock()
    r.success = True
    r.return_code = 0
    return r


def _result_fail(code: int = 1) -> MagicMock:
    r = MagicMock()
    r.success = False
    r.return_code = code
    return r


@pytest.fixture
def executor() -> MagicMock:
    mock = MagicMock(spec=LinuxCommandExecutor)
    mock.run.return_value = _result_ok()
    return mock


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock(spec=Logger)


@pytest.fixture
def manager(executor: MagicMock, logger: MagicMock) -> LinuxGroupManager:
    return LinuxGroupManager(logger=logger, executor=executor)


class TestLinuxGroupManagerEnsureGroup:
    """Tests pour LinuxGroupManager.ensure_group."""

    def test_ensure_group_correct_gid_skips(
        self,
        manager: LinuxGroupManager,
        executor: MagicMock,
    ) -> None:
        """GID correct → aucun appel executor."""
        # Arrange
        mock_grp = MagicMock()
        mock_grp.gr_gid = 1042

        # Act
        with patch(
            "linuxtools.identity.group.grp.getgrnam",
            return_value=mock_grp,
        ):
            manager.ensure_group("partage-lan", 1042)

        # Assert
        executor.run.assert_not_called()

    def test_ensure_group_wrong_gid_calls_groupmod(
        self,
        manager: LinuxGroupManager,
        executor: MagicMock,
    ) -> None:
        """GID incorrect → groupmod --gid."""
        # Arrange
        mock_grp = MagicMock()
        mock_grp.gr_gid = 9999

        # Act
        with patch(
            "linuxtools.identity.group.grp.getgrnam",
            return_value=mock_grp,
        ):
            manager.ensure_group("partage-lan", 1042)

        # Assert
        executor.run.assert_called_once()
        cmd = executor.run.call_args[0][0]
        assert cmd[0] == "groupmod"
        assert "--gid" in cmd
        assert "1042" in cmd
        assert "partage-lan" in cmd

    def test_ensure_group_missing_calls_groupadd(
        self,
        manager: LinuxGroupManager,
        executor: MagicMock,
    ) -> None:
        """Groupe absent → groupadd --gid."""
        # Act
        with patch(
            "linuxtools.identity.group.grp.getgrnam",
            side_effect=KeyError("partage-lan"),
        ):
            manager.ensure_group("partage-lan", 1042)

        # Assert
        executor.run.assert_called_once()
        cmd = executor.run.call_args[0][0]
        assert cmd[0] == "groupadd"
        assert "--gid" in cmd
        assert "1042" in cmd
        assert "partage-lan" in cmd

    def test_ensure_group_groupmod_echec_leve_exception(
        self,
        manager: LinuxGroupManager,
        executor: MagicMock,
    ) -> None:
        """groupmod code non nul → CommandExecutionError."""
        # Arrange
        mock_grp = MagicMock()
        mock_grp.gr_gid = 9999
        executor.run.return_value = _result_fail(4)

        # Act / Assert
        with patch(
            "linuxtools.identity.group.grp.getgrnam",
            return_value=mock_grp,
        ):
            with pytest.raises(CommandExecutionError, match="groupmod"):
                manager.ensure_group("partage-lan", 1042)

    def test_ensure_group_groupadd_echec_leve_exception(
        self,
        manager: LinuxGroupManager,
        executor: MagicMock,
    ) -> None:
        """groupadd code non nul → CommandExecutionError."""
        # Arrange
        executor.run.return_value = _result_fail(9)

        # Act / Assert
        with patch(
            "linuxtools.identity.group.grp.getgrnam",
            side_effect=KeyError("partage-lan"),
        ):
            with pytest.raises(CommandExecutionError, match="groupadd"):
                manager.ensure_group("partage-lan", 1042)


class TestLinuxGroupManagerValidation:
    """Tests de validation des noms Unix."""

    def test_nom_tiret_initial_leve_valueerror(
        self,
        manager: LinuxGroupManager,
    ) -> None:
        """ensure_group lève ValueError si le nom commence par '-'."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_group("-malicieux", 1042)

    def test_nom_espace_leve_valueerror(
        self,
        manager: LinuxGroupManager,
    ) -> None:
        """ensure_group lève ValueError si le nom contient un espace."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_group("mon groupe", 1042)

    def test_nom_majuscule_leve_valueerror(
        self,
        manager: LinuxGroupManager,
    ) -> None:
        """ensure_group lève ValueError si le nom contient une majuscule."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_group("MonGroupe", 1042)

    def test_nom_valide_ne_leve_pas(
        self,
        manager: LinuxGroupManager,
        executor: MagicMock,
    ) -> None:
        """Nom Unix valide (tiret interne, underscore) passe la validation."""
        with patch(
            "linuxtools.identity.group.grp.getgrnam",
            side_effect=KeyError("partage-lan"),
        ):
            manager.ensure_group("partage-lan_2", 1042)
        executor.run.assert_called_once()
