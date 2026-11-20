"""Aides partagées par les tests de couverture ``test_*_couverture.py``."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.commands.base import CommandResult
from linuxtools.deploy.models import (
    CheckResult,
    ConfigDeploySpec,
    DeployConfig,
    DeployTarget,
    SecretsSpec,
    TimerDeploySpec,
    VerificationSpec,
)
from linuxtools.deploy.transport import Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier
from linuxtools.systemd.base import ServiceConfig, TimerConfig

CONFIG_SPEC = ConfigDeploySpec(data={"a": 1}, dest_path=Path("/etc/app/config.toml"))
SECRETS_SPEC = SecretsSpec(
    keys=(("svc", "TOKEN"),),
    dest_path=Path("/etc/app/secrets.env"),
)
TIMER_SPEC = TimerDeploySpec(
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


def cmd_result(
    *, success: bool = True, stdout: str = "", stderr: str = ""
) -> CommandResult:
    """Construit un CommandResult scripté."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout=stdout,
        stderr=stderr,
        success=success,
        duration=0.01,
    )


def make_deploy_config(
    *,
    auto_source: bool = False,
    config_deploy: ConfigDeploySpec | None = None,
    secrets: SecretsSpec | None = None,
    timer_deploy: TimerDeploySpec | None = None,
) -> DeployConfig:
    """Construit une DeployConfig minimale.

    Args:
        auto_source: True pour laisser le déployeur auto-détecter la source
            (``source_dir=None``) ; sinon le dossier des tests est utilisé.
        config_deploy: Spécification du dépôt de config, ou None.
        secrets: Spécification des secrets, ou None.
        timer_deploy: Spécification du service+timer, ou None.
    """
    return DeployConfig(
        source_dir=None if auto_source else Path(__file__).resolve().parent,
        venv_path=Path("/opt/app/venv"),
        remote_source_dir=Path("/opt/app/src"),
        target=DeployTarget(),
        verification=VerificationSpec(imports=("app",)),
        cli_bin="app-cli",
        config_deploy=config_deploy,
        secrets=secrets,
        timer_deploy=timer_deploy,
    )


def make_collaborators() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Crée transport, installer et verifier mockés."""
    return (
        MagicMock(spec=Transport),
        MagicMock(spec=VenvInstaller),
        MagicMock(spec=InstallVerifier),
    )


def make_successful_collaborators() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Collaborateurs scriptés en succès jusqu'à la phase VERIFY."""
    transport, installer, verifier = make_collaborators()
    transport.transfer.return_value = cmd_result()
    installer.backup_venv.return_value = None
    installer.install.return_value = cmd_result()
    verifier.verify.return_value = [CheckResult(label="import app", ok=True)]
    return transport, installer, verifier


def simule_uv_venv(
    *, avec_bin: bool = True, dossier_dans_bin: bool = False
) -> Callable[..., CommandResult]:
    """Fabrique un side_effect simulant ``uv venv`` / ``uv pip install``.

    Args:
        avec_bin: False pour que le venv créé n'ait pas de ``bin/``.
        dossier_dans_bin: True pour ajouter un sous-dossier dans ``bin/``.

    Returns:
        Fonction à poser en ``side_effect`` de ``executor.run`` : ``uv venv``
        crée réellement l'arborescence, le reste est un succès simulé.
    """

    def _run(command: list[str], *args: object, **kwargs: object) -> CommandResult:
        if command[1:3] == ["venv", "--python"]:
            venv = Path(command[-1])
            if avec_bin:
                bin_dir = venv / "bin"
                bin_dir.mkdir(parents=True)
                outil = bin_dir / "outil"
                outil.write_text("#!/bin/sh\n", encoding="utf-8")
                outil.chmod(0o644)
                if dossier_dans_bin:
                    (bin_dir / "sous-dossier").mkdir()
            else:
                (venv / "lib").mkdir(parents=True)
        return cmd_result()

    return _run


def descripteurs_ouverts() -> set[str]:
    """Liste les descripteurs de fichiers ouverts par le processus (Linux)."""
    return {p.name for p in Path("/proc/self/fd").iterdir()}
