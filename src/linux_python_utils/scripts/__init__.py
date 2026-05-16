"""
Module de génération et installation de scripts pour systèmes Linux.

Classes disponibles:
- BashScriptConfig: Configuration pour générer des scripts bash
  avec support optionnel des notifications.
- PythonCliConfig: Configuration pour déployer un script Python CLI
  (system ou user scope, avec vérification des dépendances).
- ScriptInstaller: Interface abstraite pour l'installation de scripts.
- BashScriptInstaller: Implémentation pour installer des scripts bash.
- CliInstaller: Interface abstraite pour l'installation de scripts CLI.
- LinuxCliInstaller: Installateur CLI Linux (uv + wrapper bash).
- ScriptPaths: Résolution des chemins FHS via platformdirs.
- ScriptChecker: Interface abstraite pour les vérifications pré-install.
- LinuxScriptChecker: Vérification python3, pyproject.toml, dépendances.
- InstallReport: Rapport complet du déploiement.
- MissingDependency: Dépendance manquante dans le rapport.
"""

from linux_python_utils.scripts.config import (
    BashScriptConfig,
    PythonCliConfig,
)
from linux_python_utils.scripts.installer import (
    ScriptInstaller,
    BashScriptInstaller,
    CliInstaller,
    LinuxCliInstaller,
)
from linux_python_utils.scripts.paths import ScriptPaths
from linux_python_utils.scripts.checker import (
    ScriptChecker,
    LinuxScriptChecker,
)
from linux_python_utils.scripts.report import (
    InstallReport,
    MissingDependency,
)

__all__ = [
    "BashScriptConfig",
    "PythonCliConfig",
    "ScriptInstaller",
    "BashScriptInstaller",
    "CliInstaller",
    "LinuxCliInstaller",
    "ScriptPaths",
    "ScriptChecker",
    "LinuxScriptChecker",
    "InstallReport",
    "MissingDependency",
]
