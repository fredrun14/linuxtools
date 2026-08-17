"""Tests pour le module deploy.deployer."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.config_deployer import ConfigDeployer
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    CheckResult,
    ConfigDeploySpec,
    DeployConfig,
    DeployPhase,
    DeployTarget,
    SecretsSpec,
    TimerDeploySpec,
    VerificationSpec,
)
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner
from linuxtools.deploy.timer_deployer import TimerDeployer
from linuxtools.deploy.transport import RsyncTransport, Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier
from linuxtools.systemd.base import ServiceConfig, TimerConfig


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


_EXISTING_DIR = Path(__file__).resolve().parent


def _make_config(
    source_dir: Path | None = _EXISTING_DIR,
) -> DeployConfig:
    """Construit une DeployConfig minimale pour les tests.

    source_dir par défaut pointe vers un répertoire réel (le
    répertoire des tests) car _resolve_source_dir valide désormais
    son existence (correctif #3) — même en dry-run.
    """
    return DeployConfig(
        source_dir=source_dir,
        venv_path=Path("/opt/app/venv"),
        remote_source_dir=Path("/opt/app/src"),
        target=DeployTarget(),
        verification=VerificationSpec(imports=("app",)),
        cli_bin="app-cli",
    )


def _make_collaborators() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Crée les 3 collaborateurs mockés injectés dans Deployer."""
    transport = MagicMock(spec=Transport)
    installer = MagicMock(spec=VenvInstaller)
    verifier = MagicMock(spec=InstallVerifier)
    return transport, installer, verifier


class TestDeployerDeploySucces:
    """Ligne 1 de la table rollback : succès complet."""

    def test_deploy_succes_complet(self) -> None:
        """Toutes les phases réussissent : succès, phase DONE, prune."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = Path(
            "/opt/app/venv.bak-1"
        )
        installer.install.return_value = _result(success=True)
        verifier.verify.return_value = [
            CheckResult(label="import app", ok=True)
        ]
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is True
        assert report.phase_reached is DeployPhase.DONE
        assert report.rolled_back is False
        installer.prune_backup.assert_called_once_with(
            Path("/opt/app/venv.bak-1")
        )

    def test_deploy_succes_venv_neuf_pas_de_prune(self) -> None:
        """Sans backup (venv neuf), prune_backup n'est pas appelé."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = None
        installer.install.return_value = _result(success=True)
        verifier.verify.return_value = []
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is True
        installer.prune_backup.assert_not_called()


class TestDeployerDeployEchecTransport:
    """Ligne 2 de la table rollback : échec transport."""

    def test_echec_transport_arrete_avant_backup(self) -> None:
        """Un échec de transport arrête avant tout backup/install."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(
            success=False, stderr="connexion refusée"
        )
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.phase_reached is DeployPhase.TRANSPORT
        installer.backup_venv.assert_not_called()


class TestDeployerDeployEchecBackup:
    """Ligne 3 de la table rollback : échec backup."""

    def test_echec_backup_arrete_avant_install(self) -> None:
        """DeployError de backup_venv arrête avant l'installation."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.side_effect = DeployError(
            "cp: permission denied"
        )
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.phase_reached is DeployPhase.BACKUP
        installer.install.assert_not_called()


