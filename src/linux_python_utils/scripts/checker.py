"""Vérifications pré-déploiement pour les scripts Python CLI.

Ce module fournit ScriptChecker (ABC) et LinuxScriptChecker pour
contrôler l'environnement avant d'installer un script CLI :
python3, syntaxe du script, venv, pyproject.toml et dépendances.

Typical usage example:

    checker = LinuxScriptChecker(logger)
    if not checker.check_python(required_version="3.11"):
        raise RuntimeError("Python 3.11+ requis")
    data = checker.read_pyproject(Path("pyproject.toml"))
    missing, total, cmd = checker.check_dependencies(
        Path("pyproject.toml"), venv_path=None, check_extras=[]
    )
"""

import importlib.metadata
import re
import subprocess
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path

from linux_python_utils.logging import Logger
from linux_python_utils.scripts.report import (
    InstallReport,
    InstalledDependency,
    MissingDependency,
)


class ScriptChecker(ABC):
    """Interface abstraite pour les vérifications pré-déploiement.

    Définit le contrat de vérification à respecter avant d'installer
    un script Python CLI sur le système.
    """

    @abstractmethod
    def check_python(
        self, required_version: str | None = None
    ) -> bool:
        """Vérifie que python3 est disponible et suffisamment récent.

        Args:
            required_version: Version minimale requise (ex. '3.11').
                Si None, vérifie uniquement la disponibilité.

        Returns:
            True si python3 satisfait la version requise.
        """

    @abstractmethod
    def check_script_syntax(self, script_path: Path) -> bool:
        """Vérifie l'existence et la syntaxe d'un script Python.

        Args:
            script_path: Chemin du script à analyser.

        Returns:
            True si le script existe et est syntaxiquement correct.
        """

    @abstractmethod
    def check_venv(self, venv_path: Path) -> bool:
        """Vérifie qu'un environnement virtuel est fonctionnel.

        Args:
            venv_path: Chemin du répertoire du venv.

        Returns:
            True si le venv existe et son interpréteur répond.
        """

    @abstractmethod
    def read_pyproject(
        self, pyproject_path: Path
    ) -> dict[str, object]:
        """Lit et valide un fichier pyproject.toml (PEP 621).

        Args:
            pyproject_path: Chemin du fichier pyproject.toml.

        Returns:
            Dictionnaire avec name, version, requires_python,
            dependencies, optional_dependencies, scripts.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si la section [project] est absente.
        """

    @abstractmethod
    def check_dependencies(
        self,
        pyproject_path: Path,
        venv_path: Path | None,
        check_extras: list[str],
    ) -> tuple[list[MissingDependency], int, str]:
        """Vérifie les dépendances déclarées dans pyproject.toml.

        Args:
            pyproject_path: Chemin du pyproject.toml.
            venv_path: Chemin du venv (None → pip3 système).
            check_extras: Groupes d'extras à inclure.

        Returns:
            Tuple (missing_deps, total_count, install_command).
        """


