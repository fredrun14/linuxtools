"""Framework CLI basé sur le Command Pattern.

Ce module fournit les briques pour structurer une CLI argparse
selon SOLID : une classe par sous-commande, un orchestrateur, et
un contexte d'exécution simulée.

Command Pattern:
- CliCommand: Interface abstraite pour une sous-commande
- CliApplication: Orchestrateur qui enregistre et dispatche

Mode simulation:
- DryRunContext: Contexte d'affichage des opérations simulées
- add_dry_run_argument: Enregistre --dry-run / -n dans argparse

Exemple d'utilisation:
    import argparse
    from typing import Any

    from linuxtools import FileLogger
    from linuxtools.cli import (
        CliApplication,
        CliCommand,
        add_dry_run_argument,
    )

    class GreetCommand(CliCommand):
        @property
        def name(self) -> str:
            return "greet"

        def register(self, subparsers: Any) -> None:
            parser = subparsers.add_parser(self.name, help="Salue")
            add_dry_run_argument(parser)

        def execute(self, args: argparse.Namespace) -> None:
            print("Bonjour !")

    # Les commandes se déclarent au constructeur, pas via
    # une méthode register() sur l'application elle-même.
    app = CliApplication(
        prog="mon-outil",
        description="Démonstration",
        commands=[GreetCommand()],
        logger=FileLogger("/var/log/app.log"),
    )
    app.run()

Exemple de simulation (aucune écriture disque):
    from linuxtools.cli import DryRunContext

    ctx = DryRunContext(dry_run=args.dry_run)
    ctx.would_create("/etc/mon-outil/config.toml")
    ctx.would_write("/etc/mon-outil/config.toml", "cle=valeur")
"""

# Command Pattern
from linuxtools.cli.base import CliApplication, CliCommand

# Mode simulation
from linuxtools.cli.dry_run import DryRunContext, add_dry_run_argument

__all__ = [
    # Command Pattern
    "CliApplication",
    "CliCommand",
    # Mode simulation
    "DryRunContext",
    "add_dry_run_argument",
]
