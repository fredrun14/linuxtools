"""Tests pour le module systemd.executor."""

from unittest.mock import MagicMock, patch

import pytest

from linuxtools.systemd.executor import (
    SystemdExecutor,
    UserSystemdExecutor,
)


class TestSystemdExecutorValidation:
    """Tests pour la validation des noms d'unités dans SystemdExecutor."""

    def _make_executor(self) -> SystemdExecutor:
        """Crée un executor avec un logger mock."""
        logger = MagicMock()
        return SystemdExecutor(logger)

    def test_enable_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans enable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.enable_unit("bad;name.service")

    def test_disable_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans disable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.disable_unit("../etc.service")

    def test_start_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans start_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.start_unit("$(cmd).service")

    def test_stop_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans stop_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.stop_unit("bad name.service")

    def test_restart_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans restart_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.restart_unit(";evil.service")

    def test_get_status_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans get_status."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.get_status("../passwd.service")

    def test_is_enabled_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans is_enabled."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.is_enabled("bad;cmd.timer")

    def test_mask_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans mask_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.mask_unit("bad;name.service")

    def test_unmask_unit_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans unmask_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.unmask_unit("../etc.service")

    def test_is_masked_rejette_nom_invalide(self):
        """Vérifie le rejet d'un nom invalide dans is_masked."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.is_masked("bad;cmd.service")

    def test_nom_valide_accepte(self):
        """Vérifie que les noms valides passent la validation."""
        executor = self._make_executor()
        try:
            executor.get_status("backup.service")
        except ValueError:
            pytest.fail("Nom valide rejeté par la validation")

    def test_rejet_extension_inconnue(self):
        """Rejette une extension non autorisée dans enable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="non autorisée"):
            executor.enable_unit("backup.path")

    def test_rejet_sans_extension(self):
        """Rejette un nom sans extension dans start_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="sans extension"):
            executor.start_unit("backup")


class TestUserSystemdExecutorValidation:
    """Tests pour la validation dans UserSystemdExecutor."""

    def test_enable_unit_rejette_nom_invalide(self):
        """Vérifie le rejet dans l'executor utilisateur."""
        logger = MagicMock()
        executor = UserSystemdExecutor(logger)
        with pytest.raises(ValueError, match="invalide"):
            executor.enable_unit("bad;name.service")


