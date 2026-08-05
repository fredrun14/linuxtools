"""Tests pour le module systemd.executor."""

from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandResult
from linuxtools.systemd.executor import (
    SystemdExecutor,
    UserSystemdExecutor,
)


def _result(
    return_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    command: tuple[str, ...] = ("systemctl",),
) -> CommandResult:
    """Construit un CommandResult prêt à retourner par un mock."""
    return CommandResult(
        command=command,
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        success=return_code == 0,
        duration=0.0,
    )


class TestSystemdExecutorValidation:
    """Tests pour la validation des noms d'unités dans SystemdExecutor."""

    def _make_executor(self) -> SystemdExecutor:
        """Crée un executor avec un logger mock."""
        logger = MagicMock()
        return SystemdExecutor(logger)

    def test_enable_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans enable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.enable_unit("bad;name.service")

    def test_disable_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans disable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.disable_unit("../etc.service")

    def test_start_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans start_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.start_unit("$(cmd).service")

    def test_stop_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans stop_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.stop_unit("bad name.service")

    def test_restart_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans restart_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.restart_unit(";evil.service")

    def test_get_status_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans get_status."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.get_status("../passwd.service")

    def test_is_enabled_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans is_enabled."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.is_enabled("bad;cmd.timer")

    def test_mask_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans mask_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.mask_unit("bad;name.service")

    def test_unmask_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans unmask_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.unmask_unit("../etc.service")

    def test_is_masked_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans is_masked."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.is_masked("bad;cmd.service")

    def test_nom_valide_accepte(self) -> None:
        """Vérifie que les noms valides passent la validation."""
        executor = self._make_executor()
        try:
            executor.get_status("backup.service")
        except ValueError:
            pytest.fail("Nom valide rejeté par la validation")

    def test_rejet_extension_inconnue(self) -> None:
        """Rejette une extension non autorisée dans enable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="non autorisée"):
            executor.enable_unit("backup.path")

    def test_rejet_sans_extension(self) -> None:
        """Rejette un nom sans extension dans start_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="sans extension"):
            executor.start_unit("backup")


class TestUserSystemdExecutorValidation:
    """Tests pour la validation dans UserSystemdExecutor."""

    def test_enable_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet dans l'executor utilisateur."""
        logger = MagicMock()
        executor = UserSystemdExecutor(logger)
        with pytest.raises(ValueError, match="invalide"):
            executor.enable_unit("bad;name.service")


