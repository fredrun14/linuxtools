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
