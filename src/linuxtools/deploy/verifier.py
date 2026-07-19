"""Vérifications post-install déclaratives.

Exécute les vérifications décrites par une VerificationSpec
(imports, sous-commandes, non-régression) sur l'hôte cible via
l'exécuteur injecté.
"""

from __future__ import annotations

from pathlib import Path

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.models import CheckResult, VerificationSpec
from linuxtools.logging.base import Logger

_DETAIL_MAX_LEN = 200


class InstallVerifier:
    """Exécute les vérifications post-install déclaratives.

    Attributes:
        _executor: Exécuteur ciblant l'hôte (local ou
            SshCommandExecutor).
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        executor: CommandExecutor,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le vérificateur avec son exécuteur cible.

        Args:
            executor: Exécuteur de commandes ciblant l'hôte.
            logger: Logger optionnel.
        """
        self._executor = executor
        self._logger = logger

    def _log_check(self, check: CheckResult) -> None:
        """Logue un résultat de vérification (OK/KO)."""
        if not self._logger:
            return
        if check.ok:
            self._logger.log_info(f"✓ {check.label}")
        else:
            self._logger.log_error(f"✗ {check.label} : {check.detail}")

    def _check_imports(
        self, venv_path: Path, imports: tuple[str, ...]
    ) -> list[CheckResult]:
        """Vérifie que chaque module s'importe dans le venv cible.

        Args:
            venv_path: Chemin du venv cible.
            imports: Modules à importer.

        Returns:
            Liste des résultats, un par import testé.
        """
        python = str(venv_path / "bin" / "python")
        results: list[CheckResult] = []
        for module in imports:
            result = self._executor.run(
                [python, "-c", f"import {module}"]
            )
            check = CheckResult(
                label=f"import {module}",
                ok=result.success,
                detail=result.stderr[:_DETAIL_MAX_LEN],
            )
            results.append(check)
            self._log_check(check)
        return results

    def _check_subcommands(
        self,
        venv_path: Path,
        subcommands: tuple[str, ...],
        cli_bin: str,
    ) -> list[CheckResult]:
        """Vérifie que chaque sous-commande répond à --help.

        --help sort en code 0 si la sous-commande existe, code non
        nul si elle est inconnue.

        Args:
            venv_path: Chemin du venv cible.
            subcommands: Sous-commandes attendues.
            cli_bin: Nom de l'exécutable CLI dans le venv.

        Returns:
            Liste des résultats, un par sous-commande testée.
        """
        binary = str(venv_path / "bin" / cli_bin)
        results: list[CheckResult] = []
        for subcommand in subcommands:
            result = self._executor.run(
                [binary, subcommand, "--help"]
            )
            check = CheckResult(
                label=f"sous-commande {subcommand}",
                ok=result.success,
                detail=result.stderr[:_DETAIL_MAX_LEN],
            )
            results.append(check)
            self._log_check(check)
        return results

    def _check_regression(
        self, regression_command: tuple[str, ...]
    ) -> CheckResult:
        """Rejoue le hook de non-régression sur l'hôte cible.

        Args:
            regression_command: Commande à exécuter telle quelle.

        Returns:
            Résultat de la vérification de non-régression.
        """
        result = self._executor.run(list(regression_command))
        check = CheckResult(
            label="non-régression",
            ok=result.success,
            detail=result.stderr[:_DETAIL_MAX_LEN],
        )
        self._log_check(check)
        return check

    def verify(
        self,
        venv_path: Path,
        spec: VerificationSpec,
        cli_bin: str | None = None,
    ) -> list[CheckResult]:
        """Exécute toutes les vérifications déclarées par spec.

        Args:
            venv_path: Chemin du venv cible.
            spec: Vérifications déclaratives à exécuter.
            cli_bin: Nom de l'exécutable CLI dans le venv. Requis
                pour tester spec.subcommands (ignoré sinon).

        Returns:
            Liste de tous les CheckResult produits. `all(c.ok for
            c in results)` détermine le succès global.
        """
        results: list[CheckResult] = []

        results += self._check_imports(venv_path, spec.imports)

        if cli_bin and spec.subcommands:
            results += self._check_subcommands(
                venv_path, spec.subcommands, cli_bin
            )

        if spec.regression_command:
            results.append(
                self._check_regression(spec.regression_command)
            )

        return results
