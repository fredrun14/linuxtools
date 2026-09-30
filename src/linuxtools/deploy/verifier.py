"""Vérifications post-install déclaratives.

Exécute les vérifications décrites par une VerificationSpec
(imports, sous-commandes, non-régression) sur l'hôte cible via
l'exécuteur injecté.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from linuxtools.deploy.models import CheckResult, VerificationSpec

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.logging.base import Logger

_DETAIL_MAX_LEN = 200


def _rebase(value: str, venv_path: Path, version_path: Path) -> str:
    """Réécrit une chaîne pointant sous venv_path vers version_path.

    Gère aussi le fragment `--option=<chemin>` (ex. `--config=<venv_
    path>/etc/c.toml`) : seule la partie après le premier `=` est
    réécrite si elle référence explicitement venv_path (F03).

    Args:
        value: Chaîne à réécrire (chemin, ou fragment de commande).
        venv_path: Chemin du venv actif (lien symbolique).
        version_path: Chemin de la version à vérifier.

    Returns:
        `value` réécrite si elle vaut ou commence par
        `str(venv_path)/` (au besoin après un `--option=`), inchangée
        sinon (un chemin hors venv_path n'est jamais réécrit). Un
        `cli_bin` qui est un wrapper entièrement hors de venv_path
        (ex. `/usr/local/bin/wrapper-app`) référençant le venv en
        interne n'est pas, et ne peut pas être, réécrit par cette
        fonction — seuls les chemins et fragments `--option=chemin`
        référençant explicitement venv_path le sont.
    """
    venv_str = str(venv_path)
    if value == venv_str:
        return str(version_path)
    if value.startswith(venv_str + "/"):
        return str(version_path) + value[len(venv_str) :]
    if "=" in value:
        prefix, _, suffix = value.partition("=")
        rebased_suffix = _rebase(suffix, venv_path, version_path)
        if rebased_suffix != suffix:
            return f"{prefix}={rebased_suffix}"
    return value


def rebase_verification(
    spec: VerificationSpec,
    cli_bin: str | None,
    venv_path: Path,
    version_path: Path,
) -> tuple[VerificationSpec, str | None]:
    """Redirige vers version_path les chemins de vérification sous venv_path.

    En mode atomic_swap, les vérifications post-install s'exécutent
    sur la version avant bascule : un `cli_bin` ou un
    `regression_command` référençant `venv_path` en absolu viserait
    encore le venv actif (faux vert). `imports`/`subcommands` sont
    inchangés (déjà relatifs à la version via `<venv_path>/bin/...`
    construit par InstallVerifier).

    Limite connue (F03) : un `cli_bin` qui est un wrapper entièrement
    hors de `venv_path` (ex. `/usr/local/bin/wrapper-app`) référençant
    le venv en interne n'est pas, et ne peut pas être, réécrit par
    cette fonction — seuls les chemins et fragments `--option=chemin`
    référençant explicitement `venv_path` le sont.

    Args:
        spec: Vérifications déclaratives d'origine.
        cli_bin: Chemin/nom de l'exécutable CLI, ou None.
        venv_path: Chemin du venv actif (lien symbolique).
        version_path: Chemin de la version à vérifier.

    Returns:
        Tuple (spec réécrite, cli_bin réécrit).
    """
    new_cli_bin = (
        _rebase(cli_bin, venv_path, version_path)
        if cli_bin is not None
        else None
    )
    new_regression = (
        tuple(
            _rebase(part, venv_path, version_path)
            for part in spec.regression_command
        )
        if spec.regression_command is not None
        else None
    )
    new_spec = replace(spec, regression_command=new_regression)
    return new_spec, new_cli_bin


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
            result = self._executor.run([python, "-c", f"import {module}"])
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
            result = self._executor.run([binary, subcommand, "--help"])
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

        if spec.subcommands:
            if cli_bin:
                results += self._check_subcommands(
                    venv_path, spec.subcommands, cli_bin
                )
            else:
                check = CheckResult(
                    label="sous-commandes",
                    ok=False,
                    detail=("cli_bin requis pour vérifier les sous-commandes"),
                )
                results.append(check)
                self._log_check(check)

        if spec.regression_command:
            results.append(self._check_regression(spec.regression_command))

        return results