class TestSystemdExecutorMocked:
    """Tests pour SystemdExecutor avec subprocess.run mocke."""

    def _make_executor(self):
        """Cree un executor avec logger mock."""
        logger = MagicMock()
        return SystemdExecutor(logger), logger

    def _mock_success(self):
        """Cree un resultat subprocess de succes."""
        import subprocess
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = "active\n"
        result.stderr = ""
        return result

    def _mock_failure(self):
        """Cree une exception subprocess.CalledProcessError."""
        import subprocess
        return subprocess.CalledProcessError(1, ["systemctl"])

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_reload_systemd_succes(self, mock_run):
        """reload_systemd() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.reload_systemd()
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_reload_systemd_echec(self, mock_run):
        """reload_systemd() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "daemon-reload"]
        )
        executor, logger = self._make_executor()
        result = executor.reload_systemd()
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_enable_unit_succes_avec_now(self, mock_run):
        """enable_unit() avec now=True retourne True."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.enable_unit("backup.service", now=True)
        assert result is True
        logger.log_info.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "--now" in args

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_enable_unit_succes_sans_now(self, mock_run):
        """enable_unit() avec now=False ne passe pas --now."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.enable_unit("backup.service", now=False)
        assert result is True
        args = mock_run.call_args[0][0]
        assert "--now" not in args

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_enable_unit_echec(self, mock_run):
        """enable_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "enable", "backup.service"]
        )
        executor, logger = self._make_executor()
        result = executor.enable_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_disable_unit_succes(self, mock_run):
        """disable_unit() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.disable_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_disable_unit_echec(self, mock_run):
        """disable_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "disable", "backup.service"]
        )
        executor, logger = self._make_executor()
        result = executor.disable_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_disable_unit_ignore_errors(self, mock_run):
        """disable_unit() avec ignore_errors retourne True."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "disable", "backup.service"]
        )
        executor, logger = self._make_executor()
        result = executor.disable_unit(
            "backup.service", ignore_errors=True
        )
        assert result is True
        logger.log_warning.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_start_unit_succes(self, mock_run):
        """start_unit() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.start_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_start_unit_echec(self, mock_run):
        """start_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "start", "backup.service"]
        )
        executor, logger = self._make_executor()
        result = executor.start_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_stop_unit_succes(self, mock_run):
        """stop_unit() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.stop_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_stop_unit_echec(self, mock_run):
        """stop_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "stop", "backup.service"]
        )
        executor, logger = self._make_executor()
        result = executor.stop_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_restart_unit_succes(self, mock_run):
        """restart_unit() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.restart_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_restart_unit_echec(self, mock_run):
        """restart_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "restart", "backup.service"]
        )
        executor, logger = self._make_executor()
        result = executor.restart_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_get_status_retourne_statut(self, mock_run):
        """get_status() retourne le statut de l unite."""
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        status = executor.get_status("backup.service")
        assert status == "active"

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_get_status_erreur_subprocess(self, mock_run):
        """get_status() retourne None en cas d OSError."""
        mock_run.side_effect = OSError("systemctl non trouve")
        executor, logger = self._make_executor()
        result = executor.get_status("backup.service")
        assert result is None
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_active_retourne_true(self, mock_run):
        """is_active() retourne True si statut == active."""
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        assert executor.is_active("backup.service") is True

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_active_retourne_false(self, mock_run):
        """is_active() retourne False si statut != active."""
        mock_result = MagicMock()
        mock_result.stdout = "inactive\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        assert executor.is_active("backup.service") is False

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_enabled_retourne_true(self, mock_run):
        """is_enabled() retourne True si statut == enabled."""
        mock_result = MagicMock()
        mock_result.stdout = "enabled\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        assert executor.is_enabled("backup.service") is True

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_enabled_retourne_false(self, mock_run):
        """is_enabled() retourne False si statut != enabled."""
        mock_result = MagicMock()
        mock_result.stdout = "disabled\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        assert executor.is_enabled("backup.service") is False

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_enabled_erreur(self, mock_run):
        """is_enabled() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.SubprocessError("erreur")
        executor, logger = self._make_executor()
        result = executor.is_enabled("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_masked_retourne_true(self, mock_run):
        """is_masked() retourne True si stdout == masked."""
        mock_result = MagicMock()
        mock_result.stdout = "masked\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        assert executor.is_masked("packagekit.service") is True

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_masked_retourne_false(self, mock_run):
        """is_masked() retourne False si stdout != masked."""
        mock_result = MagicMock()
        mock_result.stdout = "enabled\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        assert executor.is_masked("packagekit.service") is False

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_is_masked_erreur(self, mock_run):
        """is_masked() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.SubprocessError("erreur")
        executor, logger = self._make_executor()
        assert executor.is_masked("packagekit.service") is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_mask_unit_succes(self, mock_run):
        """mask_unit() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.mask_unit("packagekit.service")
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_mask_unit_echec(self, mock_run):
        """mask_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "mask", "packagekit.service"]
        )
        executor, logger = self._make_executor()
        result = executor.mask_unit("packagekit.service")
        assert result is False
        logger.log_error.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_unmask_unit_succes(self, mock_run):
        """unmask_unit() retourne True en cas de succes."""
        mock_run.return_value = self._mock_success()
        executor, logger = self._make_executor()
        result = executor.unmask_unit("packagekit.service")
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_unmask_unit_echec(self, mock_run):
        """unmask_unit() retourne False en cas d erreur."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "unmask", "packagekit.service"]
        )
        executor, logger = self._make_executor()
        result = executor.unmask_unit("packagekit.service")
        assert result is False
        logger.log_error.assert_called_once()


class TestUserSystemdExecutorMocked:
    """Tests pour UserSystemdExecutor avec subprocess.run mocke."""

    def _make_executor(self):
        """Cree un executor utilisateur avec logger mock."""
        logger = MagicMock()
        return UserSystemdExecutor(logger), logger

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_run_systemctl_utilise_user_flag(self, mock_run):
        """_run_systemctl() utilise --user dans la commande."""
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result
        executor, _ = self._make_executor()
        executor._run_systemctl(["status", "backup.service"])
        args = mock_run.call_args[0][0]
        assert "--user" in args
        assert "systemctl" in args[0]

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_reload_systemd_user_succes(self, mock_run):
        """reload_systemd() pour user retourne True."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        executor, logger = self._make_executor()
        result = executor.reload_systemd()
        assert result is True
        logger.log_info.assert_called_once()

    @patch("linuxtools.systemd.executor.subprocess.run")
    def test_reload_systemd_user_echec(self, mock_run):
        """reload_systemd() pour user retourne False."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["systemctl", "--user", "daemon-reload"]
        )
        executor, logger = self._make_executor()
        result = executor.reload_systemd()
        assert result is False
        logger.log_error.assert_called_once()
