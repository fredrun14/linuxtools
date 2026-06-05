"""Tests pour linux_python_utils.identity.user."""

from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.commands import LinuxCommandExecutor
from linux_python_utils.identity.user import LinuxUserManager
from linux_python_utils.logging.base import Logger


@pytest.fixture
def executor() -> MagicMock:
    return MagicMock(spec=LinuxCommandExecutor)


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock(spec=Logger)


@pytest.fixture
def manager(executor: MagicMock, logger: MagicMock) -> LinuxUserManager:
    return LinuxUserManager(executor, logger)


class TestLinuxUserManagerEnsureUser:
    """Tests pour LinuxUserManager.ensure_user."""

    def test_ensure_user_correct_uid_skips(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """UID correct → aucun appel executor."""
        # Arrange
        mock_pwd = MagicMock()
        mock_pwd.pw_uid = 1000

        # Act
        with patch(
            "linux_python_utils.identity.user.pwd.getpwnam",
            return_value=mock_pwd,
        ):
            manager.ensure_user("frederic", 1000, "/bin/zsh", "Frédéric", True)

        # Assert
        executor.run.assert_not_called()

    def test_ensure_user_wrong_uid_calls_usermod_uid(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """UID incorrect → usermod --uid."""
        # Arrange
        mock_pwd = MagicMock()
        mock_pwd.pw_uid = 9999

        # Act
        with patch(
            "linux_python_utils.identity.user.pwd.getpwnam",
            return_value=mock_pwd,
        ):
            manager.ensure_user("frederic", 1000, "/bin/zsh", "Frédéric", True)

        # Assert
        executor.run.assert_called_once()
        cmd = executor.run.call_args[0][0]
        assert cmd[0] == "usermod"
        assert "--uid" in cmd
        assert "1000" in cmd
        assert "frederic" in cmd

    def test_ensure_user_missing_calls_useradd(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """Utilisateur absent → useradd."""
        # Act
        with patch(
            "linux_python_utils.identity.user.pwd.getpwnam",
            side_effect=KeyError("frederic"),
        ):
            manager.ensure_user("frederic", 1000, "/bin/zsh", "Frédéric", False)

        # Assert
        executor.run.assert_called_once()
        cmd = executor.run.call_args[0][0]
        assert cmd[0] == "useradd"
        assert "--uid" in cmd
        assert "1000" in cmd
        assert "--shell" in cmd
        assert "/bin/zsh" in cmd
        assert "--comment" in cmd
        assert "Frédéric" in cmd
        assert "frederic" in cmd

    def test_ensure_user_create_home_flag(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """create_home=True → --create-home présent dans useradd."""
        # Act
        with patch(
            "linux_python_utils.identity.user.pwd.getpwnam",
            side_effect=KeyError("frederic"),
        ):
            manager.ensure_user("frederic", 1000, "/bin/zsh", "Frédéric", True)

        # Assert
        cmd = executor.run.call_args[0][0]
        assert "--create-home" in cmd


class TestLinuxUserManagerEnsureUserGroups:
    """Tests pour LinuxUserManager.ensure_user_groups."""

    def test_ensure_user_groups_all_present_skips(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """Tous les groupes déjà présents → aucun appel executor."""
        # Arrange
        mock_grp = MagicMock()
        mock_grp.gr_mem = ["frederic"]

        # Act
        with patch(
            "linux_python_utils.identity.user.grp.getgrnam",
            return_value=mock_grp,
        ):
            manager.ensure_user_groups("frederic", ["partage-lan"])

        # Assert
        executor.run.assert_not_called()

    def test_ensure_user_groups_missing_calls_usermod_append(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """Groupes manquants → usermod --append --groups batché."""
        # Arrange
        mock_grp = MagicMock()
        mock_grp.gr_mem = []

        # Act
        with patch(
            "linux_python_utils.identity.user.grp.getgrnam",
            return_value=mock_grp,
        ):
            manager.ensure_user_groups("frederic", ["partage-lan", "audio"])

        # Assert
        executor.run.assert_called_once()
        cmd = executor.run.call_args[0][0]
        assert cmd[0] == "usermod"
        assert "--append" in cmd
        assert "--groups" in cmd
        groups_idx = cmd.index("--groups") + 1
        assert "partage-lan" in cmd[groups_idx]
        assert "audio" in cmd[groups_idx]
        assert "frederic" in cmd

    def test_ensure_user_groups_unknown_group_logs_warning(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
        logger: MagicMock,
    ) -> None:
        """Groupe inconnu → warning loggé, pas de crash, pas d'appel executor."""
        # Act
        with patch(
            "linux_python_utils.identity.user.grp.getgrnam",
            side_effect=KeyError("unknown-group"),
        ):
            manager.ensure_user_groups("frederic", ["unknown-group"])

        # Assert
        executor.run.assert_not_called()
        logger.log_warning.assert_called_once()

    def test_ensure_user_groups_tous_absents_aucun_appel_executor(
        self,
        manager: LinuxUserManager,
        executor: MagicMock,
    ) -> None:
        """Tous les groupes absents → aucun appel executor (best-effort)."""
        # Act
        with patch(
            "linux_python_utils.identity.user.grp.getgrnam",
            side_effect=KeyError("group"),
        ):
            manager.ensure_user_groups("frederic", ["absent1", "absent2"])

        # Assert
        executor.run.assert_not_called()


class TestLinuxUserManagerValidation:
    """Tests de validation des noms Unix."""

    def test_ensure_user_nom_tiret_initial_leve_valueerror(
        self,
        manager: LinuxUserManager,
    ) -> None:
        """ensure_user lève ValueError si le nom commence par '-'."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_user(
                "-malicieux", 1000, "/bin/bash", "X", False
            )

    def test_ensure_user_nom_majuscule_leve_valueerror(
        self,
        manager: LinuxUserManager,
    ) -> None:
        """ensure_user lève ValueError si le nom contient des majuscules."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_user(
                "Majuscule", 1000, "/bin/bash", "X", False
            )

    def test_ensure_user_groups_username_invalide_leve_valueerror(
        self,
        manager: LinuxUserManager,
    ) -> None:
        """ensure_user_groups lève ValueError si le username commence par '-'."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_user_groups("-malicieux", ["audio"])

    def test_ensure_user_groups_group_invalide_leve_valueerror(
        self,
        manager: LinuxUserManager,
    ) -> None:
        """ensure_user_groups lève ValueError si un nom de groupe est invalide."""
        with pytest.raises(ValueError, match="Nom Unix invalide"):
            manager.ensure_user_groups("frederic", ["-badgroup"])
