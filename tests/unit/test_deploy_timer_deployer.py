"""Tests pour le module deploy.timer_deployer."""

from dataclasses import replace
from unittest.mock import MagicMock, call, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.models import (
    DeployTarget,
    PhaseOutcome,
    TimerDeploySpec,
)
from linuxtools.deploy.timer_deployer import TimerDeployer
from linuxtools.systemd.base import ServiceConfig, TimerConfig

_MODULE = "linuxtools.deploy.timer_deployer"


def _cmd(stdout: str = "", code: int = 0) -> CommandResult:
    """CommandResult scripté."""
    return CommandResult(
        command=(),
        return_code=code,
        stdout=stdout,
        stderr="",
        success=code == 0,
        duration=0.01,
    )


def _linger_executor(
    user: str = "fred", linger: str | None = "no"
) -> MagicMock:
    """Exécuteur répondant aux sondes ``id -un`` et ``loginctl``."""
    executor = MagicMock(spec=CommandExecutor)

    def run(command: list[str], **_kwargs: object) -> CommandResult:
        if command[0] == "id":
            return _cmd(user + "\n")
        if command[0] == "loginctl":
            return _cmd("" if linger is None else linger + "\n", 0 if linger else 1)
        return _cmd()

    executor.run.side_effect = run
    return executor


def _commands(executor: MagicMock) -> list[list[str]]:
    """Commandes passées à l'exécuteur, dans l'ordre."""
    return [c.args[0] for c in executor.run.call_args_list]


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

        assert result.success is True
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

        assert result.success is False


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
        executor = _linger_executor()
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

        assert result.success is True
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
        executor = _linger_executor()
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
        executor = _linger_executor()
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

        assert result.success is False
        m_timer_mgr.return_value.install_timer_unit.assert_not_called()

    def test_deploy_user_scope_echec_install_timer_retourne_false(
        self,
    ) -> None:
        """Cas d'erreur : service OK mais échec du timer ->
        deploy() retourne False, enable_timer jamais appelé."""
        spec = replace(_make_spec(), scope="user")
        executor = _linger_executor()
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

        assert result.success is False
        m_timer_mgr.return_value.enable_timer.assert_not_called()

    def test_deploy_user_scope_echec_enable_timer_retourne_false(
        self,
    ) -> None:
        """Cas d'erreur : service et timer OK mais échec de
        l'activation -> deploy() retourne False."""
        spec = replace(_make_spec(), scope="user")
        executor = _linger_executor()
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

        assert result.success is False

    def test_deploy_scope_system_est_le_defaut(self) -> None:
        """`scope` vaut "system" par défaut sur TimerDeploySpec."""
        spec = _make_spec()

        assert spec.scope == "system"


class TestTimerDeployerLinger:
    """Sonde linger du scope « user » (lecture seule)."""

    @staticmethod
    def _deploy_user(executor: MagicMock) -> PhaseOutcome:
        """Déploie en scope user avec managers mockés en succès."""
        spec = replace(_make_spec(), scope="user")
        with (
            patch(f"{_MODULE}.UserSystemdExecutor"),
            patch(f"{_MODULE}.LinuxUserServiceUnitManager") as m_service,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager") as m_timer,
        ):
            m_service.return_value.install_service_unit_with_name.return_value = True
            m_timer.return_value.install_timer_unit.return_value = True
            m_timer.return_value.enable_timer.return_value = True
            return TimerDeployer(MagicMock()).deploy(
                spec, DeployTarget(), executor
            )

    def test_deploy_user_signale_linger_inactif(self) -> None:
        """F-11 : linger « no » -> message avec la commande à lancer."""
        executor = _linger_executor("fred", "no")

        outcome = self._deploy_user(executor)

        assert outcome.success is True
        assert outcome.messages == (
            "Linger inactif pour fred : le timer ne tournera pas hors "
            "session. À lancer : sudo loginctl enable-linger fred",
        )

    def test_deploy_user_linger_actif_message_neutre(self) -> None:
        """Linger « yes » -> message neutre."""
        outcome = self._deploy_user(_linger_executor("fred", "yes"))

        assert outcome.messages == ("Linger actif pour fred.",)

    @pytest.mark.parametrize("linger", [None, "maybe"])
    def test_deploy_user_linger_indetermine_si_sonde_echoue(
        self, linger: str | None
    ) -> None:
        """Sonde en échec ou réponse inattendue -> indéterminé."""
        outcome = self._deploy_user(_linger_executor("fred", linger))

        assert outcome.success is True
        assert outcome.messages == ("Linger indéterminé pour fred.",)

    def test_deploy_user_n_execute_jamais_enable_linger(self) -> None:
        """SEC : aucune commande ne contient enable-linger."""
        executor = _linger_executor("fred", "no")

        self._deploy_user(executor)

        assert not any(
            "enable-linger" in part
            for command in _commands(executor)
            for part in command
        )

    def test_deploy_system_n_appelle_pas_loginctl(self) -> None:
        """F-09 : scope system -> ni id ni loginctl, aucun message."""
        executor = _linger_executor()
        with (
            patch(f"{_MODULE}.SystemdExecutor"),
            patch(f"{_MODULE}.LinuxServiceUnitManager"),
            patch(f"{_MODULE}.LinuxTimerUnitManager"),
            patch(f"{_MODULE}.SystemdServiceTimerInstaller") as m_installer,
        ):
            m_installer.return_value.install.return_value = True
            outcome = TimerDeployer(MagicMock()).deploy(
                _make_spec(), DeployTarget(), executor
            )

        assert outcome == PhaseOutcome(True)
        assert [c[0] for c in _commands(executor)] == []

    @pytest.mark.parametrize("user", ["", "a b", "$(id)", "Fred;rm", "-x"])
    def test_deploy_user_nom_utilisateur_suspect_ne_passe_pas_a_loginctl(
        self, user: str
    ) -> None:
        """SEC : nom lu sur la cible invalide -> pas de loginctl."""
        executor = _linger_executor(user, "no")

        outcome = self._deploy_user(executor)

        assert outcome.messages == (
            "Linger indéterminé (utilisateur introuvable).",
        )
        assert all(c[0] != "loginctl" for c in _commands(executor))

    def test_deploy_user_echec_etape_ne_sonde_pas_le_linger(self) -> None:
        """Une étape en échec -> PhaseOutcome(False), aucune sonde."""
        executor = _linger_executor()
        spec = replace(_make_spec(), scope="user")
        with (
            patch(f"{_MODULE}.UserSystemdExecutor"),
            patch(f"{_MODULE}.LinuxUserServiceUnitManager") as m_service,
            patch(f"{_MODULE}.LinuxUserTimerUnitManager"),
        ):
            m_service.return_value.install_service_unit_with_name.return_value = False
            outcome = TimerDeployer(MagicMock()).deploy(
                spec, DeployTarget(), executor
            )

        assert outcome == PhaseOutcome(False)
        executor.run.assert_not_called()
