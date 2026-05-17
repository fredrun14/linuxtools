"""Framework CLI basé sur le Command Pattern.

Provides:
    CliCommand: Interface abstraite pour une sous-commande.
    CliApplication: Orchestrateur CLI.
    DryRunContext: Contexte d'exécution simulée.
    add_dry_run_argument: Enregistre --dry-run / -n dans argparse.
"""

from linux_python_utils.cli.base import CliApplication, CliCommand
from linux_python_utils.cli.dry_run import DryRunContext, add_dry_run_argument

__all__ = [
    "CliCommand",
    "CliApplication",
    "DryRunContext",
    "add_dry_run_argument",
]
