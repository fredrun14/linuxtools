"""Tests pour le module deploy.verifier."""

from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.models import VerificationSpec
from linuxtools.deploy.verifier import (
    InstallVerifier,
    _rebase,
    rebase_verification,
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


class TestInstallVerifierImports:
    """Tests pour la vérification des imports."""

    def test_import_ok(self) -> None:
        """Un import réussi produit un CheckResult ok=True."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(imports=("linuxtools",)),
        )

        assert len(results) == 1
        assert results[0].ok is True
        assert results[0].label == "import linuxtools"

    def test_import_ko_avec_detail_tronque(self) -> None:
        """Un import échoué produit un CheckResult ok=False avec detail."""
        executor = _make_executor()
        executor.run.return_value = _result(
            success=False, stderr="ModuleNotFoundError: pas trouvé"
        )
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(imports=("inexistant",)),
        )

        assert results[0].ok is False
        assert "ModuleNotFoundError" in results[0].detail

    def test_commande_utilise_python_du_venv(self) -> None:
        """La vérification passe par <venv>/bin/python -c."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        verifier = InstallVerifier(executor)

        verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(imports=("os",)),
        )

        command = executor.run.call_args.args[0]
        assert command == [
            "/opt/app/venv/bin/python",
            "-c",
            "import os",
        ]

    def test_plusieurs_imports_produisent_plusieurs_checks(self) -> None:
        """Chaque import déclaré produit un CheckResult distinct."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(imports=("os", "sys", "json")),
        )

        assert len(results) == 3
        assert executor.run.call_count == 3


class TestInstallVerifierSubcommands:
    """Tests pour la vérification des sous-commandes."""

    def test_echoue_les_subcommands_sans_cli_bin(self) -> None:
        """Sans cli_bin, les subcommands déclarées échouent (pas de
        faux succès silencieux — plan correctif #1, BLOQUANT)."""
        executor = _make_executor()
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(subcommands=("list",)),
            cli_bin=None,
        )

        assert len(results) == 1
        assert results[0].ok is False
        assert results[0].label == "sous-commandes"
        executor.run.assert_not_called()

    def test_echoue_les_subcommands_sans_cli_bin_bloque_le_all_ok(
        self,
    ) -> None:
        """Le CheckResult d'échec fait basculer all(c.ok) à False,
        ce qui déclenche le rollback côté Deployer."""
        executor = _make_executor()
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(subcommands=("list",)),
            cli_bin=None,
        )

        assert all(check.ok for check in results) is False

    def test_subcommand_ok_via_help(self) -> None:
        """Une sous-commande valide répond --help en code 0."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(subcommands=("list",)),
            cli_bin="borg-manager",
        )

        assert results[0].ok is True
        command = executor.run.call_args.args[0]
        assert command == [
            "/opt/app/venv/bin/borg-manager",
            "list",
            "--help",
        ]

    def test_subcommand_inconnue_echoue(self) -> None:
        """Une sous-commande inconnue répond --help en code non nul."""
        executor = _make_executor()
        executor.run.return_value = _result(
            success=False, stderr="unknown command"
        )
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(subcommands=("bogus",)),
            cli_bin="borg-manager",
        )

        assert results[0].ok is False


class TestInstallVerifierRegression:
    """Tests pour le hook de non-régression."""

    def test_sans_regression_aucun_check(self) -> None:
        """Sans regression_command, aucun check n'est ajouté."""
        executor = _make_executor()
        verifier = InstallVerifier(executor)

        results = verifier.verify(Path("/opt/app/venv"), VerificationSpec())

        assert results == []

    def test_regression_ok(self) -> None:
        """La commande de non-régression est exécutée telle quelle."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(regression_command=("borg-manager", "check")),
        )

        assert len(results) == 1
        assert results[0].ok is True
        assert results[0].label == "non-régression"
        command = executor.run.call_args.args[0]
        assert command == ["borg-manager", "check"]

    def test_regression_ko(self) -> None:
        """Un échec de la commande de non-régression est reporté."""
        executor = _make_executor()
        executor.run.return_value = _result(
            success=False, stderr="assertion failed"
        )
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(regression_command=("check",)),
        )

        assert results[0].ok is False


class TestInstallVerifierCombine:
    """Tests d'intégration combinant les trois types de vérifications."""

    def test_verify_combine_imports_subcommands_et_regression(self) -> None:
        """verify() combine et retourne les checks des 3 catégories."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        verifier = InstallVerifier(executor)

        results = verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(
                imports=("mod_a",),
                subcommands=("list",),
                regression_command=("check",),
            ),
            cli_bin="mon-cli",
        )

        labels = [r.label for r in results]
        assert "import mod_a" in labels
        assert "sous-commande list" in labels
        assert "non-régression" in labels

    def test_logue_chaque_check(self) -> None:
        """Chaque CheckResult est loggué (OK ou KO)."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),
            _result(success=False, stderr="boom"),
        ]
        logger = MagicMock(spec=Logger)
        verifier = InstallVerifier(executor, logger=logger)

        verifier.verify(
            Path("/opt/app/venv"),
            VerificationSpec(imports=("ok_mod", "bad_mod")),
        )

        assert logger.log_info.call_count == 1
        assert logger.log_error.call_count == 1


