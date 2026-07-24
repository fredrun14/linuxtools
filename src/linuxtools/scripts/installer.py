"""Installation de scripts bash et Python CLI sur le système de fichiers.

Ce module fournit des classes pour installer des scripts bash (via
BashScriptInstaller) et pour orchestrer le déploiement complet de
scripts Python CLI (via LinuxCliInstaller).

Example:
    Installation d'un script bash:

        from linuxtools import BashScriptInstaller, BashScriptConfig

        installer = BashScriptInstaller(logger, file_manager)
        config = BashScriptConfig(exec_command="echo 'Hello'")
        installer.install("/usr/local/bin/hello.sh", config)

    Déploiement d'un script Python CLI:

        from linuxtools.scripts import (
            LinuxCliInstaller, LinuxScriptChecker, PythonCliConfig,
        )
        from pathlib import Path

        checker = LinuxScriptChecker(logger)
        installer = LinuxCliInstaller(logger, checker)
        config = PythonCliConfig(
            name="mon-app", deploy_type="user",
            source_dir=Path("/home/user/mon-app"),
        )
        report = installer.install(config)
        print(report.format_summary())
"""

import os
import pwd
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from linuxtools.filesystem import FileManager
from linuxtools.filesystem.linux import _open_secure
from linuxtools.logging import Logger
from linuxtools.scripts.checker import ScriptChecker
from linuxtools.scripts.config import BashScriptConfig, PythonCliConfig
from linuxtools.scripts.paths import ScriptPaths
from linuxtools.scripts.report import (
    InstallReport,
    InstalledDependency,
    MissingDependency,
)


class ScriptInstaller(ABC):
    """Interface abstraite pour l'installation de scripts.

    Cette classe définit le contrat pour toute implémentation
    d'installateur de scripts.
    """

    @abstractmethod
    def install(self, path: str, config: BashScriptConfig) -> bool:
        """Installe un script à partir de sa configuration.

        Args:
            path: Chemin où installer le script.
            config: Configuration du script à générer.

        Returns:
            True si l'installation a réussi, False sinon.
        """
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Vérifie si un script existe déjà.

        Args:
            path: Chemin du script à vérifier.

        Returns:
            True si le script existe, False sinon.
        """
        ...


class BashScriptInstaller(ScriptInstaller):
    """Installateur de scripts bash pour systèmes Linux.

    Cette classe gère la création de scripts bash sur le système
    de fichiers, incluant la génération du contenu et les
    permissions d'exécution.

    Attributes:
        _logger: Logger optionnel pour la journalisation.
        _file_manager: Gestionnaire de fichiers pour les opérations I/O.
        _default_mode: Permissions par défaut (0o755).

    Example:
        >>> installer = BashScriptInstaller(logger, file_manager)
        >>> config = BashScriptConfig(exec_command="ls -la")
        >>> installer.install("/tmp/test.sh", config)
        True
    """

    def __init__(
        self,
        logger: Logger | None = None,
        file_manager: FileManager = None,  # type: ignore[assignment]
        default_mode: int = 0o755
    ) -> None:
        """Initialise l'installateur avec ses dépendances.

        Args:
            logger: Instance de Logger pour la journalisation.
            file_manager: Gestionnaire de fichiers.
            default_mode: Permissions par défaut pour les scripts.
        """
        self._logger = logger
        self._file_manager: FileManager = file_manager
        self._default_mode: int = default_mode

    def install(self, path: str, config: BashScriptConfig) -> bool:
        """Installe un script bash à partir de sa configuration.

        Génère le contenu du script via BashScriptConfig.to_bash_script(),
        crée le fichier et le rend exécutable.

        Args:
            path: Chemin où installer le script.
            config: Configuration du script à générer.

        Returns:
            True si l'installation a réussi, False sinon.

        Note:
            La permission d'exécution est appliquée via os.fchmod()
            (fd-safe, TOCTOU-safe) pour éviter les attaques par
            substitution de lien symbolique.
        """
        if self.exists(path):
            if self._logger:
                self._logger.log_info(
                    f"Le script {path} existe déjà. "
                    "Aucune modification apportée."
                )
            return True

        script_content: str = config.to_bash_script()

        if not self._file_manager.create_file(path, script_content):
            if self._logger:
                self._logger.log_error(
                    f"Impossible de créer le script {path}"
                )
            return False

        if not self._set_executable(path):
            return False

        if self._logger:
            self._logger.log_info(
                f"Script {path} installé avec succès."
            )
        return True

    def exists(self, path: str) -> bool:
        """Vérifie si un script existe déjà.

        Args:
            path: Chemin du script à vérifier.

        Returns:
            True si le script existe, False sinon.
        """
        return self._file_manager.file_exists(path)

    def _set_executable(self, path: str) -> bool:
        """Rend le script exécutable via fd (TOCTOU-safe).

        Utilise O_NOFOLLOW pour refuser les liens symboliques,
        puis fchmod pour appliquer les permissions via le fd.

        Args:
            path: Chemin du script.

        Returns:
            True si l'opération a réussi, False sinon.
        """
        try:
            fd = _open_secure(path, os.O_RDONLY, 0o000)
            try:
                os.fchmod(fd, self._default_mode)
            finally:
                os.close(fd)
            return True
        except OSError as e:
            if self._logger:
                self._logger.log_error(
                    f"Impossible de rendre le script exécutable : {e}"
                )
            return False


_WRAPPER_SYSTEM = """\
#!/bin/bash
# Généré automatiquement par linuxtools
# Service system : {name}

