"""Tests pour le module deploy.timer_deployer."""

from unittest.mock import MagicMock, call, patch

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.models import DeployTarget, TimerDeploySpec
from linuxtools.deploy.timer_deployer import TimerDeployer
from linuxtools.systemd.base import ServiceConfig, TimerConfig

_MODULE = "linuxtools.deploy.timer_deployer"


def _make_spec() -> TimerDeploySpec:
    """Construit une TimerDeploySpec minimale valide."""
    return TimerDeploySpec(
        unit_name="backup",
        service_config=ServiceConfig(
            description="Backup service", exec_start="/usr/bin/backup"
        ),
        timer_config=TimerConfig(
            description="Backup timer",
            unit="backup.service",
            on_calendar="daily",
        ),
    )


class TestTimerDeployerDeploy:
    """Tests de TimerDeployer.deploy() — assemblage des collaborateurs
    systemd, sans exécution réelle de systemctl (tout est mocké au
    niveau des classes importées par le module)."""

    def test_deploy_nominal_delegue_a_l_installateur(self) -> None:
        """Cas nominal : les collaborateurs sont construits avec les
        bons arguments et install() est appelé avec la spec."""
        spec = _make_spec()
        target = DeployTarget()
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.SystemdExecutor") as m_systemd_exec,
            patch(f"{_MODULE}.LinuxServiceUnitManager") as m_service_mgr,
            patch(f"{_MODULE}.LinuxTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller") as m_installer,
        ):
            m_installer.return_value.install.return_value = True
            deployer = TimerDeployer(logger)

            result = deployer.deploy(spec, target, executor)

        assert result is True
        m_systemd_exec.assert_called_once_with(logger, executor)
        m_service_mgr.assert_called_once_with(
            logger, m_systemd_exec.return_value, remote_write=False
        )
        m_timer_mgr.assert_called_once_with(
            logger, m_systemd_exec.return_value, remote_write=False
        )
        m_installer.assert_called_once_with(
            logger, m_service_mgr.return_value, m_timer_mgr.return_value
        )
        m_installer.return_value.install.assert_called_once_with(
            "backup", spec.service_config, spec.timer_config
        )

    def test_deploy_cible_distante_propage_remote_write(self) -> None:
        """Cas limite : cible distante -> remote_write=True propagé
        aux deux gestionnaires d'unités."""
        spec = _make_spec()
        target = DeployTarget(host="srv01")
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.SystemdExecutor") as m_systemd_exec,
            patch(f"{_MODULE}.LinuxServiceUnitManager") as m_service_mgr,
            patch(f"{_MODULE}.LinuxTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller") as m_installer,
        ):
            m_installer.return_value.install.return_value = True
            deployer = TimerDeployer(logger)

            deployer.deploy(spec, target, executor)

        assert m_service_mgr.call_args == call(
            logger, m_systemd_exec.return_value, remote_write=True
        )
        assert m_timer_mgr.call_args == call(
            logger, m_systemd_exec.return_value, remote_write=True
        )

    def test_deploy_sans_logger_utilise_console_logger(self) -> None:
        """Cas limite : logger=None -> fallback sur ConsoleLogger,
        propagé à SystemdExecutor."""
        spec = _make_spec()
        executor = MagicMock(spec=CommandExecutor)

        with (
            patch(f"{_MODULE}.ConsoleLogger") as m_console_logger,
            patch(f"{_MODULE}.SystemdExecutor") as m_systemd_exec,
            patch(f"{_MODULE}.LinuxServiceUnitManager"),
            patch(f"{_MODULE}.LinuxTimerUnitManager"),
            patch(f"{_MODULE}.SystemdServiceTimerInstaller") as m_installer,
        ):
            m_installer.return_value.install.return_value = True
            deployer = TimerDeployer(logger=None)

            deployer.deploy(spec, DeployTarget(), executor)

        m_console_logger.assert_called_once_with()
        m_systemd_exec.assert_called_once_with(
            m_console_logger.return_value, executor
        )

    def test_deploy_echec_installation_retourne_false(self) -> None:
        """Cas d'erreur : install() échoue -> deploy() retourne False."""
        spec = _make_spec()
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.SystemdExecutor"),
            patch(f"{_MODULE}.LinuxServiceUnitManager"),
            patch(f"{_MODULE}.LinuxTimerUnitManager"),
            patch(f"{_MODULE}.SystemdServiceTimerInstaller") as m_installer,
        ):
            m_installer.return_value.install.return_value = False
            deployer = TimerDeployer(logger)

            result = deployer.deploy(spec, DeployTarget(), executor)

        assert result is False
