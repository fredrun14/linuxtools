"""Tests pour le module deploy.deployer."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
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
        installer.backup_venv.return_value = Path("/opt/app/venv.bak-1")
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
        installer.backup_venv.return_value = Path("/opt/app/venv.bak-1")
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
        installer.backup_venv.return_value = Path("/opt/app/venv.bak-1")
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
        deployer = Deployer(transport, installer, verifier, dry_run=True)

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
        deployer = Deployer(transport, installer, verifier, dry_run=True)

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
        deployer = Deployer(transport, installer, verifier, dry_run=True)
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
        deployer = Deployer(transport, installer, verifier, dry_run=True)
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

    def test_dry_run_atomic_swap_affiche_planned_steps(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """atomic_swap=True : le dry-run affiche les étapes de
        VenvReleaser.planned_steps (construction versionnée, bascule,
        purge) au lieu de backup/rm/venv en place."""
        transport, installer, verifier = _make_collaborators()
        deployer = Deployer(transport, installer, verifier, dry_run=True)
        base = _make_config(source_dir=tmp_path)
        config = DeployConfig(
            source_dir=base.source_dir,
            venv_path=base.venv_path,
            remote_source_dir=base.remote_source_dir,
            target=base.target,
            verification=base.verification,
            cli_bin=base.cli_bin,
            atomic_swap=True,
            keep_versions=3,
        )

        deployer.deploy(config)

        out = capsys.readouterr().out
        assert "bascule atomique" in out
        assert "conserve 3 versions" in out
        assert f"rm -rf {base.venv_path}" not in out


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
        assert any("auto-détecté" in m for m in report.messages)
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

        config = _make_config(source_dir=Path("/inexistant/source-dir"))

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
        assert deployer._transport._local is (deployer._installer._executor)
        assert deployer._installer._executor is (deployer._verifier._executor)

    def test_for_target_remote_utilise_ssh_command_executor(self) -> None:
        """Cible distante : installer/verifier reçoivent un
        SshCommandExecutor."""
        from linuxtools.deploy.ssh_executor import SshCommandExecutor

        deployer = Deployer.for_target(DeployTarget(host="srv01"))

        assert isinstance(deployer._installer._executor, SshCommandExecutor)
        assert isinstance(deployer._verifier._executor, SshCommandExecutor)

    def test_for_target_propage_dry_run(self) -> None:
        """dry_run est propagé au Deployer construit."""
        deployer = Deployer.for_target(DeployTarget(), dry_run=True)
        assert deployer._dry_run is True

    def test_for_target_avec_factory_construit_un_secrets_provisioner(
        self,
    ) -> None:
        """credential_manager_factory fourni -> un SecretsProvisioner
        est construit (phase SECRETS activable)."""
        deployer = Deployer.for_target(
            DeployTarget(),
            credential_manager_factory=lambda service: MagicMock(),
        )
        assert deployer._secrets_provisioner is not None


def _make_config_with_phases(**overrides: object) -> DeployConfig:
    """Étend _make_config() avec les specs des 3 nouvelles phases."""
    return replace(_make_config(), **overrides)  # type: ignore[arg-type]


def _make_successful_base_collaborators() -> tuple[
    MagicMock, MagicMock, MagicMock
]:
    """Transport/installer/verifier scriptés en succès jusqu'à VERIFY,
    prêts pour enchaîner sur les phases CONFIG/SECRETS/TIMER."""
    transport, installer, verifier = _make_collaborators()
    transport.transfer.return_value = _result(success=True)
    installer.backup_venv.return_value = None
    installer.install.return_value = _result(success=True)
    verifier.verify.return_value = [CheckResult(label="import app", ok=True)]
    return transport, installer, verifier


_CONFIG_SPEC = ConfigDeploySpec(
    data={"a": 1}, dest_path=Path("/etc/app/config.toml")
)
_SECRETS_SPEC = SecretsSpec(
    keys=(("svc", "TOKEN"),),
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
        transport, installer, verifier = _make_successful_base_collaborators()
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
        transport, installer, verifier = _make_successful_base_collaborators()
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
        transport, installer, verifier = _make_successful_base_collaborators()
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
        transport, installer, verifier = _make_successful_base_collaborators()
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
        transport, installer, verifier = _make_successful_base_collaborators()
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
        assert any("TimerDeployer non configuré" in m for m in report.messages)

    def test_phase_config_echoue_arrete_avant_secrets_et_timer(
        self,
    ) -> None:
        """Échec best-effort : ConfigDeployer.deploy() renvoie False
        -> le rapport final est bien retourné (pas d'exception), en
        échec phase CONFIG, et les phases suivantes ne sont pas
        déclenchées."""
        transport, installer, verifier = _make_successful_base_collaborators()
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
        assert any("Dépôt de la config échoué." in m for m in report.messages)
        secrets_provisioner.provision.assert_not_called()
        timer_deployer.deploy.assert_not_called()
        installer.prune_backup.assert_not_called()

    def test_phase_secrets_echoue_apres_config_reussie(self) -> None:
        """Échec best-effort en aval : la phase SECRETS échoue après
        un dépôt de config réussi -> le message de succès CONFIG est
        conservé dans le rapport, TIMER n'est pas déclenché."""
        transport, installer, verifier = _make_successful_base_collaborators()
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
            "Provisioning des secrets échoué." in m for m in report.messages
        )
        timer_deployer.deploy.assert_not_called()

    def test_phase_timer_echoue_apres_config_et_secrets_reussis(
        self,
    ) -> None:
        """Échec best-effort en fin de chaîne : TIMER échoue après
        CONFIG et SECRETS réussis -> les deux messages de succès sont
        conservés dans le rapport final."""
        transport, installer, verifier = _make_successful_base_collaborators()
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


