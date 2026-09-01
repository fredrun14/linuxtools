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

    Déploiement complet (config TOML + secrets + service/timer) :

        from pathlib import Path
        from linuxtools.credentials import CredentialManager
        from linuxtools.deploy import (
            ConfigDeploySpec,
            Deployer,
            DeployConfig,
            DeployTarget,
            SecretsSpec,
            TimerDeploySpec,
            VerificationSpec,
        )
        from linuxtools.systemd import ServiceConfig, TimerConfig

        target = DeployTarget()  # local
        credentials = CredentialManager.from_dotenv(
            service="mon-outil",
            dotenv_path=Path("config/.env"),
        )
        deployer = Deployer.for_target(
            target, credential_manager=credentials
        )
        report = deployer.deploy(
            DeployConfig(
                source_dir=Path("/home/user/mon-outil"),
                venv_path=Path("/opt/mon-outil/venv"),
                remote_source_dir=Path("/opt/mon-outil/src"),
                verification=VerificationSpec(
                    imports=("mon_outil",),
                ),
                config_deploy=ConfigDeploySpec(
                    data={"backup": {"target": "/mnt/nas"}},
                    dest_path=Path("/etc/mon-outil/config.toml"),
                ),
                secrets=SecretsSpec(
                    service="mon-outil",
                    keys=("GOTIFY_TOKEN",),
                    dest_path=Path("/etc/mon-outil/secrets.env"),
                ),
                timer_deploy=TimerDeploySpec(
                    unit_name="mon-outil",
                    service_config=ServiceConfig(
                        exec_start="/opt/mon-outil/venv/bin/mon-outil",
                        environment_file="/etc/mon-outil/secrets.env",
                    ),
                    timer_config=TimerConfig(
                        unit="mon-outil.service",
                        on_calendar="daily",
                    ),
                ),
            )
        )
        print(report.format_summary())

    Préparation d'une clé USB de déploiement offline (aucun hôte
    distant — voir `usb_export.py` pour le détail des deux modes) :

        from pathlib import Path
        from linuxtools.deploy import UsbExportConfig, UsbExporter
        from linuxtools.commands import LinuxCommandExecutor

        exporter = UsbExporter(LinuxCommandExecutor())
        report = exporter.export(
            UsbExportConfig(
                target_dir=Path("/run/media/user/USB/mon-outil"),
                mode="sources",
            )
        )
        print(report.created_paths)
"""

from linuxtools.deploy.cli import CheckVersionCommand, DeployCommand
from linuxtools.deploy.config_deployer import ConfigDeployer
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.discovery import (
    find_editable_source,
    find_project_source,
)
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    CheckResult,
    ConfigDeploySpec,
    DeployConfig,
    DeployPhase,
    DeployReport,
    DeployTarget,
    SecretsSpec,
    TimerDeploySpec,
    VerificationSpec,
    VersionCheckResult,
)
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner
from linuxtools.deploy.ssh_executor import SshCommandExecutor
from linuxtools.deploy.timer_deployer import TimerDeployer
from linuxtools.deploy.transport import RsyncTransport, Transport
from linuxtools.deploy.usb_export import (
    UsbExportConfig,
    UsbExporter,
    UsbExportMode,
    UsbExportReport,
)
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier
from linuxtools.deploy.version_checker import (
    VersionChecker,
    check_target_version,
    read_source_version,
)

__all__ = [
    "CheckResult",
    "CheckVersionCommand",
    "ConfigDeploySpec",
    "ConfigDeployer",
    "DeployCommand",
    "DeployConfig",
    "DeployError",
    "DeployPhase",
    "DeployReport",
    "DeployTarget",
    "Deployer",
    "InstallVerifier",
    "RsyncTransport",
    "SecretsProvisioner",
    "SecretsSpec",
    "SshCommandExecutor",
    "TimerDeploySpec",
    "TimerDeployer",
    "Transport",
    "UsbExportConfig",
    "UsbExportMode",
    "UsbExportReport",
    "UsbExporter",
    "VenvInstaller",
    "VerificationSpec",
    "VersionChecker",
    "VersionCheckResult",
    "check_target_version",
    "find_editable_source",
    "find_project_source",
    "read_source_version",
]
