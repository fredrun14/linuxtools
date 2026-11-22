"""Fixtures partagées par les tests de couverture de ``tests/unit``.

Toutes sont explicites (aucune ``autouse``) : un fichier de tests les active
avec ``pytest.mark.usefixtures`` ou en les demandant en paramètre.
"""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.usb_export import UsbExporter
from tests.unit.couverture_helpers import cmd_result
from tests.unit.vaults_helpers import (
    DEFAULT_SETTINGS,
    Settings,
    VaultsEnv,
    conventions_md,
    emplacements_md,
    render_vaults_toml,
)


@pytest.fixture
def usb_isole(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Isole l'export USB de linuxtools et de uv installés sur la machine."""
    faux = tmp_path_factory.mktemp("fake_bin") / "uv"
    faux.write_text("#!/bin/sh\necho uv\n", encoding="utf-8")
    faux.chmod(0o755)
    with (
        patch("linuxtools.deploy.usb_export.find_editable_source", return_value=None),
        patch.object(UsbExporter, "_find_uv", return_value=str(faux)),
    ):
        yield


@pytest.fixture
def projet_usb(tmp_path: Path) -> Path:
    """Projet consommateur factice pour l'export USB."""
    src = tmp_path / "demo"
    src.mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (src / "demo.py").write_text("print('hi')\n", encoding="utf-8")
    return src


@pytest.fixture
def executeur() -> MagicMock:
    """Exécuteur de commandes mocké, succès par défaut."""
    mock = MagicMock(spec=CommandExecutor)
    mock.run.return_value = cmd_result()
    return mock


@pytest.fixture
def vaults_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VaultsEnv:
    """Isole ``HOME`` et ``XDG_CONFIG_HOME`` dans ``tmp_path``."""
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    config_file = config_home / "vault-tools" / "vaults.toml"

    def write_settings(settings: Settings | None = None) -> None:
        """Écrit le TOML de configuration (réglages neutres par défaut)."""
        config_file.parent.mkdir(parents=True, exist_ok=True)
        content = render_vaults_toml(DEFAULT_SETTINGS if settings is None else settings)
        config_file.write_text(content, encoding="utf-8")

    def write_source(name: str, content: str) -> None:
        """Écrit un fichier source sous ``home/sources``."""
        target = home / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def write_emplacements(rows: dict[str, str]) -> None:
        """Écrit le fichier des emplacements."""
        write_source("emplacements.md", emplacements_md(rows))

    def write_conventions(rows: dict[str, list[str]]) -> None:
        """Écrit le fichier des conventions."""
        write_source("conventions.md", conventions_md(rows))

    return VaultsEnv(
        home, config_file, write_settings, write_emplacements, write_conventions
    )
