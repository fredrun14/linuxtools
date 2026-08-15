"""Tests pour le module deploy.cli."""

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.deploy.cli import CheckVersionCommand, DeployCommand
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    DeployPhase,
    DeployReport,
    VersionCheckResult,
)


def _make_parser(command: DeployCommand) -> argparse.ArgumentParser:
    """Construit un ArgumentParser avec la commande deploy enregistrée."""
    parser = argparse.ArgumentParser(prog="test")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command.register(subparsers)
    return parser


class TestDeployCommandName:
    """Tests pour la propriété name."""

    def test_name_est_deploy(self) -> None:
        """Le nom de la sous-commande est 'deploy'."""
        assert DeployCommand().name == "deploy"


class TestDeployCommandRegister:
    """Tests pour register() : arguments argparse."""

    def test_venv_et_dest_sont_requis(self) -> None:
        """--venv et --dest sont requis (SystemExit si absents)."""
        parser = _make_parser(DeployCommand())
        with pytest.raises(SystemExit):
            parser.parse_args(["deploy"])

    def test_parse_arguments_minimaux(self) -> None:
        """Parse avec seulement --venv et --dest requis."""
        parser = _make_parser(DeployCommand())
        args = parser.parse_args(
            ["deploy", "--venv", "/opt/app/venv", "--dest", "/opt/app/src"]
        )
        assert args.venv == Path("/opt/app/venv")
        assert args.dest == Path("/opt/app/src")
        assert args.host is None
        assert args.imports == []
        assert args.subcommands == []
        assert args.recreate_venv is False
        assert args.dry_run is False

    def test_options_repetables(self) -> None:
        """--import, --subcommand et --ssh-option sont répétables."""
        parser = _make_parser(DeployCommand())
        args = parser.parse_args(
            [
                "deploy",
                "--venv", "/opt/app/venv",
                "--dest", "/opt/app/src",
                "--import", "mod_a",
                "--import", "mod_b",
                "--subcommand", "list",
                "--subcommand", "status",
                "--ssh-option=-p",
                "--ssh-option=2222",
            ]
        )
        assert args.imports == ["mod_a", "mod_b"]
        assert args.subcommands == ["list", "status"]
        assert args.ssh_option == ["-p", "2222"]

    def test_dry_run_active(self) -> None:
        """--dry-run active le flag dry_run."""
        parser = _make_parser(DeployCommand())
        args = parser.parse_args(
            [
                "deploy",
                "--venv", "/opt/app/venv",
                "--dest", "/opt/app/src",
                "--dry-run",
            ]
        )
        assert args.dry_run is True

    def test_recreate_venv_active(self) -> None:
        """--recreate-venv active le flag recreate_venv."""
        parser = _make_parser(DeployCommand())
        args = parser.parse_args(
            [
                "deploy",
                "--venv", "/opt/app/venv",
                "--dest", "/opt/app/src",
                "--recreate-venv",
            ]
        )
        assert args.recreate_venv is True


