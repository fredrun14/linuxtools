"""Tests de comportement complémentaires pour deploy.usb_export."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.usb_export import UsbExportConfig, UsbExporter, UsbExportMode
from linuxtools.errors.exceptions import ValidationError
from linuxtools.logging.base import Logger
from tests.unit.test_deploy_usb_export import _cmd_result, _venv_run_side_effect

if TYPE_CHECKING:
    from collections.abc import Iterator

    from linuxtools.commands.base import CommandResult

_MODULE = "linuxtools.deploy.usb_export"


@pytest.fixture(autouse=True)
def _sans_linuxtools_ni_uv_reel(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Isole le test de l'installation de linuxtools et de uv de la machine."""
    faux = tmp_path_factory.mktemp("fake_bin") / "uv"
    faux.write_text("#!/bin/sh\necho uv\n", encoding="utf-8")
    faux.chmod(0o755)
    with (
        patch(f"{_MODULE}.find_editable_source", return_value=None),
        patch.object(UsbExporter, "_find_uv", return_value=str(faux)),
    ):
        yield


@pytest.fixture
def project_src(tmp_path: Path) -> Path:
    """Projet consommateur factice."""
    src = tmp_path / "demo"
    src.mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (src / "demo.py").write_text("print('hi')\n", encoding="utf-8")
    return src


@pytest.fixture
def executor() -> MagicMock:
    """Exécuteur mocké, succès par défaut."""
    mock = MagicMock(spec=CommandExecutor)
    mock.run.return_value = _cmd_result(success=True)
    return mock


def _messages(logger: MagicMock) -> list[str]:
    """Liste les messages d'information reçus par le logger."""
    return [c.args[0] for c in logger.log_info.call_args_list]


def test_export_sources_avec_logger_trace_les_copies(
    tmp_path: Path, project_src: Path, executor: MagicMock
) -> None:
    """Mode sources : la copie de uv et celle des sources sont journalisées."""
    logger = MagicMock(spec=Logger)
    cible = tmp_path / "usb"

    UsbExporter(executor, logger).export(
        UsbExportConfig(target_dir=cible, mode="sources", project_src=project_src)
    )

    messages = _messages(logger)
    assert f"uv → {cible / 'uv'}" in messages
    assert f"{project_src} → {cible / 'demo'}" in messages


def test_export_sources_refuse_un_nom_de_projet_dangereux(
    tmp_path: Path, executor: MagicMock
) -> None:
    """Un nom de projet avec métacaractère shell est refusé pour install.sh."""
    projet = tmp_path / "mon projet;rm"
    projet.mkdir()
    (projet / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="Nom de projet invalide"):
        UsbExporter(executor).export(
            UsbExportConfig(
                target_dir=tmp_path / "usb", mode="sources", project_src=projet
            )
        )


def test_export_venv_avec_logger_trace_chaque_etape(
    tmp_path: Path, project_src: Path, executor: MagicMock
) -> None:
    """Mode venv : création, installation, copie et bits d'exécution tracés."""
    logger = MagicMock(spec=Logger)
    cible = tmp_path / "usb"
    executor.run.side_effect = _venv_run_side_effect()

    UsbExporter(executor, logger).export(
        UsbExportConfig(
            target_dir=cible,
            mode="venv",
            project_src=project_src,
            cli_entry_point="demo.cli:main",
        )
    )

    messages = _messages(logger)
    venv = cible / "venv"
    assert f"Création du venv → {venv}" in messages
    assert "Installation des paquets dans le venv…" in messages
    assert f"Copie du venv → {venv}" in messages
    assert f"Bits d'exécution restaurés → {venv / 'bin'}" in messages


def _venv_avec_bin_contenant_un_dossier(
    command: list[str], *args: object, **kwargs: object
) -> CommandResult:
    """Simule uv : le venv a un bin/ avec un exécutable et un sous-dossier."""
    if command[1:3] == ["venv", "--python"]:
        bin_dir = Path(command[-1]) / "bin"
        (bin_dir / "sous-dossier").mkdir(parents=True)
        outil = bin_dir / "outil"
        outil.write_text("#!/bin/sh\n", encoding="utf-8")
        outil.chmod(0o644)
    return _cmd_result(success=True, command=tuple(command))


def _venv_sans_bin(
    command: list[str], *args: object, **kwargs: object
) -> CommandResult:
    """Simule uv : le venv créé n'a pas de répertoire bin/."""
    if command[1:3] == ["venv", "--python"]:
        (Path(command[-1]) / "lib").mkdir(parents=True)
    return _cmd_result(success=True, command=tuple(command))


def _config_venv(cible: Path, projet: Path) -> UsbExportConfig:
    """Configuration d'export en mode venv."""
    return UsbExportConfig(
        target_dir=cible,
        mode="venv",
        project_src=projet,
        cli_entry_point="demo.cli:main",
    )


def test_export_venv_ignore_les_dossiers_de_bin_et_rend_les_fichiers_executables(
    tmp_path: Path, project_src: Path, executor: MagicMock
) -> None:
    """Dans bin/, les fichiers deviennent exécutables, les dossiers sont laissés."""
    cible = tmp_path / "usb"
    executor.run.side_effect = _venv_avec_bin_contenant_un_dossier

    UsbExporter(executor).export(_config_venv(cible, project_src))

    bin_dir = cible / "venv" / "bin"
    assert (bin_dir / "outil").stat().st_mode & 0o777 == 0o755
    assert (bin_dir / "sous-dossier").is_dir()


def test_export_venv_sans_bin_reussit_sans_restaurer_de_bits(
    tmp_path: Path, project_src: Path, executor: MagicMock
) -> None:
    """Un venv sans bin/ est copié tel quel, sans erreur."""
    cible = tmp_path / "usb"
    executor.run.side_effect = _venv_sans_bin

    report = UsbExporter(executor).export(_config_venv(cible, project_src))

    assert str(cible / "venv") in report.created_paths
    assert not (cible / "venv" / "bin").exists()


@pytest.mark.parametrize("mode", ["sources", "venv"])
def test_dry_run_avec_logger_journalise_les_lignes_du_rapport(
    tmp_path: Path, project_src: Path, executor: MagicMock, mode: UsbExportMode
) -> None:
    """Le dry-run trace chaque ligne du rapport dans le logger."""
    logger = MagicMock(spec=Logger)

    report = UsbExporter(executor, logger).export(
        UsbExportConfig(
            target_dir=tmp_path / "usb",
            mode=mode,
            project_src=project_src,
            cli_entry_point="demo.cli:main",
            dry_run=True,
        )
    )

    assert set(report.created_paths) <= set(_messages(logger))
