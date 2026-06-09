"""Module de génération et installation de scripts pour systèmes Linux."""

from linux_python_utils.scripts.checker import (
    LinuxScriptChecker,
    ScriptChecker,
)
from linux_python_utils.scripts.config import (
    BashScriptConfig,
    PythonCliConfig,
)
from linux_python_utils.scripts.installer import (
    BashScriptInstaller,
    CliInstaller,
    LinuxCliInstaller,
    ScriptInstaller,
)
from linux_python_utils.scripts.paths import ScriptPaths
from linux_python_utils.scripts.report import (
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
