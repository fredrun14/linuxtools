"""Tests pour le module deploy.deployer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from linuxtools.commands.base import CommandResult
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    CheckResult,
    DeployConfig,
    DeployPhase,
    DeployTarget,
    VerificationSpec,
)
from linuxtools.deploy.transport import Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier


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

    def test_deploy_succes_complet(self):
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

    def test_deploy_succes_venv_neuf_pas_de_prune(self):
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

    def test_echec_transport_arrete_avant_backup(self):
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

    def test_echec_backup_arrete_avant_install(self):
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

    def test_echec_install_avec_backup_declenche_rollback(self):
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

    def test_echec_install_sans_backup_pas_de_rollback(self):
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

    def test_echec_install_et_rollback_ko_ajoute_un_message(self):
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

    def test_echec_verify_avec_backup_declenche_rollback(self):
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

    def test_echec_verify_sans_backup_pas_de_rollback(self):
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

    def test_echec_verify_et_rollback_ko_ajoute_un_message(self):
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

    def test_dry_run_ne_touche_aucun_collaborateur(self):
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

    def test_dry_run_affiche_les_operations_simulees(self, capsys):
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
        self, capsys
    ):
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
        self, capsys, tmp_path
    ):
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

    def test_source_dir_none_introuvable(self):
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

    def test_source_dir_none_auto_detecte(self):
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

    def test_source_dir_auto_detecte_inexistant(self):
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

    def test_source_dir_explicite_inexistant(self):
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

    def test_for_target_local_utilise_le_meme_executeur(self):
        """Cible locale : transport/installer/verifier partagent le
        même LinuxCommandExecutor (pas de SshCommandExecutor)."""
        deployer = Deployer.for_target(DeployTarget())

        assert deployer._transport._local is (
            deployer._installer._executor
        )
        assert deployer._installer._executor is (
            deployer._verifier._executor
        )

    def test_for_target_remote_utilise_ssh_command_executor(self):
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

    def test_for_target_propage_dry_run(self):
        """dry_run est propagé au Deployer construit."""
        deployer = Deployer.for_target(DeployTarget(), dry_run=True)
        assert deployer._dry_run is True