class TestSystemdExecutorMocked:
    """Tests pour SystemdExecutor avec un CommandExecutor injecté mocké."""

    def _make_executor(
        self,
    ) -> tuple[SystemdExecutor, MagicMock, MagicMock]:
        """Crée un executor avec logger et CommandExecutor mockés."""
        logger = MagicMock()
        command_executor = MagicMock()
        return (
            SystemdExecutor(logger, command_executor),
            logger,
            command_executor,
        )

    def test_reload_systemd_succes(self) -> None:
        """reload_systemd() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.reload_systemd()
        assert result is True
        logger.log_info.assert_called_once()

    def test_reload_systemd_echec(self) -> None:
        """reload_systemd() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.reload_systemd()
        assert result is False
        logger.log_error.assert_called_once()

    def test_enable_unit_succes_avec_now(self) -> None:
        """enable_unit() avec now=True retourne True."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.enable_unit("backup.service", now=True)
        assert result is True
        logger.log_info.assert_called_once()
        args = command_executor.run.call_args[0][0]
        assert "--now" in args

    def test_enable_unit_succes_sans_now(self) -> None:
        """enable_unit() avec now=False ne passe pas --now."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.enable_unit("backup.service", now=False)
        assert result is True
        args = command_executor.run.call_args[0][0]
        assert "--now" not in args

    def test_enable_unit_echec(self) -> None:
        """enable_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.enable_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_disable_unit_succes(self) -> None:
        """disable_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.disable_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_disable_unit_echec(self) -> None:
        """disable_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.disable_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_disable_unit_ignore_errors(self) -> None:
        """disable_unit() avec ignore_errors retourne True."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.disable_unit(
            "backup.service", ignore_errors=True
        )
        assert result is True
        logger.log_warning.assert_called_once()

    def test_start_unit_succes(self) -> None:
        """start_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.start_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_start_unit_echec(self) -> None:
        """start_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.start_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_stop_unit_succes(self) -> None:
        """stop_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.stop_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_stop_unit_echec(self) -> None:
        """stop_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.stop_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_restart_unit_succes(self) -> None:
        """restart_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.restart_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_restart_unit_echec(self) -> None:
        """restart_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.restart_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_get_status_retourne_statut(self) -> None:
        """get_status() retourne le statut de l unite."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="active\n")
        status = executor.get_status("backup.service")
        assert status == "active"

    def test_get_status_retourne_chaine_vide_si_commande_echoue(
        self,
    ) -> None:
        """get_status() retourne "" (jamais None) si la commande echoue.

        CommandExecutor.run() ne leve jamais : une erreur systeme est
        deja convertie en CommandResult avec un stdout vide.
        """
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=-1, stdout="", stderr="systemctl non trouve"
        )
        result = executor.get_status("backup.service")
        assert result == ""

    def test_is_active_retourne_true(self) -> None:
        """is_active() retourne True si statut == active."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="active\n")
        assert executor.is_active("backup.service") is True

    def test_is_active_retourne_false(self) -> None:
        """is_active() retourne False si statut != active."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="inactive\n")
        assert executor.is_active("backup.service") is False

    def test_is_enabled_retourne_true(self) -> None:
        """is_enabled() retourne True si statut == enabled."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="enabled\n")
        assert executor.is_enabled("backup.service") is True

    def test_is_enabled_retourne_false(self) -> None:
        """is_enabled() retourne False si statut != enabled."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="disabled\n")
        assert executor.is_enabled("backup.service") is False

    def test_is_enabled_erreur(self) -> None:
        """is_enabled() retourne False en cas d erreur."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=-1, stdout="", stderr="erreur"
        )
        result = executor.is_enabled("backup.service")
        assert result is False

    def test_is_masked_retourne_true(self) -> None:
        """is_masked() retourne True si stdout == masked."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="masked\n")
        assert executor.is_masked("packagekit.service") is True

    def test_is_masked_retourne_false(self) -> None:
        """is_masked() retourne False si stdout != masked."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="enabled\n")
        assert executor.is_masked("packagekit.service") is False

    def test_is_masked_erreur(self) -> None:
        """is_masked() retourne False en cas d erreur."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=-1, stdout="", stderr="erreur"
        )
        assert executor.is_masked("packagekit.service") is False

    def test_mask_unit_succes(self) -> None:
        """mask_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.mask_unit("packagekit.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_mask_unit_echec(self) -> None:
        """mask_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.mask_unit("packagekit.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_unmask_unit_succes(self) -> None:
        """unmask_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.unmask_unit("packagekit.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_unmask_unit_echec(self) -> None:
        """unmask_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.unmask_unit("packagekit.service")
        assert result is False
        logger.log_error.assert_called_once()


class TestSystemdExecutorSansExecutorInjecte:
    """Non-régression : SystemdExecutor(logger) reste utilisable seul."""

    def test_sans_executor_utilise_linuxcommandexecutor_local(
        self,
    ) -> None:
        """Sans executor injecté, un LinuxCommandExecutor local est créé."""
        from linuxtools.commands.runner import LinuxCommandExecutor

        logger = MagicMock()
        executor = SystemdExecutor(logger)
        assert isinstance(executor._executor, LinuxCommandExecutor)


class TestUserSystemdExecutorMocked:
    """Tests pour UserSystemdExecutor avec un CommandExecutor mocké."""

    def _make_executor(
        self,
    ) -> tuple[UserSystemdExecutor, MagicMock, MagicMock]:
        """Crée un executor utilisateur avec logger et CommandExecutor mockés."""
        logger = MagicMock()
        command_executor = MagicMock()
        return (
            UserSystemdExecutor(logger, command_executor),
            logger,
            command_executor,
        )

    def test_run_systemctl_utilise_user_flag(self) -> None:
        """_run_systemctl() utilise --user dans la commande."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="active\n")
        executor._run_systemctl(["status", "backup.service"])
        args = command_executor.run.call_args[0][0]
        assert "--user" in args
        assert "systemctl" in args[0]

    def test_reload_systemd_user_succes(self) -> None:
        """reload_systemd() pour user retourne True."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.reload_systemd()
        assert result is True
        logger.log_info.assert_called_once()

    def test_reload_systemd_user_echec(self) -> None:
        """reload_systemd() pour user retourne False."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(
            return_code=1, stderr="erreur"
        )
        result = executor.reload_systemd()
        assert result is False
        logger.log_error.assert_called_once()
