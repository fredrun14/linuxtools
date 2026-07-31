"""Module d'exécution de commandes système.

Ce module fournit les briques pour construire, exécuter et
formater des commandes système de manière structurée.

Construction:
- CommandBuilder: Constructeur fluent de commandes

Exécution:
- CommandExecutor: Interface abstraite pour les exécuteurs
- LinuxCommandExecutor: Exécuteur concret via subprocess
- CommandResult: Résultat immuable d'une exécution

Formatage:
- CommandFormatter: Interface abstraite de formatage
- AnsiCommandFormatter: Formatage ANSI coloré (console)
- PlainCommandFormatter: Formatage texte brut (logs fichier)

Exemple d'utilisation:
    from linuxtools import FileLogger
    from linuxtools.commands import (
        CommandBuilder,
        LinuxCommandExecutor,
    )

    logger = FileLogger("/var/log/app.log")
    executor = LinuxCommandExecutor(logger=logger)

    cmd = CommandBuilder("rpm").with_args(["-q", "vim"]).build()
    result = executor.run(cmd)
    if result.return_code == 0:
        print("vim est installé")

Exemple en mode simulation (dry-run):
    # Les commandes mutantes sont simulées, mais une sonde en
    # lecture seule (probe()) s'exécute réellement : le mode
    # dry-run s'appuie sur son résultat pour décider quoi faire.
    # probe() est une façade de run(..., probe=True) : une seule
    # façon d'écrire une sonde, sans risquer d'oublier le drapeau.
    executor = LinuxCommandExecutor(logger=logger, dry_run=True)

    check = CommandBuilder("rpm").with_args(["-q", "vim"]).build()
    installed = executor.probe(check).return_code == 0

    if not installed:
        # Simulée : rien n'est installé pour de vrai.
        executor.run_streaming(
            CommandBuilder("dnf")
            .with_args(["install", "-y", "vim"])
            .build()
        )
"""

# Construction
# Exécution
from linuxtools.commands.base import (
    CommandExecutor,
    CommandResult,
)
from linuxtools.commands.builder import CommandBuilder

# Formatage
from linuxtools.commands.formatter import (
    AnsiCommandFormatter,
    CommandFormatter,
    PlainCommandFormatter,
)
from linuxtools.commands.runner import LinuxCommandExecutor

__all__ = [
    # Construction
    "CommandBuilder",
    # Exécution
    "CommandExecutor",
    "CommandResult",
    "LinuxCommandExecutor",
    # Formatage
    "AnsiCommandFormatter",
    "CommandFormatter",
    "PlainCommandFormatter",
]