class TestDeployerDeployAtomicSwap:
    """Tests pour la branche atomic_swap de Deployer.deploy() (T8)."""

    def test_atomic_swap_sans_releaser_echoue_proprement(self) -> None:
        """atomic_swap=True sans releaser injecté : échec propre en
        phase INSTALL, pas d'exception."""
        transport, installer, verifier = _make_successful_base_collaborators()
        deployer = Deployer(transport, installer, verifier)
        config = replace(_make_config(), atomic_swap=True)

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.INSTALL
        assert any("VenvReleaser" in m for m in report.messages)

    def test_atomic_swap_succes_delegue_au_releaser(self) -> None:
        """atomic_swap=True avec releaser : delegue à release(),
        rapport DONE avec active_version/fallback_version."""
        transport, installer, verifier = _make_successful_base_collaborators()
        releaser = MagicMock()
        active = Path("/opt/app/venvs/venv-20260929-000000-000000")
        fallback = Path("/opt/app/venvs/venv-20260901-000000-000000")
        releaser.release.return_value = SimpleNamespace(
            success=True,
            phase_reached=DeployPhase.DONE,
            checks=(CheckResult(label="import app", ok=True),),
            active_version=active,
            fallback_version=fallback,
            messages=(),
        )
        deployer = Deployer(transport, installer, verifier, releaser=releaser)
        config = replace(_make_config(), atomic_swap=True)

        report = deployer.deploy(config)

        assert report.success is True
        assert report.phase_reached is DeployPhase.DONE
        assert report.active_version == active
        assert report.fallback_version == fallback
        installer.install.assert_not_called()

    def test_atomic_swap_echec_release_traduit_en_rapport(self) -> None:
        """Un ReleaseOutcome en échec est traduit fidèlement en
        DeployReport (phase, checks, messages)."""
        transport, installer, verifier = _make_successful_base_collaborators()
        releaser = MagicMock()
        releaser.release.return_value = SimpleNamespace(
            success=False,
            phase_reached=DeployPhase.VERIFY,
            checks=(CheckResult(label="import app", ok=False),),
            active_version=None,
            fallback_version=None,
            messages=("Vérification post-install échouée.",),
        )
        deployer = Deployer(transport, installer, verifier, releaser=releaser)
        config = replace(_make_config(), atomic_swap=True)

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.VERIFY
        assert "Vérification post-install échouée." in report.messages

    def test_atomic_swap_recreate_venv_ajoute_un_message(self) -> None:
        """recreate_venv=True + atomic_swap=True : message d'info,
        release() est quand même appelé (recreate ignoré)."""
        transport, installer, verifier = _make_successful_base_collaborators()
        releaser = MagicMock()
        releaser.release.return_value = SimpleNamespace(
            success=True,
            phase_reached=DeployPhase.DONE,
            checks=(),
            active_version=Path("/opt/app/venvs/venv-1"),
            fallback_version=None,
            messages=(),
        )
        deployer = Deployer(transport, installer, verifier, releaser=releaser)
        config = replace(_make_config(), atomic_swap=True, recreate_venv=True)

        report = deployer.deploy(config)

        assert any("recreate_venv ignoré" in m for m in report.messages)

    def test_atomic_swap_rebase_verification_avant_verify(self) -> None:
        """La fonction verify passée à release() redirige les
        vérifications sur la version (rebase_verification)."""
        transport, installer, verifier = _make_successful_base_collaborators()
        verifier.verify.return_value = [
            CheckResult(label="import app", ok=True)
        ]
        releaser = MagicMock()
        version = Path("/opt/app/venvs/venv-20260929-000000-000000")

        def _release(
            venv_path: Path,
            source_dir: Path,
            verify: Callable[[Path], object],
            keep_versions: int,
        ) -> SimpleNamespace:
            """Simule VenvReleaser.release en rappelant verify()."""
            checks = verify(version)
            return SimpleNamespace(
                success=True,
                phase_reached=DeployPhase.DONE,
                checks=checks,
                active_version=version,
                fallback_version=None,
                messages=(),
            )

        releaser.release.side_effect = _release
        deployer = Deployer(transport, installer, verifier, releaser=releaser)
        # cli_bin absolu égal à venv_path (cas backup-py-manager,
        # conception §7) : sans rebase_verification, viserait encore
        # le venv actif au lieu de la version en cours de vérif.
        config = replace(
            _make_config(), atomic_swap=True, cli_bin="/opt/app/venv"
        )

        deployer.deploy(config)

        verifier.verify.assert_called_once()
        call_args = verifier.verify.call_args.args
        assert call_args[0] == version
        assert call_args[2] == str(version)

    def test_atomic_swap_echec_post_install_conserve_les_versions(
        self,
    ) -> None:
        """release() réussit mais une phase post-install (CONFIG)
        échoue : le rapport d'échec porte quand même active_version/
        fallback_version (mode atomic_swap, pas de rebascule mais le
        lien a bien bougé — l'appelant doit pouvoir le savoir)."""
        transport, installer, verifier = _make_successful_base_collaborators()
        releaser = MagicMock()
        active = Path("/opt/app/venvs/venv-20260929-000000-000000")
        fallback = Path("/opt/app/venvs/venv-20260901-000000-000000")
        releaser.release.return_value = SimpleNamespace(
            success=True,
            phase_reached=DeployPhase.DONE,
            checks=(CheckResult(label="import app", ok=True),),
            active_version=active,
            fallback_version=fallback,
            messages=(),
        )
        deployer = Deployer(transport, installer, verifier, releaser=releaser)
        config = replace(
            _make_config(), atomic_swap=True, config_deploy=_CONFIG_SPEC
        )

        report = deployer.deploy(config)

        assert report.success is False
        assert report.phase_reached is DeployPhase.CONFIG
        assert report.active_version == active
        assert report.fallback_version == fallback


class TestDeployerForTargetAtomicSwap:
    """Tests pour Deployer.for_target() et le releaser construit."""

    def test_for_target_construit_un_releaser(self) -> None:
        """for_target construit toujours un VenvReleaser, injecté."""
        deployer = Deployer.for_target(DeployTarget())
        assert deployer._releaser is not None
