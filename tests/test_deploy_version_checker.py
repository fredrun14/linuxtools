"""Tests pour le module deploy.version_checker."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import DeployTarget
from linuxtools.deploy.version_checker import (
    VersionChecker,
    check_target_version,
    read_source_version,
)
from linuxtools.logging.base import Logger


def _result(
    success: bool = True, stdout: str = "", stderr: str = ""
) -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout=stdout,
        stderr=stderr,
        success=success,
        duration=0.01,
    )


def _make_executor() -> MagicMock:
    """Crée un mock de CommandExecutor cible."""
    return MagicMock(spec=CommandExecutor)


def _write_pyproject(
    tmp_path: Path,
    name: str = "mon-outil",
    version: str = "1.2.3",
) -> Path:
    """Écrit un pyproject.toml minimal dans tmp_path."""
    content = (
        "[project]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
    )
    (tmp_path / "pyproject.toml").write_text(content, encoding="utf-8")
    return tmp_path


class TestReadSourceVersion:
    """Tests pour read_source_version()."""

    def test_retourne_nom_et_version_cas_nominal(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : name et version lus depuis [project]."""
        _write_pyproject(tmp_path, name="mon-outil", version="1.2.3")

        name, version = read_source_version(tmp_path)

        assert name == "mon-outil"
        assert version == "1.2.3"

    def test_leve_deployerror_si_fichier_absent(
        self, tmp_path: Path
    ) -> None:
        """pyproject.toml absent -> DeployError."""
        with pytest.raises(DeployError, match="introuvable"):
            read_source_version(tmp_path)

    def test_leve_deployerror_si_toml_malforme(
        self, tmp_path: Path
    ) -> None:
        """TOML malformé -> DeployError."""
        (tmp_path / "pyproject.toml").write_text(
            "[project\nname = ", encoding="utf-8"
        )

        with pytest.raises(DeployError, match="illisible"):
            read_source_version(tmp_path)

    def test_leve_deployerror_si_fichier_illisible(
        self, tmp_path: Path
    ) -> None:
        """pyproject.toml illisible (OSError à l'ouverture) ->
        DeployError, pas PermissionError brute."""
        _write_pyproject(tmp_path)

        with patch.object(
            Path,
            "open",
            side_effect=PermissionError("Permission denied"),
        ):
            with pytest.raises(DeployError, match="illisible"):
                read_source_version(tmp_path)

    def test_leve_deployerror_si_version_absente(
        self, tmp_path: Path
    ) -> None:
        """Clé project.version absente -> DeployError."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "mon-outil"\n', encoding="utf-8"
        )

        with pytest.raises(DeployError, match="name.*version"):
            read_source_version(tmp_path)


class TestVersionCheckerCheck:
    """Tests pour VersionChecker.check()."""

    def test_retourne_up_to_date_true_si_versions_identiques(
        self,
    ) -> None:
        """Versions identiques -> up_to_date True."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=True, stdout="1.2.3\n"
        )
        checker = VersionChecker(executor)

        result = checker.check(
            Path("/opt/app/venv"), "mon-outil", "1.2.3"
        )

        assert result.up_to_date is True
        assert result.installed_version == "1.2.3"
        assert result.source_version == "1.2.3"
        assert result.package == "mon-outil"

    def test_retourne_up_to_date_false_si_versions_differentes(
        self,
    ) -> None:
        """Versions différentes -> up_to_date False."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=True, stdout="1.0.0\n"
        )
        checker = VersionChecker(executor)

        result = checker.check(
            Path("/opt/app/venv"), "mon-outil", "1.2.3"
        )

        assert result.up_to_date is False
        assert result.installed_version == "1.0.0"

    def test_retourne_installed_version_none_si_paquet_absent(
        self,
    ) -> None:
        """Commande cible en échec -> installed_version None."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=False, stderr="PackageNotFoundError"
        )
        checker = VersionChecker(executor)

        result = checker.check(
            Path("/opt/app/venv"), "mon-outil", "1.2.3"
        )

        assert result.installed_version is None
        assert result.up_to_date is False

    def test_retourne_installed_version_none_si_stdout_vide(
        self,
    ) -> None:
        """Sonde réussie mais stdout vide -> installed_version None."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=True, stdout=""
        )
        checker = VersionChecker(executor)

        result = checker.check(
            Path("/opt/app/venv"), "mon-outil", "1.2.3"
        )

        assert result.installed_version is None
        assert result.up_to_date is False

    def test_transmet_un_timeout_a_probe(self) -> None:
        """probe() est appelé avec un timeout non None."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=True, stdout="1.2.3\n"
        )
        checker = VersionChecker(executor)

        checker.check(Path("/opt/app/venv"), "mon-outil", "1.2.3")

        _, kwargs = executor.probe.call_args
        assert kwargs.get("timeout") is not None

    def test_utilise_probe_pas_run(self) -> None:
        """La lecture de version cible passe par .probe(), pas .run()."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=True, stdout="1.2.3\n"
        )
        checker = VersionChecker(executor)

        checker.check(Path("/opt/app/venv"), "mon-outil", "1.2.3")

        executor.probe.assert_called_once()
        executor.run.assert_not_called()

    def test_logue_le_resultat_si_logger_fourni(self) -> None:
        """Le résultat est loggué en info quand un logger est injecté."""
        executor = _make_executor()
        executor.probe.return_value = _result(
            success=True, stdout="1.2.3\n"
        )
        logger = MagicMock(spec=Logger)
        checker = VersionChecker(executor, logger=logger)

        checker.check(Path("/opt/app/venv"), "mon-outil", "1.2.3")

        logger.log_info.assert_called_once()


class TestCheckTargetVersion:
    """Tests pour la façade check_target_version()."""

    def test_construit_executeur_local_si_target_none(
        self, tmp_path: Path
    ) -> None:
        """target=None -> exécuteur local (pas de SshCommandExecutor)."""
        _write_pyproject(tmp_path, name="mon-outil", version="1.2.3")

        with patch(
            "linuxtools.deploy.version_checker.LinuxCommandExecutor"
        ) as mock_local_cls:
            mock_local = MagicMock()
            mock_local.probe.return_value = _result(
                success=True, stdout="1.2.3\n"
            )
            mock_local_cls.return_value = mock_local

            result = check_target_version(
                tmp_path, Path("/opt/app/venv")
            )

        mock_local.probe.assert_called_once()
        assert result.up_to_date is True

    def test_construit_ssh_executor_si_target_remote(
        self, tmp_path: Path
    ) -> None:
        """target distante -> SshCommandExecutor est utilisé."""
        _write_pyproject(tmp_path, name="mon-outil", version="1.2.3")

        with patch(
            "linuxtools.deploy.version_checker.SshCommandExecutor"
        ) as mock_ssh_cls:
            mock_ssh = MagicMock()
            mock_ssh.probe.return_value = _result(
                success=True, stdout="1.2.3\n"
            )
            mock_ssh_cls.return_value = mock_ssh

            result = check_target_version(
                tmp_path,
                Path("/opt/app/venv"),
                DeployTarget(host="srv01"),
            )

        mock_ssh_cls.assert_called_once()
        mock_ssh.probe.assert_called_once()
        assert result.up_to_date is True

    def test_utilise_nom_pyproject_si_package_non_fourni(
        self, tmp_path: Path
    ) -> None:
        """package=None -> déduit de [project].name du pyproject.toml.

        Nom de paquet hostile (apostrophe + point-virgule) : la liste
        exacte de tokens transmise à probe() est vérifiée, pas un
        simple `in`, pour garantir qu'aucune concaténation shell
        n'est possible (le nom est injecté via repr() dans le script
        -c, jamais interpolé dans une chaîne shell).
        """
        hostile_name = "mon-outil'; rm -rf ~ #"
        _write_pyproject(tmp_path, name=hostile_name, version="1.2.3")

        with patch(
            "linuxtools.deploy.version_checker.LinuxCommandExecutor"
        ) as mock_local_cls:
            mock_local = MagicMock()
            mock_local.probe.return_value = _result(
                success=True, stdout="1.2.3\n"
            )
            mock_local_cls.return_value = mock_local

            result = check_target_version(
                tmp_path, Path("/opt/app/venv")
            )

        assert result.package == hostile_name
        command_args, command_kwargs = mock_local.probe.call_args
        expected_script = (
            "from importlib.metadata import version; "
            f"print(version({hostile_name!r}))"
        )
        assert command_args[0] == [
            str(Path("/opt/app/venv") / "bin" / "python"),
            "-c",
            expected_script,
        ]
        assert command_kwargs.get("timeout") is not None
