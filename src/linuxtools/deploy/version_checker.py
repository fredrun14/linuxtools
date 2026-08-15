"""Comparaison de version source vs cible pour le module deploy.

Permet de savoir, avant ou indépendamment d'un déploiement, si une
cible (locale ou distante) tourne déjà avec la dernière version
disponible en source — en comparant le numéro de version du
pyproject.toml source local à celui effectivement installé dans le
venv cible. Ne décide jamais de déployer : la fonction informe, elle
ne décide pas (cf. CDC §2, hors périmètre explicite).
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import DeployTarget, VersionCheckResult
from linuxtools.deploy.ssh_executor import SshCommandExecutor

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.logging.base import Logger


def read_source_version(source_dir: Path) -> tuple[str, str]:
    """Lit le nom et la version du paquet depuis le pyproject.toml source.

    Args:
        source_dir: Répertoire source local (contient pyproject.toml).

    Returns:
        Tuple (package_name, version) lu dans la table [project].

    Raises:
        DeployError: Si pyproject.toml est absent, illisible, ou si
            la table [project] n'expose pas les clés name/version
            (ex. version dynamique — hors périmètre ici).
    """
    path = source_dir / "pyproject.toml"
    if not path.is_file():
        raise DeployError(
            f"pyproject.toml introuvable dans {source_dir}"
        )

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise DeployError(
            f"pyproject.toml illisible : {exc}"
        ) from exc
    except OSError as exc:
        raise DeployError(
            f"pyproject.toml illisible : {exc}"
        ) from exc

    project_table = data.get("project", {})
    name = project_table.get("name")
    version = project_table.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise DeployError(
            "pyproject.toml : 'project.name' et 'project.version' "
            "requis (version dynamique non supportée)"
        )

    return name, version


class VersionChecker:
    """Compare la version source à la version installée sur la cible.

    Attributes:
        _executor: Exécuteur ciblant l'hôte (local ou
            SshCommandExecutor).
        _logger: Logger optionnel.
    """

    _PROBE_TIMEOUT = 30

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

    def _log(self, message: str) -> None:
        """Envoie un message d'information au logger si disponible."""
        if self._logger:
            self._logger.log_info(message)

    def check(
        self,
        venv_path: Path,
        package: str,
        source_version: str,
    ) -> VersionCheckResult:
        """Compare source_version à la version installée dans venv_path.

        Args:
            venv_path: Venv cible sur l'hôte (local ou distant).
            package: Nom du paquet à interroger (importlib.metadata).
            source_version: Version source à comparer (déjà lue en
                amont, ex. via read_source_version).

        Returns:
            VersionCheckResult. installed_version vaut None si le
            paquet n'est pas installé (venv absent, jamais déployé,
            ou paquet différent installé) — ce n'est jamais une
            erreur, seulement un signal « pas encore là ».

        Note:
            La comparaison des versions est une égalité de chaînes
            stricte, sans normalisation PEP 440 : "1.0-beta1" et
            "1.0b1" ne seront pas jugées égales, même si `packaging`
            les considérerait équivalentes (hors périmètre du CDC).
        """
        python_bin = str(venv_path / "bin" / "python")
        result = self._executor.probe(
            [
                python_bin,
                "-c",
                "from importlib.metadata import version; "
                f"print(version({package!r}))",
            ],
            timeout=self._PROBE_TIMEOUT,
        )

        stdout = result.stdout.strip() if result.success else ""
        installed_version = stdout or None
        if installed_version is None:
            self._log(f"{package} non installé dans {venv_path}")

        up_to_date = installed_version == source_version

        self._log(
            f"{package} : source={source_version} installé="
            f"{installed_version or '(absent)'} -> "
            f"{'à jour' if up_to_date else 'obsolète'}"
        )

        return VersionCheckResult(
            package=package,
            source_version=source_version,
            installed_version=installed_version,
            up_to_date=up_to_date,
        )


def check_target_version(
    source_dir: Path,
    venv_path: Path,
    target: DeployTarget | None = None,
    package: str | None = None,
    logger: Logger | None = None,
) -> VersionCheckResult:
    """Façade : lit la version source et compare à la cible en un appel.

    Construit l'exécuteur adapté à la cible (LinuxCommandExecutor en
    local, SshCommandExecutor si target.is_remote), exactement comme
    Deployer.for_target — pour rester utilisable indépendamment de
    Deployer (F-02 du CDC).

    Args:
        source_dir: Répertoire source local (contient pyproject.toml).
        venv_path: Venv cible sur l'hôte (local ou distant).
        target: Description de l'hôte cible. None = local (défaut
            DeployTarget()).
        package: Nom du paquet à interroger. None = déduit du
            pyproject.toml source (recommandé — évite une
            désynchronisation entre le nom déclaré et celui vérifié).
        logger: Logger optionnel, propagé à l'exécuteur et au
            VersionChecker.

    Returns:
        VersionCheckResult de la comparaison.
    """
    resolved_target = target or DeployTarget()
    name, source_version = read_source_version(source_dir)
    resolved_package = package or name

    local_exec = LinuxCommandExecutor(logger=logger)
    target_exec: CommandExecutor = (
        SshCommandExecutor(resolved_target, local_exec, logger)
        if resolved_target.is_remote
        else local_exec
    )

    checker = VersionChecker(target_exec, logger)
    return checker.check(venv_path, resolved_package, source_version)
