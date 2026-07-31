"""Module de génération et installation de scripts pour systèmes Linux.

Couvre deux besoins distincts : générer un script bash wrapper
(exécution + notification), et installer une CLI Python (venv +
dépendances + point d'entrée) selon le standard FHS, en scope
system ou user.

Résolution de chemins FHS:
- ScriptPaths: Calcule data_dir/bin_path selon le scope (system/user)

Génération de script bash:
- BashScriptConfig: Configuration d'un wrapper bash (commande + notification)

Installation d'une CLI Python:
- PythonCliConfig: Configuration du déploiement (venv, extras, wrapper)
- CliInstaller: Interface abstraite d'installation
- LinuxCliInstaller: Orchestre venv + dépendances + `uv tool install`
- ScriptChecker: Interface abstraite de vérification des prérequis
- LinuxScriptChecker: Vérifie python3, pyproject.toml, venv, dépendances
- ScriptInstaller: Interface abstraite pour l'installation de scripts bash
- BashScriptInstaller: Installe un wrapper bash généré via BashScriptConfig

Rapport d'installation:
- InstallReport: Résultat complet d'une installation
- InstalledDependency, MissingDependency: Détail des dépendances vérifiées

Exemple d'utilisation:
    from pathlib import Path
    from linuxtools.scripts import LinuxCliInstaller, PythonCliConfig

    installer = LinuxCliInstaller(logger=logger)
    report = installer.install(PythonCliConfig(
        name="mon-outil",
        deploy_type="user",
        source_dir=Path("/home/user/mon-outil"),
    ))
"""

from linuxtools.scripts.checker import (
    LinuxScriptChecker,
    ScriptChecker,
)
from linuxtools.scripts.config import (
    BashScriptConfig,
    PythonCliConfig,
)
from linuxtools.scripts.installer import (
    BashScriptInstaller,
    CliInstaller,
    LinuxCliInstaller,
    ScriptInstaller,
)
from linuxtools.scripts.paths import ScriptPaths
from linuxtools.scripts.report import (
    InstalledDependency,
    InstallReport,
    MissingDependency,
)

__all__ = [
    "BashScriptConfig",
    "BashScriptInstaller",
    "CliInstaller",
    "InstallReport",
    "InstalledDependency",
    "LinuxCliInstaller",
    "LinuxScriptChecker",
    "MissingDependency",
    "PythonCliConfig",
    "ScriptChecker",
    "ScriptInstaller",
    "ScriptPaths",
]
