"""Helpers Fedora / RPM.

Ce module regroupe les commandes spécifiques à Fedora, isolées du
reste de la bibliothèque (cf. docstring de `linuxtools.distro`).
"""

from linuxtools.commands.base import CommandExecutor
from linuxtools.commands.builder import CommandBuilder


def fedora_version(executor: CommandExecutor) -> str:
    """Retourne la version Fedora courante via rpm.

    Args:
        executor: Exécuteur de commandes injecté.

    Returns:
        Chaîne de version (ex. "44"), ou "" si indisponible.
    """
    cmd = CommandBuilder("rpm").with_args(["--eval", "%fedora"]).build()
    result = executor.probe(cmd)
    return result.stdout.strip() if result.return_code == 0 else ""
