"""Tests pour le module deploy.journal."""

import os
import re
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.journal import DeployJournal, open_deploy_journal
from linuxtools.deploy.models import DeployTarget, SecretsSpec
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.logging.file_logger import FileLogger

_SENTINELLE = "SENTINELLE-secret-journal-77c1"


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
        """Nommage : deploy_<label>_<AAAAMMJJ_HHMMSS>.log."""
        journal = open_deploy_journal(
            "bpm", "nas-01", dry_run=False, log_dir=tmp_path
        )

        assert journal.path is not None
        assert re.fullmatch(
            r"deploy_nas-01_\d{8}_\d{6}\.log", journal.path.name
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
        """A-13 : un déploiement simulé ne laisse aucun secret du poste."""
        monkeypatch.setenv("GOTIFY_TOKEN", _SENTINELLE)
        journal = open_deploy_journal(
            "bpm", "nas", dry_run=False, log_dir=tmp_path / "logs"
        )
        dest = tmp_path / "secrets.env"
        spec = SecretsSpec(
            keys=(("bpm", "GOTIFY_TOKEN"),),
            dest_path=dest,
            values_from="target",
        )

        outcome = SecretsProvisioner(None, journal.logger).provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )
        # Chemin d'erreur : fichier de secrets illisible côté écriture
        SecretsProvisioner(None, journal.logger).provision(
            SecretsSpec(
                keys=(("bpm", "GOTIFY_TOKEN"),),
                dest_path=tmp_path / "absent" / "s.env",
                values_from="target",
            ),
            DeployTarget(host="srv"),
            MagicMock(spec=CommandExecutor),
        )

        assert outcome.success is True
        assert journal.path is not None
        assert _SENTINELLE not in journal.path.read_text(encoding="utf-8")