class TestRebaseVerification:
    """Tests pour rebase_verification (mode atomic_swap, T4)."""

    def test_cli_bin_egal_au_venv_path_est_reecrit(self) -> None:
        """cli_bin == str(venv_path) est réécrit vers version_path."""
        spec = VerificationSpec(imports=("app",))
        new_spec, new_cli_bin = rebase_verification(
            spec,
            cli_bin="/opt/app/venv",
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-20260929-000000-000000"),
        )
        assert new_cli_bin == "/opt/app/venvs/venv-20260929-000000-000000"
        assert new_spec == spec

    def test_cli_bin_relatif_inchange(self) -> None:
        """cli_bin relatif (nom simple) n'est pas réécrit."""
        spec = VerificationSpec()
        _new_spec, new_cli_bin = rebase_verification(
            spec,
            cli_bin="mon-outil",
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-1"),
        )
        assert new_cli_bin == "mon-outil"

    def test_cli_bin_none_reste_none(self) -> None:
        """cli_bin=None reste None après réécriture."""
        spec = VerificationSpec()
        _new_spec, new_cli_bin = rebase_verification(
            spec,
            cli_bin=None,
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-1"),
        )
        assert new_cli_bin is None

    def test_regression_command_reecrit_le_prefixe_venv_path(self) -> None:
        """Chaque élément de regression_command préfixé par venv_path
        est réécrit, les autres inchangés."""
        spec = VerificationSpec(
            regression_command=(
                "/opt/app/venv/bin/mon-outil",
                "check",
                "--verbose",
            )
        )
        new_spec, _new_cli_bin = rebase_verification(
            spec,
            cli_bin=None,
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-1"),
        )
        assert new_spec.regression_command == (
            "/opt/app/venvs/venv-1/bin/mon-outil",
            "check",
            "--verbose",
        )

    def test_chemin_hors_venv_path_jamais_reecrit(self) -> None:
        """Un chemin `/opt/x/venv2/...` proche mais distinct n'est
        pas réécrit (pas de préfixe partiel foireux)."""
        spec = VerificationSpec(
            regression_command=("/opt/x/venv2/bin/autre-outil",)
        )
        new_spec, _new_cli_bin = rebase_verification(
            spec,
            cli_bin=None,
            venv_path=Path("/opt/x/venv"),
            version_path=Path("/opt/x/venvs/venv-1"),
        )
        assert new_spec.regression_command == ("/opt/x/venv2/bin/autre-outil",)

    def test_rebase_fragment_option_egal_chemin_venv_path_reecrit(
        self,
    ) -> None:
        """`--option=<venv_path>/...` : le fragment après `=` est
        réécrit vers version_path (F03)."""
        result = _rebase(
            "--config=/opt/app/venv/etc/c.toml",
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-20260929-000000-000000"),
        )
        assert result == (
            "--config=/opt/app/venvs/venv-20260929-000000-000000/etc/c.toml"
        )

    def test_rebase_fragment_option_sans_rapport_avec_venv_path_inchange(
        self,
    ) -> None:
        """`--option=<chemin sans rapport>` n'est pas réécrit (pas de
        faux positif sur un `=` quelconque, F03)."""
        result = _rebase(
            "--config=/autre/chemin",
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-20260929-000000-000000"),
        )
        assert result == "--config=/autre/chemin"

    def test_imports_et_subcommands_inchanges(self) -> None:
        """imports/subcommands ne sont jamais réécrits par
        rebase_verification (déjà relatifs via InstallVerifier)."""
        spec = VerificationSpec(imports=("app",), subcommands=("list",))
        new_spec, _new_cli_bin = rebase_verification(
            spec,
            cli_bin=None,
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-1"),
        )
        assert new_spec.imports == ("app",)
        assert new_spec.subcommands == ("list",)

    def test_regression_command_none_reste_none(self) -> None:
        """regression_command=None reste None après réécriture."""
        spec = VerificationSpec()
        new_spec, _new_cli_bin = rebase_verification(
            spec,
            cli_bin=None,
            venv_path=Path("/opt/app/venv"),
            version_path=Path("/opt/app/venvs/venv-1"),
        )
        assert new_spec.regression_command is None
