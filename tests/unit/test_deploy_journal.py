"""Tests pour le module deploy.journal."""

import os
import re
import stat
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.journal import DeployJournal, open_deploy_journal
from linuxtools.deploy.models import (
    CheckResult,
    DeployConfig,
    DeployTarget,
    SecretsSpec,
    VerificationSpec,
)
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner
from linuxtools.deploy.transport import Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.logging.file_logger import FileLogger

_SENTINELLE = "SENTINELLE-secret-journal-77c1"


def _ok() -> CommandResult:
    """Résultat de commande en succès."""
    return CommandResult(
        command=(),
        return_code=0,
        stdout="",
        stderr="",
        success=True,
        duration=0.01,
    )


class TestOpenDeployJournal:
    """Ouverture du journal d'un déploiement."""

    @pytest.mark.parametrize("label", ["../x", "a b", "a/b", "", "a%h", "x\n"])
    def test_open_deploy_journal_rejette_label_traversant(
        self, tmp_path: Path, label: str
    ) -> None:
        """SEC : label invalide -> ValueError avant tout accès disque."""
        with pytest.raises(ValueError):
            open_deploy_journal(
                "bpm", label, dry_run=False, log_dir=tmp_path / "logs"
            )

        assert not (tmp_path / "logs").exists()

    def test_open_deploy_journal_rejette_app_name_invalide(
        self, tmp_path: Path
    ) -> None:
        """SEC : app_name invalide -> ValueError."""
        with pytest.raises(ValueError):
            open_deploy_journal(
                "../bpm", "nas", dry_run=False, log_dir=tmp_path
            )

    def test_open_deploy_journal_cree_fichier_0600_dans_dossier_0700(
        self, tmp_path: Path
    ) -> None:
        """F-14 : fichier 0600 dans <log_dir>/deploy en 0700."""
        journal = open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )
        journal.logger.log_info("bonjour")

        assert isinstance(journal, DeployJournal)
        assert isinstance(journal.logger, FileLogger)
        assert journal.path is not None
        assert journal.path.parent == tmp_path / "logs" / "deploy"
        assert stat.S_IMODE(journal.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(journal.path.parent.stat().st_mode) == 0o700
        assert "bonjour" in journal.path.read_text(encoding="utf-8")

    def test_open_deploy_journal_resserre_un_dossier_existant_en_0700(
        self, tmp_path: Path
    ) -> None:
        """SEC : un dossier deploy/ permissif est resserré."""
        base = tmp_path / "logs" / "deploy"
        base.mkdir(parents=True)
        os.chmod(base, 0o755)

        open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )

        assert stat.S_IMODE(base.stat().st_mode) == 0o700

    def test_open_deploy_journal_refuse_dossier_lien_symbolique(
        self, tmp_path: Path
    ) -> None:
        """SEC : deploy/ lien symbolique -> OSError, rien créé."""
        ailleurs = tmp_path / "ailleurs"
        ailleurs.mkdir()
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "deploy").symlink_to(ailleurs)

        with pytest.raises(OSError, match="lien symbolique"):
            open_deploy_journal("bpm", "nas", dry_run=False, log_dir=logs)

        assert list(ailleurs.iterdir()) == []

    def test_open_deploy_journal_refuse_parent_lien_symbolique(
        self, tmp_path: Path
    ) -> None:
        """SEC : log_dir lui-même lien symbolique -> OSError."""
        ailleurs = tmp_path / "ailleurs"
        ailleurs.mkdir()
        logs = tmp_path / "logs"
        logs.symlink_to(ailleurs)

        with pytest.raises(OSError, match="lien symbolique"):
            open_deploy_journal("bpm", "nas", dry_run=False, log_dir=logs)

        assert list(ailleurs.iterdir()) == []

    @staticmethod
    def _vieux_fichier(chemin: Path, jours: int) -> Path:
        """Crée un fichier dont la date de modification est simulée."""
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("ancien", encoding="utf-8")
        t = time.time() - jours * 86_400
        os.utime(chemin, (t, t))
        return chemin

    def test_open_deploy_journal_purge_anciens_journaux_par_defaut(
        self, tmp_path: Path
    ) -> None:
        """A-04 : journal de 91 j supprimé, autre fichier et récent gardés."""
        base = tmp_path / "logs" / "deploy"
        vieux = self._vieux_fichier(
            base / "deploy_nas_20200101_000000Z.log", 91
        )
        autre = self._vieux_fichier(base / "notes.txt", 400)
        recent = self._vieux_fichier(
            base / "deploy_nas_20260101_000000Z.log", 5
        )

        open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )

        assert not vieux.exists()
        assert autre.exists()
        assert recent.exists()

    def test_open_deploy_journal_purge_garde_le_nouveau_journal(
        self, tmp_path: Path
    ) -> None:
        """F-04 : le journal créé n'est jamais purgé, même à 1 jour."""
        journal = open_deploy_journal(
            "bpm",
            "nas",
            dry_run=False,
            log_dir=tmp_path / "logs",
            retention_days=1,
        )

        assert journal.path is not None
        assert journal.path.exists()

    def test_open_deploy_journal_retention_none_ne_purge_pas(
        self, tmp_path: Path
    ) -> None:
        """A-06 : retention_days=None désactive la purge."""
        base = tmp_path / "logs" / "deploy"
        vieux = self._vieux_fichier(
            base / "deploy_nas_20200101_000000Z.log", 400
        )

        open_deploy_journal(
            "bpm",
            "nas",
            dry_run=False,
            log_dir=tmp_path / "logs",
            retention_days=None,
        )

        assert vieux.exists()

    def test_open_deploy_journal_dry_run_ne_purge_pas(
        self, tmp_path: Path
    ) -> None:
        """A-07 : en dry-run, un vieux journal présent reste en place."""
        base = tmp_path / "logs" / "deploy"
        vieux = self._vieux_fichier(
            base / "deploy_nas_20200101_000000Z.log", 400
        )

        open_deploy_journal(
            "bpm", "nas", dry_run=True, log_dir=tmp_path / "logs"
        )

        assert vieux.exists()

    def test_open_deploy_journal_ne_leve_pas_si_purge_echoue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A-05 : une suppression refusée n'empêche pas d'ouvrir le journal."""
        base = tmp_path / "logs" / "deploy"
        vieux = self._vieux_fichier(
            base / "deploy_nas_20200101_000000Z.log", 400
        )

        def refuser(self: Path, missing_ok: bool = False) -> None:
            raise PermissionError("refusé")

        monkeypatch.setattr(Path, "unlink", refuser)

        journal = open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )

        assert journal.path is not None
        assert vieux.exists()

    def test_open_deploy_journal_signale_les_fichiers_supprimes(
        self, tmp_path: Path
    ) -> None:
        """F-07 : le journal note le nombre purgé, sans nom de fichier."""
        base = tmp_path / "logs" / "deploy"
        self._vieux_fichier(
            base / "deploy_secret-nom_20200101_000000Z.log", 400
        )

        journal = open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )

        assert journal.path is not None
        contenu = journal.path.read_text(encoding="utf-8")
        assert "Rétention : 1 ancien(s) journal(aux) supprimé(s)" in contenu
        assert "secret-nom" not in contenu

    def test_open_deploy_journal_rejette_retention_invalide(
        self, tmp_path: Path
    ) -> None:
        """retention_days=0 -> ValueError, aucun dossier créé."""
        with pytest.raises(ValueError):
            open_deploy_journal(
                "bpm",
                "nas",
                dry_run=False,
                log_dir=tmp_path / "logs",
                retention_days=0,
            )

        assert not (tmp_path / "logs").exists()

    def test_open_deploy_journal_dry_run_ne_cree_aucun_fichier(
        self, tmp_path: Path
    ) -> None:
        """A-08 : dry-run -> ConsoleLogger, path None, disque intact."""
        journal = open_deploy_journal(
            "bpm", "nas", dry_run=True, log_dir=tmp_path / "logs"
        )

        assert isinstance(journal.logger, ConsoleLogger)
        assert journal.path is None
        assert not (tmp_path / "logs").exists()

    def test_open_deploy_journal_nom_horodate_et_label(
        self, tmp_path: Path
    ) -> None:
        """Nommage : deploy_<label>_<AAAAMMJJ_HHMMSS>Z.log (Z = UTC)."""
        journal = open_deploy_journal(
            "bpm", "nas-01", dry_run=False, log_dir=tmp_path
        )

        assert journal.path is not None
        assert re.fullmatch(
            r"deploy_nas-01_\d{8}_\d{6}Z\.log", journal.path.name
        )

    def test_open_deploy_journal_log_dir_par_defaut(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sans log_dir : dossier par défaut de l'application."""
        monkeypatch.setattr(
            "linuxtools.deploy.journal.default_log_dir",
            lambda app: tmp_path / app,
        )

        journal = open_deploy_journal("bpm", "nas", dry_run=False)

        assert journal.path is not None
        assert journal.path.parent == tmp_path / "bpm" / "deploy"

    def test_journal_ne_contient_aucune_valeur_sentinelle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A-13 : un déploiement via Deployer ne journalise aucun secret.

        La sentinelle est dans l'environnement du poste ; le journal doit
        contenir une ligne attendue (le test ne passe pas à vide) et pas
        la sentinelle.
        """
        monkeypatch.setenv("GOTIFY_TOKEN", _SENTINELLE)
        journal = open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )
        transport = MagicMock(spec=Transport)
        transport.transfer.return_value = _ok()
        installer = MagicMock(spec=VenvInstaller)
        installer.backup_venv.return_value = None
        installer.install.return_value = _ok()
        verifier = MagicMock(spec=InstallVerifier)
        verifier.verify.return_value = [CheckResult(label="import", ok=True)]
        # Exécuteur de la cible distante : la sonde répond « ambigu » (2)
        sonde = MagicMock(spec=CommandExecutor)
        sonde.run.return_value = CommandResult(
            command=(),
            return_code=2,
            stdout="",
            stderr="",
            success=False,
            duration=0.01,
        )

        def deployer_pour(executor: MagicMock) -> Deployer:
            return Deployer(
                transport,
                installer,
                verifier,
                logger=journal.logger,
                secrets_provisioner=SecretsProvisioner(None, journal.logger),
                target_executor=executor,
            )

        def config(dest: Path, target: DeployTarget) -> DeployConfig:
            return DeployConfig(
                source_dir=Path(__file__).parent,
                venv_path=Path("/opt/app/venv"),
                remote_source_dir=Path("/opt/app/src"),
                target=target,
                verification=VerificationSpec(imports=("app",)),
                cli_bin="app-cli",
                secrets=SecretsSpec(
                    keys=(("bpm", "GOTIFY_TOKEN"),),
                    dest_path=dest,
                    values_from="target",
                ),
            )

        ok = deployer_pour(MagicMock(spec=CommandExecutor)).deploy(
            config(tmp_path / "secrets.env", DeployTarget())
        )
        # Chemin d'erreur : sonde distante ambiguë -> ligne d'erreur loguée
        ko = deployer_pour(sonde).deploy(
            config(Path("/etc/app/s.env"), DeployTarget(host="srv"))
        )

        assert ok.success is True
        assert ko.success is False
        assert journal.path is not None
        contenu = journal.path.read_text(encoding="utf-8")
        assert "ERROR" in contenu
        assert "Sonde d'existence ambiguë" in contenu
        assert _SENTINELLE not in contenu
        assert _SENTINELLE not in (tmp_path / "secrets.env").read_text(
            encoding="utf-8"
        )
