"""Tests de comportement complémentaires pour deploy.deployer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.models import DeployPhase
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner
from tests.unit.test_deploy_deployer import (
    _CONFIG_SPEC,
    _SECRETS_SPEC,
    _TIMER_SPEC,
    _make_collaborators,
    _make_config,
    _make_config_with_phases,
    _make_successful_base_collaborators,
)


def test_source_auto_detectee_sans_logger_figure_dans_le_rapport(
    tmp_path: Path,
) -> None:
    """Sans logger, la source auto-détectée est quand même signalée au rapport."""
    transport, installer, verifier = _make_collaborators()
    deployer = Deployer(transport, installer, verifier, dry_run=True)

    with patch("linuxtools.deploy.deployer.find_project_source", return_value=tmp_path):
        report = deployer.deploy(_make_config(source_dir=None))

    assert report.success is True
    assert f"Source auto-détecté : {tmp_path}" in report.messages


def test_dry_run_annonce_le_depot_de_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le dry-run annonce le dépôt de la config sans l'effectuer."""
    transport, installer, verifier = _make_collaborators()
    deployer = Deployer(transport, installer, verifier, dry_run=True)

    deployer.deploy(_make_config_with_phases(config_deploy=_CONFIG_SPEC))

    assert f"dépôt config -> {_CONFIG_SPEC.dest_path}" in capsys.readouterr().out


def test_secrets_configures_sans_provisionneur_echoue() -> None:
    """Secrets demandés sans SecretsProvisioner : échec propre en phase SECRETS."""
    transport, installer, verifier = _make_successful_base_collaborators()
    deployer = Deployer(
        transport,
        installer,
        verifier,
        target_executor=MagicMock(spec=CommandExecutor),
    )

    report = deployer.deploy(_make_config_with_phases(secrets=_SECRETS_SPEC))

    assert report.success is False
    assert report.phase_reached is DeployPhase.SECRETS
    assert any("SecretsProvisioner non configuré" in m for m in report.messages)


def test_timer_configure_sans_target_executor_echoue() -> None:
    """Timer demandé sans target_executor : échec propre en phase TIMER."""
    transport, installer, verifier = _make_successful_base_collaborators()
    deployer = Deployer(
        transport,
        installer,
        verifier,
        secrets_provisioner=MagicMock(spec=SecretsProvisioner),
    )

    report = deployer.deploy(_make_config_with_phases(timer_deploy=_TIMER_SPEC))

    assert report.success is False
    assert report.phase_reached is DeployPhase.TIMER
    assert any("target_executor non configuré" in m for m in report.messages)
