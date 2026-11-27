"""Les unités générées par l'installeur sont relues par systemd lui-même (F08)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.jobnotify import installer as installer_module
from linuxtools.jobnotify.installer import NotifiedJobInstaller
from linuxtools.jobnotify.spec import (
    FingerprintProbe,
    NotifiedJob,
    Outcome,
)
from linuxtools.logging.base import Logger
from linuxtools.systemd.executor import SystemdExecutor
from tests.unit.jobnotify.systemd_support import user_manager

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("systemd-analyze") is None, reason="systemd-analyze absent"
    ),
]

_GUARD = "demo-app-demo-guard.service"


@pytest.fixture(autouse=True)
def _non_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le test ne dépend pas de l'uid réel (la CI peut tourner en root)."""
    monkeypatch.setattr(installer_module, "_is_root", lambda: False)


def _verify(*units: Path) -> subprocess.CompletedProcess[str]:
    """`systemd-analyze --user verify` : relit la grammaire des fichiers d'unité."""
    systemd_analyze = shutil.which("systemd-analyze")
    assert systemd_analyze is not None
    return subprocess.run(  # noqa: S603 - argv fixe, fichiers écrits par le test
        [systemd_analyze, "--user", "verify", *map(str, units)],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def _install(tmp_path: Path, scope: str) -> tuple[Path, Path]:
    """Installe un job avec verrou et sonde à instantané ; rend (compagnon, drop-in).

    Le service surveillé n'est pas un artefact de l'installeur : un service
    minimal le remplace, et le drop-in est vérifié comme un service complet
    (un drop-in n'est pas lu isolément par `verify`).
    """
    job = NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="user" if scope == "user" else "system",
        start_texts=("Début", "Corps"),
        end_texts=dict.fromkeys(Outcome, ("Fin", "Corps")),
        lock=True,
        probe=FingerprintProbe(argv=("/usr/bin/flatpak", "list")),
    )
    logger = MagicMock(spec=Logger)
    if scope == "user":
        home = tmp_path / "home"
        home.mkdir()
        # Le gestionnaire réel n'est pas sollicité : faux gestionnaire partagé
        user = user_manager(home)
        unit_dir = home / ".config/systemd/user"
        NotifiedJobInstaller(job, user, logger, home=home).sync(
            enabled=True, dry_run=False
        )
    else:
        system = MagicMock(spec=SystemdExecutor)
        system.get_status.return_value = "inactive"
        system.reload_systemd.return_value = True
        NotifiedJobInstaller(job, system, logger, root_dir=tmp_path).sync(
            enabled=True, dry_run=False
        )
        unit_dir = tmp_path / "etc/systemd/system"
    dropin = unit_dir / "demo.service.d/demo-app-notify.conf"
    watched = tmp_path / "service" / "demo.service"
    watched.parent.mkdir()
    watched.write_text(
        dropin.read_text(encoding="utf-8") + "ExecStart=/usr/bin/sleep 1\n",
        encoding="utf-8",
    )
    return unit_dir / _GUARD, watched


@pytest.mark.parametrize("scope", ["system", "user"])
def test_unites_generees_acceptees_par_systemd_analyze(
    tmp_path: Path, scope: str
) -> None:
    # Arrange : compagnon (`--why` avec espaces, entre guillemets) et drop-in
    guard, watched = _install(tmp_path, scope)

    # Act
    completed = _verify(watched, guard)

    # Assert
    assert completed.returncode == 0, completed.stderr
    assert "Unbalanced quoting" not in completed.stderr


def test_systemd_analyze_refuse_un_why_mal_cite(tmp_path: Path) -> None:
    # Arrange : témoin négatif, prouve que la vérification lit bien le compagnon
    guard, _ = _install(tmp_path, "user")
    guard.write_text(
        guard.read_text(encoding="utf-8").replace(
            '"--why=Mise à jour en cours"', '--why=Mise à jour "en cours'
        ),
        encoding="utf-8",
    )

    # Act
    completed = _verify(guard)

    # Assert
    assert completed.returncode != 0
    assert "Unbalanced quoting" in completed.stderr
