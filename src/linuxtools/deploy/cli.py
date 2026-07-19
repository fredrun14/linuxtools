"""Sous-commande CLI pour le module deploy.

DeployCommand est une CliCommand prête à être enregistrée dans le
CliApplication d'un projet consommateur (linuxtools n'a pas de
binaire CLI propre). Même pattern que les installateurs
systemd/scripts, mais exposé ici en Command Pattern.
"""

# stdlib
import argparse
import sys
from pathlib import Path

# Any est inévitable : argparse._SubParsersAction est une API privée
from typing import Any

# local
from linuxtools.cli.base import CliCommand
from linuxtools.cli.dry_run import add_dry_run_argument
from linuxtools.deploy.deployer import Deployer
from linuxtools.deploy.models import (
    DeployConfig,
    DeployTarget,
    VerificationSpec,
)
from linuxtools.logging.base import Logger


class DeployCommand(CliCommand):
    """Sous-commande `deploy` : déploie/met à jour un outil Python.

    Attributes:
        _logger: Logger optionnel, propagé au Deployer construit.

    Example:
        >>> app = CliApplication(
        ...     prog="mon-outil",
        ...     description="Mon outil CLI",
        ...     commands=[DeployCommand(logger)],
        ... )
        >>> app.run()
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise la commande avec un logger optionnel.

        Args:
            logger: Logger optionnel, propagé au Deployer.for_target.
        """
        self._logger = logger

    @property
    def name(self) -> str:
        """Retourne le nom de la sous-commande."""
        return "deploy"

    def register(self, subparsers: Any) -> None:
        """Enregistre la commande deploy et ses arguments.

        Args:
            subparsers: Objet retourné par
                ``ArgumentParser.add_subparsers()``.
        """
        parser = subparsers.add_parser(
            self.name,
            help="Déploie/met à jour un outil Python sur un hôte.",
        )
        parser.add_argument(
            "--source",
            type=Path,
            default=None,
            help=(
                "Répertoire source local (auto-détecté depuis le "
                "cwd si omis)."
            ),
        )
        parser.add_argument(
            "--venv",
            type=Path,
            required=True,
            help="Venv cible sur l'hôte.",
        )
        parser.add_argument(
            "--dest",
            type=Path,
            required=True,
            help="Répertoire où déposer le source sur l'hôte cible.",
        )
        parser.add_argument(
            "--host",
            default=None,
            help="Hôte distant (omis = déploiement local).",
        )
        parser.add_argument(
            "--user",
            default=None,
            help="Utilisateur SSH (ignoré si --host est omis).",
        )
        parser.add_argument(
            "--ssh-option",
            action="append",
            default=[],
            dest="ssh_option",
            help="Option ssh supplémentaire (répétable).",
        )
        parser.add_argument(
            "--cli-bin",
            default=None,
            dest="cli_bin",
            help="Nom de l'exécutable CLI dans le venv, pour tester "
            "les sous-commandes.",
        )
        parser.add_argument(
            "--import",
            action="append",
            default=[],
            dest="imports",
            help="Module à importer pour vérification (répétable).",
        )
        parser.add_argument(
            "--subcommand",
            action="append",
            default=[],
            dest="subcommands",
            help="Sous-commande attendue, testée via --help "
            "(répétable).",
        )
        parser.add_argument(
            "--regression",
            nargs="*",
            default=None,
            help="Commande de non-régression à rejouer sur l'hôte.",
        )
        parser.add_argument(
            "--recreate-venv",
            action="store_true",
            dest="recreate_venv",
            help="Recrée le venv proprement avant d'installer.",
        )
        add_dry_run_argument(parser)

    def execute(self, args: argparse.Namespace) -> None:
        """Construit la configuration et lance le déploiement.

        Args:
            args: Namespace argparse après parse_args().
        """
        target = DeployTarget(
            host=args.host,
            user=args.user,
            ssh_options=tuple(args.ssh_option),
        )
        verification = VerificationSpec(
            imports=tuple(args.imports),
            subcommands=tuple(args.subcommands),
            regression_command=(
                tuple(args.regression) if args.regression else None
            ),
        )
        config = DeployConfig(
            source_dir=args.source,
            venv_path=args.venv,
            remote_source_dir=args.dest,
            target=target,
            verification=verification,
            cli_bin=args.cli_bin,
            recreate_venv=args.recreate_venv,
        )

        deployer = Deployer.for_target(
            target, logger=self._logger, dry_run=args.dry_run
        )
        report = deployer.deploy(config)
        print(report.format_summary())
        sys.exit(0 if report.success else 1)
