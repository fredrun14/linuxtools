"""Déployeur/updateur d'outil Python sur hôte (local ou distant).

Orchestre 4 phases : transport → (ré)installation venv →
vérification déclarative → rollback automatique. Utilisable en API
Python et en CLI, en local et via SSH.

Example:
    Déploiement local :

        from pathlib import Path
        from linuxtools.deploy import (
            Deployer, DeployConfig, DeployTarget, VerificationSpec,
        )

        target = DeployTarget()  # local
        deployer = Deployer.for_target(target)
        report = deployer.deploy(
            DeployConfig(
                source_dir=Path("/home/user/mon-outil"),
                venv_path=Path("/opt/mon-outil/venv"),
                remote_source_dir=Path("/opt/mon-outil/src"),
                verification=VerificationSpec(
                    imports=("mon_outil",),
                ),
            )
        )
        print(report.format_summary())
"""

from linuxtools.deploy.cli import DeployCommand
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.discovery import (
    find_editable_source,
    find_project_source,
)
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    CheckResult,
    DeployConfig,
    DeployPhase,
    DeployReport,
    DeployTarget,
    VerificationSpec,
)
from linuxtools.deploy.ssh_executor import SshCommandExecutor
from linuxtools.deploy.transport import RsyncTransport, Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier

__all__ = [
    "CheckResult",
    "DeployCommand",
    "DeployConfig",
    "DeployError",
    "DeployPhase",
    "DeployReport",
    "DeployTarget",
    "Deployer",
    "InstallVerifier",
    "RsyncTransport",
    "SshCommandExecutor",
    "Transport",
    "VenvInstaller",
    "VerificationSpec",
    "find_editable_source",
    "find_project_source",
]
