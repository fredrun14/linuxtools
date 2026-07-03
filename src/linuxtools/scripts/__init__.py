"""Module de génération et installation de scripts pour systèmes Linux."""

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
    InstallReport,
    InstalledDependency,
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