class TestDeployerDeployEchecInstall:
    """Lignes 4 et 5 de la table rollback : échec install."""

    def test_echec_install_avec_backup_declenche_rollback(self) -> None:
        """Backup dispo : install échoue -> restore_venv appelé."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = Path(
            "/opt/app/venv.bak-1"
        )
        installer.install.return_value = _result(
            success=False, stderr="pip error"
        )
        installer.restore_venv.return_value = True
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.rolled_back is True
        assert report.phase_reached is DeployPhase.ROLLBACK
        installer.restore_venv.assert_called_once_with(
            Path("/opt/app/venv"), Path("/opt/app/venv.bak-1")
        )
        verifier.verify.assert_not_called()

    def test_echec_install_sans_backup_pas_de_rollback(self) -> None:
        """Venv neuf (pas de backup) : install échoue -> pas de restore."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = None
        installer.install.return_value = _result(
            success=False, stderr="pip error"
        )
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.rolled_back is False
        assert report.phase_reached is DeployPhase.INSTALL
        installer.restore_venv.assert_not_called()

    def test_echec_install_et_rollback_ko_ajoute_un_message(self) -> None:
        """Backup dispo, install échoue ET restore_venv échoue :
        le rapport contient un message explicite d'alerte
        (correctif #2 — un rapport honnête ne tait pas l'échec du
        rollback)."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        backup_path = Path("/opt/app/venv.bak-1")
        installer.backup_venv.return_value = backup_path
        installer.install.return_value = _result(
            success=False, stderr="pip error"
        )
        installer.restore_venv.return_value = False
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.rolled_back is False
        assert report.phase_reached is DeployPhase.INSTALL
        assert any(
            "Rollback ÉCHOUÉ" in m and str(backup_path) in m
            for m in report.messages
        )


class TestDeployerDeployEchecVerify:
    """Ligne 6 de la table rollback : échec vérification."""

    def test_echec_verify_avec_backup_declenche_rollback(self) -> None:
        """Backup dispo : vérif échoue -> restore_venv appelé."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = Path(
            "/opt/app/venv.bak-1"
        )
        installer.install.return_value = _result(success=True)
        verifier.verify.return_value = [
            CheckResult(label="import app", ok=False, detail="boom")
        ]
        installer.restore_venv.return_value = True
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.rolled_back is True
        assert report.phase_reached is DeployPhase.ROLLBACK
        installer.prune_backup.assert_not_called()

    def test_echec_verify_sans_backup_pas_de_rollback(self) -> None:
        """Venv neuf : vérif échoue -> pas de restore, phase VERIFY."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = None
        installer.install.return_value = _result(success=True)
        verifier.verify.return_value = [
            CheckResult(label="import app", ok=False, detail="boom")
        ]
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.rolled_back is False
        assert report.phase_reached is DeployPhase.VERIFY
        installer.restore_venv.assert_not_called()

    def test_echec_verify_et_rollback_ko_ajoute_un_message(self) -> None:
        """Backup dispo, vérif échoue ET restore_venv échoue : le
        rapport contient un message explicite d'alerte (correctif
        #2)."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        backup_path = Path("/opt/app/venv.bak-1")
        installer.backup_venv.return_value = backup_path
        installer.install.return_value = _result(success=True)
        verifier.verify.return_value = [
            CheckResult(label="import app", ok=False, detail="boom")
        ]
        installer.restore_venv.return_value = False
        deployer = Deployer(transport, installer, verifier)

        report = deployer.deploy(_make_config())

        assert report.success is False
        assert report.rolled_back is False
        assert any(
            "Rollback ÉCHOUÉ" in m and str(backup_path) in m
            for m in report.messages
        )


class TestDeployerDeployDryRun:
    """Tests du mode dry-run (F-11) : simulation sans effet de bord."""

    def test_dry_run_ne_touche_aucun_collaborateur(self) -> None:
        """dry_run=True : aucun appel réel à transport/installer/verifier."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(
            transport, installer, verifier, dry_run=True
        )

        report = deployer.deploy(_make_config())

        assert report.success is True
        assert report.phase_reached is DeployPhase.DONE
        transport.transfer.assert_not_called()
        installer.backup_venv.assert_not_called()
        installer.install.assert_not_called()
        verifier.verify.assert_not_called()

    def test_dry_run_affiche_les_operations_simulees(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Le dry-run affiche les opérations simulées via DryRunContext."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(
            transport, installer, verifier, dry_run=True
        )

        deployer.deploy(_make_config())

        out = capsys.readouterr().out
        assert "[DRY-RUN]" in out
        assert "rsync" in out
        assert "pip install" in out

    def test_dry_run_cible_distante_affiche_destination_ssh(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry-run avec cible distante : destination user@host:dest."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(
            transport, installer, verifier, dry_run=True
        )
        config = _make_config()
        config = DeployConfig(
            source_dir=config.source_dir,
            venv_path=config.venv_path,
            remote_source_dir=config.remote_source_dir,
            target=DeployTarget(host="srv01", user="deploy"),
            verification=config.verification,
            cli_bin=config.cli_bin,
        )

        deployer.deploy(config)

        out = capsys.readouterr().out
        assert "deploy@srv01:/opt/app/src" in out

    def test_dry_run_recreate_venv_affiche_rm_et_venv(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """recreate_venv=True : le dry-run montre rm -rf puis
        python3 -m venv avant le pip install (correctif #6)."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(
            transport, installer, verifier, dry_run=True
        )
        base = _make_config(source_dir=tmp_path)
        config = DeployConfig(
            source_dir=base.source_dir,
            venv_path=base.venv_path,
            remote_source_dir=base.remote_source_dir,
            target=base.target,
            verification=base.verification,
            cli_bin=base.cli_bin,
            recreate_venv=True,
        )

        deployer.deploy(config)

        out = capsys.readouterr().out
        assert f"rm -rf {base.venv_path}" in out
        assert f"python3 -m venv {base.venv_path}" in out
        rm_index = out.index(f"rm -rf {base.venv_path}")
        venv_index = out.index(f"python3 -m venv {base.venv_path}")
        pip_index = out.index("pip install")
        assert rm_index < venv_index < pip_index