APP_DIR="/usr/local/share/{name}"

if [ -f "${{APP_DIR}}/venv/bin/activate" ]; then
    source "${{APP_DIR}}/venv/bin/activate"
fi

export PATH="/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED="1"
export PYTHONPATH="${{APP_DIR}}/src:${{PYTHONPATH}}"

cd "${{APP_DIR}}" || exit 1
exec /usr/bin/python3 "${{APP_DIR}}/main.py" "$@"
"""

_WRAPPER_USER = """\
#!/bin/bash
# Généré automatiquement par linuxtools
# Service user : {name}

APP_DIR="${{HOME}}/.local/share/{name}"

if [ -f "${{APP_DIR}}/venv/bin/activate" ]; then
    source "${{APP_DIR}}/venv/bin/activate"
fi

export PATH="${{HOME}}/.local/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED="1"
export PYTHONPATH="${{APP_DIR}}/src:${{PYTHONPATH}}"

cd "${{APP_DIR}}" || exit 1
exec /usr/bin/python3 "${{APP_DIR}}/main.py" "$@"
"""


class CliInstaller(ABC):
    """Interface abstraite pour l'installation de scripts CLI Python.

    Contrat de haut niveau : reçoit une PythonCliConfig, orchestre
    les vérifications, la génération du wrapper et l'installation,
    et retourne un InstallReport.
    """

    @abstractmethod
    def install(
        self,
        config: PythonCliConfig,
        confirm_wrapper: bool = True,
    ) -> InstallReport:
        """Installe un script Python CLI selon la configuration.

        Args:
            config: Configuration de déploiement.
            confirm_wrapper: Si True, demande confirmation avant
                de générer un wrapper bash.

        Returns:
            Rapport complet du déploiement.
        """
        ...


class LinuxCliInstaller(CliInstaller):
    """Installateur de scripts Python CLI pour systèmes Linux.

    Orchestre dans l'ordre :
    1. Résolution des chemins FHS via ScriptPaths.
    2. Vérification python3, pyproject.toml, dépendances, venv.
    3. Génération d'un wrapper bash si aucun [project.scripts]
       n'est déclaré dans pyproject.toml (avec confirmation).
    4. Installation via `uv tool install` (user) ou
       `sudo uv tool install --python /usr/bin/python3` (system).
    5. Retour d'un InstallReport avec le résultat complet.

    Attributes:
        _logger: Logger optionnel pour la journalisation.
        _checker: Implémentation de ScriptChecker.
    """

    _PYTHON_EXEC: str = "/usr/bin/python3"

    def __init__(
        self,
        logger: Logger | None = None,
        checker: ScriptChecker = None,  # type: ignore[assignment]
    ) -> None:
        """Initialise avec les dépendances injectées.

        Args:
            logger: Instance de Logger.
            checker: Implémentation de ScriptChecker.
        """
        self._logger = logger
        self._checker = checker

    def _failure(
        self,
        config: PythonCliConfig,
        install_path: Path,
        *,
        missing: list[MissingDependency] | None = None,
        installed: list[InstalledDependency] | None = None,
        total: int = 0,
        install_cmd: str = "",
        warnings: list[str] | None = None,
    ) -> InstallReport:
        """Construit un InstallReport d'échec avec les champs communs.

        Args:
            config: Configuration du déploiement.
            install_path: Chemin d'installation cible.
            missing: Dépendances manquantes.
            installed: Dépendances installées.
            total: Nombre total de dépendances.
            install_cmd: Commande de remédiation.
            warnings: Avertissements à inclure.

        Returns:
            InstallReport avec success=False.
        """
        return InstallReport(
            success=False,
            app_name=config.name,
            deploy_type=config.deploy_type,
            install_path=install_path,
            missing_deps=missing or [],
            installed_deps=installed or [],
            total_deps=total,
            install_command=install_cmd,
            warnings=warnings or [],
        )

    def _check_preconditions(
        self,
        config: PythonCliConfig,
        paths: ScriptPaths,
    ) -> tuple[InstallReport | None, dict[str, object] | None]:
        """Vérifie python3 et lit pyproject.toml.

        Args:
            config: Configuration du déploiement.
            paths: Chemins FHS résolus.

        Returns:
            Tuple (échec, données) : si échec non nul, l'installation
            doit s'arrêter ; sinon, données contient le pyproject.
        """
        if not self._checker.check_python():
            return self._failure(
                config, paths.bin_path,
                warnings=[
                    "python3 indisponible ou version insuffisante"
                ],
            ), None

        pyproject_path = config.source_dir / "pyproject.toml"
        try:
            pyproject_data = self._checker.read_pyproject(
                pyproject_path
            )
        except (FileNotFoundError, ValueError) as exc:
            if self._logger:
                self._logger.log_error(str(exc))
            return self._failure(
                config, paths.bin_path, warnings=[str(exc)]
            ), None

        return None, pyproject_data

    def _handle_wrapper(
        self,
        config: PythonCliConfig,
        paths: ScriptPaths,
        pyproject_data: dict[str, object],
        missing: list[MissingDependency],
        installed: list[InstalledDependency],
        total: int,
        install_cmd: str,
        warnings: list[str],
        confirm_wrapper: bool,
    ) -> InstallReport | None:
        """Gère la génération conditionnelle du wrapper bash.

        Args:
            config: Configuration du déploiement.
            paths: Chemins FHS résolus.
            pyproject_data: Données lues depuis pyproject.toml.
            missing: Dépendances manquantes.
            installed: Dépendances installées.
            total: Nombre total de dépendances.
            install_cmd: Commande de remédiation.
            warnings: Avertissements accumulés.
            confirm_wrapper: Si True, demande confirmation interactive.

        Returns:
            InstallReport d'échec si le wrapper est refusé ou non
            écrit, None si aucun wrapper ou wrapper écrit avec succès.
        """
        needs_wrapper = (
            config.generate_wrapper
            and not pyproject_data.get("scripts")
        )
        if not needs_wrapper:
            return None

        if confirm_wrapper and not sys.stdin.isatty():
            confirm_wrapper = False

        if confirm_wrapper:
            print(
                "\nAucun [project.scripts] détecté.\n"
                "Générer un wrapper bash"
                f" → {paths.bin_path} ? [o/N] ",
                end="",
                flush=True,
            )
            answer = input().strip().lower()
            if answer not in ("o", "oui", "y", "yes"):
                return self._failure(
                    config, paths.bin_path,
                    missing=missing, installed=installed,
                    total=total, install_cmd=install_cmd,
                    warnings=["Wrapper refusé par l'utilisateur"],
                )

        wrapper_content = self._generate_wrapper_content(
            config, paths
        )
        try:
            self._write_wrapper(wrapper_content, paths.bin_path)
        except OSError as exc:
            if self._logger:
                self._logger.log_error(
                    f"Échec écriture wrapper : {exc}"
                )
            return self._failure(
                config, paths.bin_path,
                missing=missing, installed=installed,
                total=total, install_cmd=install_cmd,
                warnings=warnings + [f"Wrapper non écrit : {exc}"],
            )
        return None

    def install(
        self,
        config: PythonCliConfig,
        confirm_wrapper: bool = True,
    ) -> InstallReport:
        """Installe un script Python CLI selon la configuration.

        Args:
            config: Configuration de déploiement.
            confirm_wrapper: Si True, demande confirmation avant
                de générer un wrapper bash.

        Returns:
            Rapport complet du déploiement.
        """
        paths = ScriptPaths(config.name, config.deploy_type)
        warnings: list[str] = []

        failure, pyproject_data = self._check_preconditions(
            config, paths
        )
        if failure is not None:
            return failure

        pyproject_path = config.source_dir / "pyproject.toml"
        missing, installed, total, install_cmd = (
            self._checker.check_dependencies(
                pyproject_path, config.venv_path, config.check_extras
            )
        )
        if missing:
            warnings.append(
                f"{len(missing)}/{total} dépendances manquantes"
            )

        if config.venv_path:
            if not self._checker.check_venv(config.venv_path):
                warnings.append(
                    f"Venv inaccessible : {config.venv_path}"
                )

        failure = self._handle_wrapper(
            config, paths, pyproject_data,  # type: ignore[arg-type]
            missing, installed, total, install_cmd,
            warnings, confirm_wrapper,
        )
        if failure is not None:
            return failure

        if not self._run_uv_install(config):
            return self._failure(
                config, paths.bin_path,
                missing=missing, installed=installed,
                total=total, install_cmd=install_cmd,
                warnings=warnings + ["Échec de uv tool install"],
            )

        if self._logger:
            self._logger.log_info(
                f"Déploiement réussi : {config.name} → {paths.bin_path}"
            )
        return InstallReport(
            success=True,
            app_name=config.name,
            deploy_type=config.deploy_type,
            install_path=paths.bin_path,
            missing_deps=missing,
            installed_deps=installed,
            total_deps=total,
            install_command=install_cmd,
            warnings=warnings,
        )

    def _generate_wrapper_content(
        self,
        config: PythonCliConfig,
        paths: ScriptPaths,
    ) -> str:
        """Génère le contenu du wrapper bash selon le type de déploiement.

        Args:
            config: Configuration du déploiement.
            paths: Chemins FHS résolus.

        Returns:
            Contenu complet du script bash.
        """
        template = (
            _WRAPPER_SYSTEM
            if config.deploy_type == "system"
            else _WRAPPER_USER
        )
        content = template.format(name=config.name)
        if config.venv_path is None:
            content = self._strip_venv_block(content)
        return content

    @staticmethod
    def _strip_venv_block(content: str) -> str:
        """Supprime le bloc d'activation du venv du wrapper bash.

        Args:
            content: Contenu brut du wrapper.

        Returns:
            Contenu sans le bloc if [ -f ...activate ]...fi.
        """
        lines = content.splitlines(keepends=True)
        filtered: list[str] = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('if [ -f "') and "activate" in stripped:
                skip = True
            if skip:
                if stripped == "fi":
                    skip = False
                continue
            filtered.append(line)
        return "".join(filtered)

    def _write_wrapper(
        self, content: str, target_path: Path
    ) -> None:
        """Écrit le wrapper bash sur disque (TOCTOU-safe).

        Utilise O_NOFOLLOW pour refuser les liens symboliques.
        O_CREAT|O_TRUNC crée ou écrase ; fchmod(0o755) appliqué
        sur le fd avant fermeture (fd-safe).

        Args:
            content: Contenu du script bash.
            target_path: Chemin de destination.

        Raises:
            OSError: Si target_path est un symlink, si l'écriture
                ou le chmod échoue.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd = _open_secure(
            target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644
        )
        try:
            with os.fdopen(
                fd, "w", encoding="utf-8", closefd=False
            ) as fh:
                fh.write(content)
            os.fchmod(fd, 0o755)  # nosec B103
        finally:
            os.close(fd)
        if self._logger:
            self._logger.log_info(f"Wrapper écrit : {target_path}")

    @staticmethod
    def _candidate_homes() -> list[Path]:
        """Retourne les homes à sonder pour localiser uv.

        Inclut le home de l'utilisateur courant et, le cas échéant,
        celui de ``$SUDO_USER`` (cas d'une exécution via sudo/root).

        Returns:
            Liste des répertoires home candidats.
        """
        homes = [Path.home()]
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            try:
                homes.append(Path(pwd.getpwnam(sudo_user).pw_dir))
            except KeyError:
                pass
        return homes

    def _find_uv(self) -> str | None:
        """Localise l'exécutable uv : PATH puis emplacements usuels.

        Cherche dans l'ordre :
        1. Le PATH courant (``shutil.which``).
        2. ``~/.local/bin/uv`` et ``~/.cargo/bin/uv`` de l'utilisateur
           courant et de ``$SUDO_USER``.

        Indispensable sous sudo/root : le PATH de root n'inclut pas le
        ``~/.local/bin`` de l'utilisateur qui a installé uv.

        Returns:
            Chemin absolu vers uv, ou None si introuvable.
        """
        found = shutil.which("uv")
        if found:
            return found
        for home in self._candidate_homes():
            for sub in (".local/bin/uv", ".cargo/bin/uv"):
                candidate = home / sub
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
        return None

    def _run_uv_install(self, config: PythonCliConfig) -> bool:
        """Lance uv tool install pour déployer le script CLI.

        Args:
            config: Configuration du déploiement.

        Returns:
            True si l'installation uv a réussi, False sinon.
        """
        uv_path = self._find_uv()
        if uv_path is None:
            if self._logger:
                self._logger.log_error(
                    "uv introuvable (ni dans le PATH, ni dans "
                    "~/.local/bin ou ~/.cargo/bin). "
                    "Installez-le (pip install uv) ou ajoutez-le au PATH."
                )
            return False

        if config.deploy_type == "system":
            base = [
                "env", "UV_TOOL_BIN_DIR=/usr/local/bin",
                uv_path, "tool", "install",
                "--python", self._PYTHON_EXEC,
                "--editable",
                str(config.source_dir),
            ]
            # sudo uniquement si on n'est pas déjà root
            cmd = (["sudo"] if os.geteuid() != 0 else []) + base
        else:
            cmd = [
                uv_path, "tool", "install",
                "--force", "--editable", str(config.source_dir),
            ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
        except FileNotFoundError:
            if self._logger:
                self._logger.log_error(
                    f"uv non trouvé à {uv_path}"
                )
            return False

        if result.returncode != 0:
            if self._logger:
                self._logger.log_error(
                    f"uv tool install a échoué : {result.stderr.strip()}"
                )
            return False

        return True
