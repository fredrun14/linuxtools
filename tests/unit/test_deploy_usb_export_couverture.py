"""Tests de comportement complémentaires pour deploy.usb_export."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.deploy.usb_export import UsbExportConfig, UsbExporter, UsbExportMode
from linuxtools.errors.exceptions import ValidationError
from linuxtools.logging.base import Logger
from tests.unit.couverture_helpers import simule_uv_venv

pytestmark = pytest.mark.usefixtures("usb_isole")


def _messages(logger: MagicMock) -> list[str]:
    """Liste les messages d'information reçus par le logger."""
    return [c.args[0] for c in logger.log_info.call_args_list]


def _config_venv(cible: Path, projet: Path) -> UsbExportConfig:
    """Configuration d'export en mode venv."""
    return UsbExportConfig(
        target_dir=cible,
        mode="venv",
        project_src=projet,
        cli_entry_point="demo.cli:main",
    )


def test_export_sources_avec_logger_trace_les_copies(
    tmp_path: Path, projet_usb: Path, executeur: MagicMock
) -> None:
    """Mode sources : la copie de uv et celle des sources sont journalisées."""
    logger = MagicMock(spec=Logger)
    cible = tmp_path / "usb"

    UsbExporter(executeur, logger).export(
        UsbExportConfig(target_dir=cible, mode="sources", project_src=projet_usb)
    )

    messages = _messages(logger)
    assert f"uv → {cible / 'uv'}" in messages
    assert f"{projet_usb} → {cible / 'demo'}" in messages


def test_export_sources_refuse_un_nom_de_projet_dangereux(
    tmp_path: Path, executeur: MagicMock
) -> None:
    """Un nom de projet avec métacaractère shell est refusé pour install.sh."""
    projet = tmp_path / "mon projet;rm"
    projet.mkdir()
    (projet / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="Nom de projet invalide"):
        UsbExporter(executeur).export(
            UsbExportConfig(
                target_dir=tmp_path / "usb", mode="sources", project_src=projet
            )
        )


def test_export_venv_avec_logger_trace_chaque_etape(
    tmp_path: Path, projet_usb: Path, executeur: MagicMock
) -> None:
    """Mode venv : création, installation, copie et bits d'exécution tracés."""
    logger = MagicMock(spec=Logger)
    cible = tmp_path / "usb"
    executeur.run.side_effect = simule_uv_venv()

    UsbExporter(executeur, logger).export(_config_venv(cible, projet_usb))

    messages = _messages(logger)
    venv = cible / "venv"
    assert f"Création du venv → {venv}" in messages
    assert "Installation des paquets dans le venv…" in messages
    assert f"Copie du venv → {venv}" in messages
    assert f"Bits d'exécution restaurés → {venv / 'bin'}" in messages


def test_export_venv_ignore_les_dossiers_de_bin_et_rend_les_fichiers_executables(
    tmp_path: Path, projet_usb: Path, executeur: MagicMock
) -> None:
    """Dans bin/, les fichiers deviennent exécutables, les dossiers sont laissés."""
    cible = tmp_path / "usb"
    executeur.run.side_effect = simule_uv_venv(dossier_dans_bin=True)

    UsbExporter(executeur).export(_config_venv(cible, projet_usb))

    bin_dir = cible / "venv" / "bin"
    assert (bin_dir / "outil").stat().st_mode & 0o777 == 0o755
    assert (bin_dir / "sous-dossier").is_dir()


def test_export_venv_sans_bin_reussit_sans_restaurer_de_bits(
    tmp_path: Path, projet_usb: Path, executeur: MagicMock
) -> None:
    """Un venv sans bin/ est copié tel quel, sans erreur."""
    cible = tmp_path / "usb"
    executeur.run.side_effect = simule_uv_venv(avec_bin=False)

    report = UsbExporter(executeur).export(_config_venv(cible, projet_usb))

    assert str(cible / "venv") in report.created_paths
    assert not (cible / "venv" / "bin").exists()


@pytest.mark.parametrize("mode", ["sources", "venv"])
def test_dry_run_avec_logger_journalise_les_lignes_du_rapport(
    tmp_path: Path, projet_usb: Path, executeur: MagicMock, mode: UsbExportMode
) -> None:
    """Le dry-run trace chaque ligne du rapport dans le logger."""
    logger = MagicMock(spec=Logger)

    report = UsbExporter(executeur, logger).export(
        UsbExportConfig(
            target_dir=tmp_path / "usb",
            mode=mode,
            project_src=projet_usb,
            cli_entry_point="demo.cli:main",
            dry_run=True,
        )
    )

    assert report.created_paths
    assert set(report.created_paths) <= set(_messages(logger))