class TestDeployerResolveSourceDir:
    """Tests de la résolution auto (V1) de source_dir."""

    def test_source_dir_none_introuvable(self) -> None:
        """Aucun pyproject.toml trouvé : échec dès la phase TRANSPORT."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(transport, installer, verifier)

        with patch(
            "linuxtools.deploy.deployer.find_project_source",
            return_value=None,
        ):
            report = deployer.deploy(_make_config(source_dir=None))

        assert report.success is False
        assert report.phase_reached is DeployPhase.TRANSPORT
        assert "introuvable" in report.messages[0]
        transport.transfer.assert_not_called()

    def test_source_dir_none_auto_detecte(self) -> None:
        """source_dir auto-détecté est utilisé et loggué."""
        transport, installer, verifier = _make_collaborators()
        transport.transfer.return_value = _result(success=True)
        installer.backup_venv.return_value = None
        installer.install.return_value = _result(success=True)
        verifier.verify.return_value = []
        logger = MagicMock()
        deployer = Deployer(transport, installer, verifier, logger)

        detected = _EXISTING_DIR
        with patch(
            "linuxtools.deploy.deployer.find_project_source",
            return_value=detected,
        ):
            report = deployer.deploy(_make_config(source_dir=None))

        assert report.success is True
        assert any(
            "auto-détecté" in m for m in report.messages
        )
        transport.transfer.assert_called_once()
        assert transport.transfer.call_args.args[0] == detected
        logger.log_info.assert_called_once_with(
            f"Source auto-détecté : {detected}"
        )

    def test_source_dir_auto_detecte_inexistant(self) -> None:
        """source_dir auto-détecté mais inexistant sur disque : échec
        phase TRANSPORT, pas d'exception (correctif #3)."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(transport, installer, verifier)

        detected = Path("/home/user/mon-projet-disparu")
        with patch(
            "linuxtools.deploy.deployer.find_project_source",
            return_value=detected,
        ):
            report = deployer.deploy(_make_config(source_dir=None))

        assert report.success is False
        assert report.phase_reached is DeployPhase.TRANSPORT
        assert "inexistant" in report.messages[0]
        transport.transfer.assert_not_called()

    def test_source_dir_explicite_inexistant(self) -> None:
        """source_dir explicite inexistant : DeployReport en échec
        phase TRANSPORT, pas de FileNotFoundError levée (correctif
        #3, contrat de l'API)."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(transport, installer, verifier)

        config = _make_config(
            source_dir=Path("/inexistant/source-dir")
        )

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.TRANSPORT
        assert "inexistant" in report.messages[0]
        transport.transfer.assert_not_called()


class TestDeployerForTarget:
    """Tests pour la fabrique Deployer.for_target()."""

    def test_for_target_local_utilise_le_meme_executeur(self) -> None:
        """Cible locale : transport/installer/verifier partagent le
        même LinuxCommandExecutor (pas de SshCommandExecutor)."""
        deployer = Deployer.for_target(DeployTarget())

        # Deployer._transport est typé Transport (ABC) ; for_target()
        # construit toujours un RsyncTransport concret, seul à exposer
        # _local. L'isinstance narrowe pour mypy sans changer le
        # comportement runtime du test.
        assert isinstance(deployer._transport, RsyncTransport)
        assert deployer._transport._local is (
            deployer._installer._executor
        )
        assert deployer._installer._executor is (
            deployer._verifier._executor
        )

    def test_for_target_remote_utilise_ssh_command_executor(self) -> None:
        """Cible distante : installer/verifier reçoivent un
        SshCommandExecutor."""
        from linuxtools.deploy.ssh_executor import SshCommandExecutor

        deployer = Deployer.for_target(DeployTarget(host="srv01"))

        assert isinstance(
            deployer._installer._executor, SshCommandExecutor
        )
        assert isinstance(
            deployer._verifier._executor, SshCommandExecutor
        )

    def test_for_target_propage_dry_run(self) -> None:
        """dry_run est propagé au Deployer construit."""
        deployer = Deployer.for_target(DeployTarget(), dry_run=True)
        assert deployer._dry_run is True


def _make_config_with_phases(**overrides: object) -> DeployConfig:
    """Étend _make_config() avec les specs des 3 nouvelles phases."""
    return replace(_make_config(), **overrides)  # type: ignore[arg-type]


def _make_successful_base_collaborators() -> (
    tuple[MagicMock, MagicMock, MagicMock]
):
    """Transport/installer/verifier scriptés en succès jusqu'à VERIFY,
    prêts pour enchaîner sur les phases CONFIG/SECRETS/TIMER."""
    transport, installer, verifier = _make_collaborators()
    transport.transfer.return_value = _result(success=True)
    installer.backup_venv.return_value = None
    installer.install.return_value = _result(success=True)
    verifier.verify.return_value = [
        CheckResult(label="import app", ok=True)
    ]
    return transport, installer, verifier


_CONFIG_SPEC = ConfigDeploySpec(
    data={"a": 1}, dest_path=Path("/etc/app/config.toml")
)
_SECRETS_SPEC = SecretsSpec(
    service="svc",
    keys=("TOKEN",),
    dest_path=Path("/etc/app/secrets.env"),
)
_TIMER_SPEC = TimerDeploySpec(
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


class TestDeployerNouvellesPhases:
    """Tests d'intégration des phases CONFIG/SECRETS/TIMER dans
    Deployer.deploy() — chaque phase est best-effort (pas de rollback
    en cas d'échec), et le rapport final est toujours retourné
    proprement plutôt qu'une exception."""

    def test_toutes_les_phases_reussissent_rapport_final_done(
        self,
    ) -> None:
        """Succès complet : les 3 phases sont appelées avec (spec,
        target, target_executor) et leurs messages figurent dans le
        rapport final."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        config_deployer = MagicMock(spec=ConfigDeployer)
        config_deployer.deploy.return_value = True
        secrets_provisioner = MagicMock(spec=SecretsProvisioner)
        secrets_provisioner.provision.return_value = True
        timer_deployer = MagicMock(spec=TimerDeployer)
        timer_deployer.deploy.return_value = True
        target_executor = MagicMock(spec=CommandExecutor)
        config = _make_config_with_phases(
            config_deploy=_CONFIG_SPEC,
            secrets=_SECRETS_SPEC,
            timer_deploy=_TIMER_SPEC,
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            config_deployer=config_deployer,
            secrets_provisioner=secrets_provisioner,
            timer_deployer=timer_deployer,
            target_executor=target_executor,
        )

        report = deployer.deploy(config)

        assert report.success is True
        assert report.phase_reached is DeployPhase.DONE
        config_deployer.deploy.assert_called_once_with(
            _CONFIG_SPEC, config.target, target_executor
        )
        secrets_provisioner.provision.assert_called_once_with(
            _SECRETS_SPEC, config.target, target_executor
        )
        timer_deployer.deploy.assert_called_once_with(
            _TIMER_SPEC, config.target, target_executor
        )
        assert "Config déployée." in report.messages
        assert "Secrets provisionnés." in report.messages
        assert "Service+timer installés." in report.messages

    def test_aucune_spec_configuree_aucun_collaborateur_appele(
        self,
    ) -> None:
        """Cas limite (no-op) : ni config_deploy, ni secrets, ni
        timer_deploy dans la config -> aucun des 3 collaborateurs
        n'est sollicité, même s'ils sont injectés."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        config_deployer = MagicMock(spec=ConfigDeployer)
        secrets_provisioner = MagicMock(spec=SecretsProvisioner)
        timer_deployer = MagicMock(spec=TimerDeployer)
        deployer = Deployer(
            transport,
            installer,
            verifier,
            config_deployer=config_deployer,
            secrets_provisioner=secrets_provisioner,
            timer_deployer=timer_deployer,
            target_executor=MagicMock(spec=CommandExecutor),
        )

        report = deployer.deploy(_make_config())

        assert report.success is True
        assert report.phase_reached is DeployPhase.DONE
        config_deployer.deploy.assert_not_called()
        secrets_provisioner.provision.assert_not_called()
        timer_deployer.deploy.assert_not_called()

    def test_config_deploy_configure_sans_config_deployer_echoue(
        self,
    ) -> None:
        """Cas limite (no-op collaborateur absent) : config.config_deploy
        renseigné mais aucun ConfigDeployer injecté -> échec propre,
        phase CONFIG, message explicite."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            target_executor=MagicMock(spec=CommandExecutor),
        )
        config = _make_config_with_phases(config_deploy=_CONFIG_SPEC)

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.CONFIG
        assert any(
            "ConfigDeployer non configuré" in m for m in report.messages
        )

    def test_secrets_configure_sans_target_executor_echoue(self) -> None:
        """Cas limite (no-op target_executor absent) : config.secrets
        renseigné mais aucun target_executor injecté -> échec propre,
        phase SECRETS, message explicite."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            secrets_provisioner=MagicMock(spec=SecretsProvisioner),
        )
        config = _make_config_with_phases(secrets=_SECRETS_SPEC)

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.SECRETS
        assert any(
            "target_executor non configuré" in m for m in report.messages
        )

    def test_timer_deploy_configure_sans_timer_deployer_echoue(
        self,
    ) -> None:
        """Cas limite (no-op collaborateur absent) : config.timer_deploy
        renseigné mais aucun TimerDeployer injecté -> échec propre,
        phase TIMER, message explicite."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            target_executor=MagicMock(spec=CommandExecutor),
        )
        config = _make_config_with_phases(timer_deploy=_TIMER_SPEC)

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.TIMER
        assert any(
            "TimerDeployer non configuré" in m for m in report.messages
        )

    def test_phase_config_echoue_arrete_avant_secrets_et_timer(
        self,
    ) -> None:
        """Échec best-effort : ConfigDeployer.deploy() renvoie False
        -> le rapport final est bien retourné (pas d'exception), en
        échec phase CONFIG, et les phases suivantes ne sont pas
        déclenchées."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        config_deployer = MagicMock(spec=ConfigDeployer)
        config_deployer.deploy.return_value = False
        secrets_provisioner = MagicMock(spec=SecretsProvisioner)
        timer_deployer = MagicMock(spec=TimerDeployer)
        config = _make_config_with_phases(
            config_deploy=_CONFIG_SPEC,
            secrets=_SECRETS_SPEC,
            timer_deploy=_TIMER_SPEC,
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            config_deployer=config_deployer,
            secrets_provisioner=secrets_provisioner,
            timer_deployer=timer_deployer,
            target_executor=MagicMock(spec=CommandExecutor),
        )

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.CONFIG
        assert any(
            "Dépôt de la config échoué." in m for m in report.messages
        )
        secrets_provisioner.provision.assert_not_called()
        timer_deployer.deploy.assert_not_called()
        installer.prune_backup.assert_not_called()

    def test_phase_secrets_echoue_apres_config_reussie(self) -> None:
        """Échec best-effort en aval : la phase SECRETS échoue après
        un dépôt de config réussi -> le message de succès CONFIG est
        conservé dans le rapport, TIMER n'est pas déclenché."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        config_deployer = MagicMock(spec=ConfigDeployer)
        config_deployer.deploy.return_value = True
        secrets_provisioner = MagicMock(spec=SecretsProvisioner)
        secrets_provisioner.provision.return_value = False
        timer_deployer = MagicMock(spec=TimerDeployer)
        config = _make_config_with_phases(
            config_deploy=_CONFIG_SPEC,
            secrets=_SECRETS_SPEC,
            timer_deploy=_TIMER_SPEC,
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            config_deployer=config_deployer,
            secrets_provisioner=secrets_provisioner,
            timer_deployer=timer_deployer,
            target_executor=MagicMock(spec=CommandExecutor),
        )

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.SECRETS
        assert "Config déployée." in report.messages
        assert any(
            "Provisioning des secrets échoué." in m
            for m in report.messages
        )
        timer_deployer.deploy.assert_not_called()

    def test_phase_timer_echoue_apres_config_et_secrets_reussis(
        self,
    ) -> None:
        """Échec best-effort en fin de chaîne : TIMER échoue après
        CONFIG et SECRETS réussis -> les deux messages de succès sont
        conservés dans le rapport final."""
        transport, installer, verifier = (
            _make_successful_base_collaborators()
        )
        config_deployer = MagicMock(spec=ConfigDeployer)
        config_deployer.deploy.return_value = True
        secrets_provisioner = MagicMock(spec=SecretsProvisioner)
        secrets_provisioner.provision.return_value = True
        timer_deployer = MagicMock(spec=TimerDeployer)
        timer_deployer.deploy.return_value = False
        config = _make_config_with_phases(
            config_deploy=_CONFIG_SPEC,
            secrets=_SECRETS_SPEC,
            timer_deploy=_TIMER_SPEC,
        )
        deployer = Deployer(
            transport,
            installer,
            verifier,
            config_deployer=config_deployer,
            secrets_provisioner=secrets_provisioner,
            timer_deployer=timer_deployer,
            target_executor=MagicMock(spec=CommandExecutor),
        )

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.TIMER
        assert "Config déployée." in report.messages
        assert "Secrets provisionnés." in report.messages
        assert any(
            "Installation du service+timer échouée." in m
            for m in report.messages
        )