class LinuxScriptChecker(ScriptChecker):
    """Implémentation Linux des vérifications pré-déploiement.

    Utilise subprocess et tomllib (stdlib Python 3.11+) pour
    analyser l'environnement et les dépendances déclarées dans
    pyproject.toml.

    Attributes:
        _logger: Logger pour la journalisation.
    """

    _PYTHON_EXEC: str = "/usr/bin/python3"

    def __init__(self, logger: Logger) -> None:
        """Initialise avec le logger.

        Args:
            logger: Instance de Logger pour la journalisation.
        """
        self._logger = logger

    def check_python(
        self, required_version: str | None = None
    ) -> bool:
        """Vérifie que /usr/bin/python3 est disponible et récent.

        Args:
            required_version: Version minimale requise (ex. '3.11').

        Returns:
            True si python3 satisfait la version requise.
        """
        if not Path(self._PYTHON_EXEC).exists():
            self._logger.log_error(
                f"Exécutable Python introuvable : {self._PYTHON_EXEC}"
            )
            return False

        result = subprocess.run(
            [self._PYTHON_EXEC, "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self._logger.log_error("Impossible d'interroger python3")
            return False

        if required_version is None:
            return True

        version_str = result.stdout.strip() or result.stderr.strip()
        try:
            parts = version_str.split()[1].split(".")
            current = tuple(int(p) for p in parts[:2])
            required = tuple(
                int(p) for p in required_version.split(".")[:2]
            )
        except (IndexError, ValueError):
            self._logger.log_info(
                "Version Python illisible, vérification ignorée"
            )
            return True

        if current < required:
            self._logger.log_error(
                f"Python {required_version}+ requis,"
                f" version actuelle : {version_str}"
            )
            return False

        self._logger.log_info(
            f"Python OK : {version_str}"
        )
        return True

    def check_script_syntax(self, script_path: Path) -> bool:
        """Vérifie l'existence et la syntaxe d'un script Python.

        Args:
            script_path: Chemin du script à analyser.

        Returns:
            True si le script existe et est syntaxiquement correct.
        """
        if not script_path.is_file():
            self._logger.log_error(
                f"Script introuvable : {script_path}"
            )
            return False

        result = subprocess.run(
            [self._PYTHON_EXEC, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self._logger.log_error(
                f"Erreur de syntaxe dans {script_path} :"
                f" {result.stderr.strip()}"
            )
            return False

        self._logger.log_info(f"Syntaxe OK : {script_path}")
        return True

    def check_venv(self, venv_path: Path) -> bool:
        """Vérifie qu'un environnement virtuel est fonctionnel.

        Args:
            venv_path: Chemin du répertoire du venv.

        Returns:
            True si le venv existe et son interpréteur répond.
        """
        if not venv_path.is_dir():
            self._logger.log_error(
                f"Venv introuvable : {venv_path}"
            )
            return False

        python_bin = venv_path / "bin" / "python"
        if not python_bin.is_file():
            self._logger.log_error(
                f"Interpréteur venv absent : {python_bin}"
            )
            return False

        result = subprocess.run(
            [str(python_bin), "--version"],
            capture_output=True,
        )
        if result.returncode != 0:
            self._logger.log_error(
                f"Interpréteur venv non fonctionnel : {python_bin}"
            )
            return False

        self._logger.log_info(f"Venv OK : {venv_path}")
        return True

    def read_pyproject(
        self, pyproject_path: Path
    ) -> dict[str, object]:
        """Lit et valide un fichier pyproject.toml (PEP 621).

        Args:
            pyproject_path: Chemin du fichier pyproject.toml.

        Returns:
            Dictionnaire avec name, version, requires_python,
            dependencies, optional_dependencies, scripts.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si la section [project] est absente.
        """
        if not pyproject_path.is_file():
            raise FileNotFoundError(
                f"pyproject.toml introuvable : {pyproject_path}"
            )

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        if "project" not in data:
            raise ValueError(
                f"Section [project] manquante dans {pyproject_path}"
            )

        project = data["project"]
        return {
            "name": project.get("name", ""),
            "version": project.get("version", ""),
            "requires_python": project.get("requires-python"),
            "dependencies": project.get("dependencies", []),
            "optional_dependencies": project.get(
                "optional-dependencies", {}
            ),
            "scripts": project.get("scripts", {}),
        }

    def check_dependencies(
        self,
        pyproject_path: Path,
        venv_path: Path | None,
        check_extras: list[str],
    ) -> tuple[list[MissingDependency], list[InstalledDependency], int, str]:
        """Vérifie les dépendances déclarées dans pyproject.toml.

        Args:
            pyproject_path: Chemin du pyproject.toml.
            venv_path: Chemin du venv (None → pip3 système).
            check_extras: Groupes d'extras à inclure.

        Returns:
            Tuple (missing_deps, installed_deps, total_count,
            install_command).
        """
        pyproject_data = self.read_pyproject(pyproject_path)

        deps: list[str] = list(pyproject_data["dependencies"])  # type: ignore[arg-type]
        opt: dict[str, list[str]] = pyproject_data["optional_dependencies"]  # type: ignore[assignment]
        for extra in check_extras:
            if extra in opt:
                deps.extend(opt[extra])

        if venv_path is not None:
            pip_cmd = str(venv_path / "bin" / "pip")
        else:
            pip_cmd = "pip3"

        missing: list[MissingDependency] = []
        installed: list[InstalledDependency] = []
        for dep in deps:
            pkg = self._extract_package_name(dep)
            constraint = self._extract_version_constraint(dep)
            location = self._is_installed(pkg, pip_cmd)
            if location is None:
                missing.append(
                    MissingDependency(
                        package=pkg, required=constraint
                    )
                )
            else:
                installed.append(
                    InstalledDependency(package=pkg, location=location)
                )

        if venv_path is not None:
            install_cmd = (
                f"{pip_cmd} install -e '{pyproject_path.parent}'"
            )
        else:
            install_cmd = (
                f"uv tool install --editable '{pyproject_path.parent}'"
            )
        return missing, installed, len(deps), install_cmd

    @staticmethod
    def _extract_package_name(dep: str) -> str:
        """Extrait le nom du paquet depuis une spécification PEP 508.

        Args:
            dep: Spécification de dépendance (ex. 'requests>=2.0').

        Returns:
            Nom du paquet seul (ex. 'requests').
        """
        dep_clean = re.sub(r"\[.*?\]", "", dep)
        return re.split(r"[>=<!~\s]", dep_clean, maxsplit=1)[0].strip()

    @staticmethod
    def _extract_version_constraint(dep: str) -> str:
        """Extrait la contrainte de version d'une spécification PEP 508.

        Args:
            dep: Spécification de dépendance (ex. 'requests>=2.0').

        Returns:
            Contrainte de version (ex. '>=2.0') ou '' si absente.
        """
        match = re.search(r"[>=<!~][^,\s]+", dep)
        return match.group() if match else ""

    @staticmethod
    def _is_installed(pkg: str, pip_cmd: str) -> str | None:
        """Vérifie si un paquet est installé et retourne son chemin.

        Utilise d'abord importlib.metadata (détecte les installs
        éditables du venv courant), puis pip show en fallback.

        Args:
            pkg: Nom du paquet (ex. 'linux-python-utils').
            pip_cmd: Chemin vers pip à utiliser en fallback.

        Returns:
            Chemin d'installation si trouvé, None sinon.
        """
        import json

        for name in (pkg.replace("-", "_").lower(), pkg):
            try:
                dist = importlib.metadata.distribution(name)
                direct_url = dist.read_text("direct_url.json")
                if direct_url:
                    data = json.loads(direct_url)
                    url = data.get("url", "")
                    if url.startswith("file://"):
                        return url[7:]
                return str(dist.locate_file("."))
            except importlib.metadata.PackageNotFoundError:
                continue

        result = subprocess.run(
            [pip_cmd, "show", pkg], capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Location:"):
                    return line.split(":", 1)[1].strip()
            return "installé"
        return None
