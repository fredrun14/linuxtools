"""Installation de scripts bash et Python CLI sur le système de fichiers.

Ce module fournit des classes pour installer des scripts bash (via
BashScriptInstaller) et pour orchestrer le déploiement complet de
scripts Python CLI (via LinuxCliInstaller).

Example:
    Installation d'un script bash:

        from linux_python_utils import BashScriptInstaller, BashScriptConfig

        installer = BashScriptInstaller(logger, file_manager)
        config = BashScriptConfig(exec_command="echo 'Hello'")
        installer.install("/usr/local/bin/hello.sh", config)

    Déploiement d'un script Python CLI:

        from linux_python_utils.scripts import (
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
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from linux_python_utils.logging import Logger
from linux_python_utils.filesystem import FileManager
from linux_python_utils.scripts.config import BashScriptConfig, PythonCliConfig
from linux_python_utils.scripts.checker import ScriptChecker
from linux_python_utils.scripts.paths import ScriptPaths
from linux_python_utils.scripts.report import InstallReport


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
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Vérifie si un script existe déjà.

        Args:
            path: Chemin du script à vérifier.

        Returns:
            True si le script existe, False sinon.
        """
        pass


class BashScriptInstaller(ScriptInstaller):
    """Installateur de scripts bash pour systèmes Linux.

    Cette classe gère la création de scripts bash sur le système
    de fichiers, incluant la génération du contenu et les
    permissions d'exécution.

    Attributes:
        logger: Instance de Logger pour la journalisation.
        file_manager: Gestionnaire de fichiers pour les opérations I/O.
        default_mode: Permissions par défaut (0o755).

    Example:
        >>> installer = BashScriptInstaller(logger, file_manager)
        >>> config = BashScriptConfig(exec_command="ls -la")
        >>> installer.install("/tmp/test.sh", config)
        True
    """

    def __init__(
        self,
        logger: Logger,
        file_manager: FileManager,
        default_mode: int = 0o755
    ) -> None:
        """Initialise l'installateur avec ses dépendances.

        Args:
            logger: Instance de Logger pour la journalisation.
            file_manager: Gestionnaire de fichiers.
            default_mode: Permissions par défaut pour les scripts.
        """
        self._logger: Logger = logger
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
            self._logger.log_info(
                f"Le script {path} existe déjà. "
                "Aucune modification apportée."
            )
            return True

        script_content: str = config.to_bash_script()

        if not self._file_manager.create_file(path, script_content):
            self._logger.log_error(f"Impossible de créer le script {path}")
            return False

        if not self._set_executable(path):
            return False

        self._logger.log_info(f"Script {path} installé avec succès.")
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
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fchmod(fd, self._default_mode)
            finally:
                os.close(fd)
            return True
        except OSError as e:
            self._logger.log_error(
                f"Impossible de rendre le script exécutable : {e}"
            )
            return False


_WRAPPER_SYSTEM = """\
#!/bin/bash
# Généré automatiquement par linux_python_utils
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
# Généré automatiquement par linux_python_utils
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
        _logger: Logger pour la journalisation.
        _checker: Implémentation de ScriptChecker.
    """

    _PYTHON_EXEC: str = "/usr/bin/python3"

    def __init__(
        self,
        logger: Logger,
        checker: ScriptChecker,
    ) -> None:
        """Initialise avec les dépendances injectées.

        Args:
            logger: Instance de Logger.
            checker: Implémentation de ScriptChecker.
        """
        self._logger = logger
        self._checker = checker

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

        if not self._checker.check_python():
            return InstallReport(
                success=False,
                app_name=config.name,
                deploy_type=config.deploy_type,
                install_path=paths.bin_path,
                warnings=["python3 indisponible ou version insuffisante"],
            )

        pyproject_path = config.source_dir / "pyproject.toml"
        try:
            pyproject_data = self._checker.read_pyproject(
                pyproject_path
            )
        except (FileNotFoundError, ValueError) as exc:
            self._logger.log_error(str(exc))
            return InstallReport(
                success=False,
                app_name=config.name,
                deploy_type=config.deploy_type,
                install_path=paths.bin_path,
                warnings=[str(exc)],
            )

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

        needs_wrapper = (
            config.generate_wrapper
            and not pyproject_data.get("scripts")
        )

        if needs_wrapper:
            if confirm_wrapper:
                print(
                    f"\nAucun [project.scripts] détecté.\n"
                    f"Générer un wrapper bash"
                    f" → {paths.bin_path} ? [o/N] ",
                    end="",
                    flush=True,
                )
                answer = input().strip().lower()
                if answer not in ("o", "oui", "y", "yes"):
                    return InstallReport(
                        success=False,
                        app_name=config.name,
                        deploy_type=config.deploy_type,
                        install_path=paths.bin_path,
                        missing_deps=missing,
                        installed_deps=installed,
                        total_deps=total,
                        install_command=install_cmd,
                        warnings=["Wrapper refusé par l'utilisateur"],
                    )
            wrapper_content = self._generate_wrapper_content(
                config, paths
            )
            self._write_wrapper(wrapper_content, paths.bin_path)

        if not self._run_uv_install(config):
            return InstallReport(
                success=False,
                app_name=config.name,
                deploy_type=config.deploy_type,
                install_path=paths.bin_path,
                missing_deps=missing,
                installed_deps=installed,
                total_deps=total,
                install_command=install_cmd,
                warnings=warnings + ["Échec de uv tool install"],
            )

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
        """Écrit le wrapper bash sur disque et le rend exécutable.

        Utilise O_NOFOLLOW + fchmod (TOCTOU-safe) pour les permissions.

        Args:
            content: Contenu du script bash.
            target_path: Chemin de destination.

        Raises:
            OSError: Si l'écriture ou chmod échoue.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        fd = os.open(str(target_path), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fchmod(fd, 0o755)  # nosec B103
        finally:
            os.close(fd)
        self._logger.log_info(f"Wrapper écrit : {target_path}")

    def _run_uv_install(self, config: PythonCliConfig) -> bool:
        """Lance uv tool install pour déployer le script CLI.

        Args:
            config: Configuration du déploiement.

        Returns:
            True si l'installation uv a réussi, False sinon.
        """
        uv_path = shutil.which("uv")
        if uv_path is None:
            self._logger.log_error(
                "uv non trouvé — installez uv : pip install uv"
            )
            return False

        if config.deploy_type == "system":
            cmd = [
                "sudo", uv_path, "tool", "install",
                "--python", self._PYTHON_EXEC,
                "--editable",
                str(config.source_dir),
            ]
        else:
            cmd = [
                uv_path, "tool", "install",
                "--editable", str(config.source_dir),
            ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True
            )
        except FileNotFoundError:
            self._logger.log_error(
                f"uv non trouvé à {uv_path}"
            )
            return False

        if result.returncode != 0:
            self._logger.log_error(
                f"uv tool install a échoué : {result.stderr.strip()}"
            )
            return False

        return True


