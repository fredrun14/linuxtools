"""Non-régression de l'interface : les booléens sont en mot-clé seul."""

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.deployer import Deployer
from linuxtools.logging.file_logger import FileLogger
from linuxtools.systemd.base import MountUnitManager
from linuxtools.systemd.mount import LinuxMountUnitManager

# (callable public, nom du paramètre booléen)
CAS: list[tuple[Callable[..., Any], str]] = [
    (MountUnitManager.enable_mount, "with_automount"),
    (LinuxMountUnitManager.enable_mount, "with_automount"),
    (Deployer.__init__, "dry_run"),
    (FileLogger.__init__, "console_output"),
    (CommandExecutor.run, "probe"),
]


@pytest.mark.parametrize(
    ("fonction", "parametre"),
    CAS,
    ids=[f"{f.__qualname__}.{p}" for f, p in CAS],
)
def test_booleens_sont_mot_cle_seul(
    fonction: Callable[..., Any], parametre: str
) -> None:
    """Le paramètre booléen doit être KEYWORD_ONLY (pas d'appel positionnel)."""
    # Arrange / Act
    kind = inspect.signature(fonction).parameters[parametre].kind

    # Assert
    assert kind is inspect.Parameter.KEYWORD_ONLY
