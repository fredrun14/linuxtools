"""Tests pour le module deploy.timer_deployer."""

from dataclasses import replace
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


class TestTimerDeployerDeployUser:
    """Tests de TimerDeployer.deploy() pour le scope "user" — mêmes
    principes que TestTimerDeployerDeploy, mais sur les managers
    utilisateur, sans passer par SystemdServiceTimerInstaller."""

    def test_deploy_user_scope_delegue_aux_managers_utilisateur(
        self,
    ) -> None:
        """Cas nominal : les 3 étapes (service -> timer -> enable)
        sont appelées sur les managers utilisateur, et
        SystemdServiceTimerInstaller n'est jamais sollicité."""
        spec = replace(_make_spec(), scope="user")
        target = DeployTarget()
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.UserSystemdExecutor") as m_user_systemd_exec,
            patch(
                f"{_MODULE}.LinuxUserServiceUnitManager"
            ) as m_service_mgr,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller") as m_installer,
        ):
            m_service_mgr.return_value.install_service_unit_with_name.return_value = (
                True
            )
            m_timer_mgr.return_value.install_timer_unit.return_value = True
            m_timer_mgr.return_value.enable_timer.return_value = True
            deployer = TimerDeployer(logger)

            result = deployer.deploy(spec, target, executor)

        assert result is True
        m_user_systemd_exec.assert_called_once_with(logger, executor)
        m_service_mgr.assert_called_once_with(
            logger, m_user_systemd_exec.return_value, remote_write=False
        )
        m_timer_mgr.assert_called_once_with(
            logger, m_user_systemd_exec.return_value, remote_write=False
        )
        m_service_mgr.return_value.install_service_unit_with_name.assert_called_once_with(
            "backup", spec.service_config
        )
        m_timer_mgr.return_value.install_timer_unit.assert_called_once_with(
            spec.timer_config
        )
        m_timer_mgr.return_value.enable_timer.assert_called_once_with(
            "backup"
        )
        m_installer.assert_not_called()

    def test_deploy_user_scope_cible_distante_propage_remote_write(
        self,
    ) -> None:
        """Cas limite : cible distante -> remote_write=True propagé
        aux deux gestionnaires d'unités utilisateur."""
        spec = replace(_make_spec(), scope="user")
        target = DeployTarget(host="srv01")
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.UserSystemdExecutor") as m_user_systemd_exec,
            patch(
                f"{_MODULE}.LinuxUserServiceUnitManager"
            ) as m_service_mgr,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller"),
        ):
            m_service_mgr.return_value.install_service_unit_with_name.return_value = (
                True
            )
            m_timer_mgr.return_value.install_timer_unit.return_value = True
            m_timer_mgr.return_value.enable_timer.return_value = True
            deployer = TimerDeployer(logger)

            deployer.deploy(spec, target, executor)

        assert m_service_mgr.call_args == call(
            logger, m_user_systemd_exec.return_value, remote_write=True
        )
        assert m_timer_mgr.call_args == call(
            logger, m_user_systemd_exec.return_value, remote_write=True
        )

    def test_deploy_user_scope_echec_install_service_retourne_false(
        self,
    ) -> None:
        """Cas d'erreur : échec de l'installation du service ->
        deploy() retourne False, install_timer_unit jamais appelé."""
        spec = replace(_make_spec(), scope="user")
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.UserSystemdExecutor"),
            patch(
                f"{_MODULE}.LinuxUserServiceUnitManager"
            ) as m_service_mgr,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller"),
        ):
            m_service_mgr.return_value.install_service_unit_with_name.return_value = (
                False
            )
            deployer = TimerDeployer(logger)

            result = deployer.deploy(spec, DeployTarget(), executor)

        assert result is False
        m_timer_mgr.return_value.install_timer_unit.assert_not_called()

    def test_deploy_user_scope_echec_install_timer_retourne_false(
        self,
    ) -> None:
        """Cas d'erreur : service OK mais échec du timer ->
        deploy() retourne False, enable_timer jamais appelé."""
        spec = replace(_make_spec(), scope="user")
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.UserSystemdExecutor"),
            patch(
                f"{_MODULE}.LinuxUserServiceUnitManager"
            ) as m_service_mgr,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller"),
        ):
            m_service_mgr.return_value.install_service_unit_with_name.return_value = (
                True
            )
            m_timer_mgr.return_value.install_timer_unit.return_value = False
            deployer = TimerDeployer(logger)

            result = deployer.deploy(spec, DeployTarget(), executor)

        assert result is False
        m_timer_mgr.return_value.enable_timer.assert_not_called()

    def test_deploy_user_scope_echec_enable_timer_retourne_false(
        self,
    ) -> None:
        """Cas d'erreur : service et timer OK mais échec de
        l'activation -> deploy() retourne False."""
        spec = replace(_make_spec(), scope="user")
        executor = MagicMock(spec=CommandExecutor)
        logger = MagicMock()

        with (
            patch(f"{_MODULE}.UserSystemdExecutor"),
            patch(
                f"{_MODULE}.LinuxUserServiceUnitManager"
            ) as m_service_mgr,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager") as m_timer_mgr,
            patch(f"{_MODULE}.SystemdServiceTimerInstaller"),
        ):
            m_service_mgr.return_value.install_service_unit_with_name.return_value = (
                True
            )
            m_timer_mgr.return_value.install_timer_unit.return_value = True
            m_timer_mgr.return_value.enable_timer.return_value = False
            deployer = TimerDeployer(logger)

            result = deployer.deploy(spec, DeployTarget(), executor)

        assert result is False

    def test_deploy_scope_system_est_le_defaut(self) -> None:
        """`scope` vaut "system" par défaut sur TimerDeploySpec."""
        spec = _make_spec()

        assert spec.scope == "system"
