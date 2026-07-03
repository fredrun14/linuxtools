"""Framework CLI basé sur le Command Pattern.

Exporte :
    CliApplication: Orchestrateur CLI.
    CliCommand: Interface abstraite pour une sous-commande.
    DryRunContext: Contexte d'exécution simulée.
    add_dry_run_argument: Enregistre --dry-run / -n dans argparse.
"""

from linuxtools.cli.base import CliApplication, CliCommand
from linuxtools.cli.dry_run import DryRunContext, add_dry_run_argument

__all__ = [
    "CliApplication",
    "CliCommand",
    "DryRunContext",
    "add_dry_run_argument",
]