class TestDeployCommandExecute:
    """Tests pour execute() : construction config + délégation."""

    def _base_args(self, **overrides: Any) -> argparse.Namespace:
        """Construit un Namespace minimal valide, avec overrides."""
        base: dict[str, Any] = {
            "source": None,
            "venv": Path("/opt/app/venv"),
            "dest": Path("/opt/app/src"),
            "host": None,
            "user": None,
            "ssh_option": [],
            "cli_bin": None,
            "imports": [],
            "subcommands": [],
            "regression": None,
            "recreate_venv": False,
            "dry_run": False,
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    @patch("linuxtools.deploy.cli.Deployer")
    def test_execute_succes_sort_avec_code_0(
        self, mock_deployer_cls: MagicMock
    ) -> None:
        """Un déploiement réussi termine avec sys.exit(0)."""
        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = DeployReport(
            success=True, phase_reached=DeployPhase.DONE
        )
        mock_deployer_cls.for_target.return_value = mock_deployer

        with pytest.raises(SystemExit) as exc_info:
            DeployCommand().execute(self._base_args())

        assert exc_info.value.code == 0

    @patch("linuxtools.deploy.cli.Deployer")
    def test_execute_echec_sort_avec_code_1(
        self, mock_deployer_cls: MagicMock
    ) -> None:
        """Un déploiement en échec termine avec sys.exit(1)."""
        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = DeployReport(
            success=False, phase_reached=DeployPhase.INSTALL
        )
        mock_deployer_cls.for_target.return_value = mock_deployer

        with pytest.raises(SystemExit) as exc_info:
            DeployCommand().execute(self._base_args())

        assert exc_info.value.code == 1

    @patch("linuxtools.deploy.cli.Deployer")
    def test_execute_construit_la_config_correctement(
        self, mock_deployer_cls: MagicMock
    ) -> None:
        """execute() transmet les bons paramètres à Deployer.deploy."""
        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = DeployReport(
            success=True, phase_reached=DeployPhase.DONE
        )
        mock_deployer_cls.for_target.return_value = mock_deployer

        args = self._base_args(
            host="srv01",
            user="deploy",
            imports=["mod_a"],
            subcommands=["list"],
            cli_bin="mon-cli",
            regression=["mon-cli", "check"],
        )

        with pytest.raises(SystemExit):
            DeployCommand().execute(args)

        config = mock_deployer.deploy.call_args.args[0]
        assert config.venv_path == Path("/opt/app/venv")
        assert config.remote_source_dir == Path("/opt/app/src")
        assert config.target.host == "srv01"
        assert config.target.user == "deploy"
        assert config.verification.imports == ("mod_a",)
        assert config.verification.subcommands == ("list",)
        assert config.verification.regression_command == (
            "mon-cli", "check",
        )
        assert config.cli_bin == "mon-cli"

    @patch("linuxtools.deploy.cli.Deployer")
    def test_execute_propage_dry_run_au_deployer(
        self, mock_deployer_cls: MagicMock
    ) -> None:
        """dry_run est transmis à Deployer.for_target."""
        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = DeployReport(
            success=True, phase_reached=DeployPhase.DONE
        )
        mock_deployer_cls.for_target.return_value = mock_deployer

        with pytest.raises(SystemExit):
            DeployCommand().execute(self._base_args(dry_run=True))

        assert (
            mock_deployer_cls.for_target.call_args.kwargs["dry_run"]
            is True
        )

    @patch("linuxtools.deploy.cli.Deployer")
    def test_execute_affiche_le_resume(
        self, mock_deployer_cls: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """execute() affiche report.format_summary() sur stdout."""
        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = DeployReport(
            success=True, phase_reached=DeployPhase.DONE
        )
        mock_deployer_cls.for_target.return_value = mock_deployer

        with pytest.raises(SystemExit):
            DeployCommand().execute(self._base_args())

        out = capsys.readouterr().out
        assert "Succès" in out


def _make_check_version_parser(
    command: CheckVersionCommand,
) -> argparse.ArgumentParser:
    """Construit un ArgumentParser avec check-version enregistrée."""
    parser = argparse.ArgumentParser(prog="test")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command.register(subparsers)
    return parser


class TestCheckVersionCommandName:
    """Tests pour la propriété name."""

    def test_name_est_check_version(self) -> None:
        """Le nom de la sous-commande est 'check-version'."""
        assert CheckVersionCommand().name == "check-version"


class TestCheckVersionCommandRegister:
    """Tests pour register() : arguments argparse."""

    def test_venv_est_requis(self) -> None:
        """--venv est requis (SystemExit si absent)."""
        parser = _make_check_version_parser(CheckVersionCommand())
        with pytest.raises(SystemExit):
            parser.parse_args(["check-version"])

    def test_parse_arguments_minimaux(self) -> None:
        """Parse avec seulement --venv requis."""
        parser = _make_check_version_parser(CheckVersionCommand())
        args = parser.parse_args(
            ["check-version", "--venv", "/opt/app/venv"]
        )
        assert args.venv == Path("/opt/app/venv")
        assert args.source is None
        assert args.host is None
        assert args.user is None
        assert args.ssh_option == []

    def test_options_repetables(self) -> None:
        """--ssh-option est répétable."""
        parser = _make_check_version_parser(CheckVersionCommand())
        args = parser.parse_args(
            [
                "check-version",
                "--venv", "/opt/app/venv",
                "--host", "srv01",
                "--user", "deploy",
                "--ssh-option=-p",
                "--ssh-option=2222",
            ]
        )
        assert args.host == "srv01"
        assert args.user == "deploy"
        assert args.ssh_option == ["-p", "2222"]


class TestCheckVersionCommandExecute:
    """Tests pour execute() : délégation à check_target_version."""

    def _base_args(self, **overrides: Any) -> argparse.Namespace:
        """Construit un Namespace minimal valide, avec overrides."""
        base: dict[str, Any] = {
            "source": Path("/home/user/mon-outil"),
            "venv": Path("/opt/app/venv"),
            "host": None,
            "user": None,
            "ssh_option": [],
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    @patch("linuxtools.deploy.cli.check_target_version")
    def test_execute_exit_0_si_a_jour(
        self, mock_check: MagicMock
    ) -> None:
        """Cible à jour -> sys.exit(0)."""
        mock_check.return_value = VersionCheckResult(
            package="mon-outil",
            source_version="1.2.3",
            installed_version="1.2.3",
            up_to_date=True,
        )

        with pytest.raises(SystemExit) as exc_info:
            CheckVersionCommand().execute(self._base_args())

        assert exc_info.value.code == 0

    @patch("linuxtools.deploy.cli.check_target_version")
    def test_execute_exit_1_si_obsolete_ou_absent(
        self, mock_check: MagicMock
    ) -> None:
        """Cible obsolète ou paquet absent -> sys.exit(1)."""
        mock_check.return_value = VersionCheckResult(
            package="mon-outil",
            source_version="1.2.3",
            installed_version=None,
            up_to_date=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            CheckVersionCommand().execute(self._base_args())

        assert exc_info.value.code == 1

    @patch("linuxtools.deploy.cli.find_project_source")
    def test_execute_exit_2_si_source_introuvable(
        self, mock_find_source: MagicMock
    ) -> None:
        """Source introuvable (ni --source ni auto-détection) ->
        sys.exit(2) (erreur, pas verdict "obsolète")."""
        mock_find_source.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            CheckVersionCommand().execute(
                self._base_args(source=None)
            )

        assert exc_info.value.code == 2

    @patch("linuxtools.deploy.cli.check_target_version")
    def test_execute_exit_2_si_deployerror(
        self, mock_check: MagicMock
    ) -> None:
        """check_target_version lève DeployError -> sys.exit(2), pas
        de traceback brut."""
        mock_check.side_effect = DeployError(
            "pyproject.toml illisible : Permission denied"
        )

        with pytest.raises(SystemExit) as exc_info:
            CheckVersionCommand().execute(self._base_args())

        assert exc_info.value.code == 2

    @patch("linuxtools.deploy.cli.Deployer")
    @patch("linuxtools.deploy.cli.check_target_version")
    def test_execute_n_instancie_jamais_deployer(
        self, mock_check: MagicMock, mock_deployer_cls: MagicMock
    ) -> None:
        """CheckVersionCommand.execute() ne construit jamais de
        Deployer : c'est une lecture seule, pas un déploiement."""
        mock_check.return_value = VersionCheckResult(
            package="mon-outil",
            source_version="1.2.3",
            installed_version="1.2.3",
            up_to_date=True,
        )

        with pytest.raises(SystemExit):
            CheckVersionCommand().execute(self._base_args())

        mock_deployer_cls.for_target.assert_not_called()
