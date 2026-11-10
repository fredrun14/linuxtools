"""CLI ``linuxtools-dev`` : sous-commande ``bump-consumers``.

Racine de composition : construit l'exécuteur et le logger, vérifie
l'environnement, boucle sur les consommateurs et rend le rapport.
Lancée par ``python -m linuxtools.devtools`` (aucun point d'entrée).
"""

# stdlib
import argparse
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

# Any est inévitable : argparse._SubParsersAction est une API privée
from typing import Any

# local
from linuxtools.cli.base import CliApplication, CliCommand
from linuxtools.cli.dry_run import add_dry_run_argument
from linuxtools.commands.base import CommandExecutor
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.devtools.bumper import (
    CO_AUTHOR_RE,
    TAG_RE,
    ConsumerBumper,
)
from linuxtools.devtools.discovery import discover_consumers
from linuxtools.devtools.manifest import LINUXTOOLS_URL
from linuxtools.devtools.report import BumpOutcome, exit_code, format_report
from linuxtools.logging.base import Logger
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.logging.file_logger import FileLogger
from linuxtools.logging.paths import default_log_dir

APP_NAME = "linuxtools-dev"
DEFAULT_CO_AUTHOR = "Claude Sonnet 5.5 <noreply@anthropic.com>"
FORBIDDEN_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "UV_FROZEN",
    "UV_LOCKED",
    "UV_NO_SYNC",
    "UV_PROJECT",
    "UV_PROJECT_ENVIRONMENT",
)
_MIN_GIT = (2, 32)
_GIT_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)")

ExecutorFactory = Callable[[Logger, bool], CommandExecutor]


class _UsageError(Exception):
    """Usage ou environnement invalide (code de sortie 2)."""


class BumpConsumersCommand(CliCommand):
    """Sous-commande ``bump-consumers`` : monte le pin sur les projets."""

    def __init__(
        self,
        executor_factory: ExecutorFactory | None = None,
        linuxtools_dir: Path | None = None,
    ) -> None:
        """Initialise la commande.

        Args:
            executor_factory: Fabrique ``(logger, dry_run) -> executor``
                (défaut : ``LinuxCommandExecutor``).
            linuxtools_dir: Répertoire de travail de la vérification du
                tag (facultatif, doit exister ; ``--linuxtools-dir``
                l'emporte). Le dépôt interrogé est toujours l'URL du pin.
        """
        self._executor_factory = executor_factory or self.make_executor
        self._linuxtools_dir = linuxtools_dir

    @property
    def name(self) -> str:
        """Retourne le nom de la sous-commande."""
        return "bump-consumers"

    @staticmethod
    def make_executor(logger: Logger, dry_run: bool) -> CommandExecutor:
        """Construit l'exécuteur réel (double barrière en dry-run)."""
        return LinuxCommandExecutor(logger=logger, dry_run=dry_run)

    # Any : voir CliCommand.register (type privé de la stdlib).
    def register(self, subparsers: Any) -> None:  # noqa: ANN401
        """Enregistre la sous-commande et ses arguments."""
        parser = subparsers.add_parser(
            self.name,
            help="Monter le pin linuxtools des projets consommateurs.",
        )
        parser.add_argument("tag", help="Tag cible, au format vX.Y.Z.")
        parser.add_argument(
            "--root",
            type=Path,
            default=Path("~/PycharmProjects").expanduser(),
            help="Dossier contenant les dépôts (défaut : %(default)s).",
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--only",
            action="append",
            default=[],
            metavar="NOM",
            help="Ne traiter que ce projet (répétable).",
        )
        group.add_argument(
            "--exclude",
            action="append",
            default=[],
            metavar="NOM",
            help="Ignorer ce projet (répétable).",
        )
        add_dry_run_argument(parser)
        parser.add_argument(
            "--linuxtools-dir",
            type=Path,
            default=None,
            dest="linuxtools_dir",
            metavar="DOSSIER",
            help=(
                "Répertoire de travail de la vérification du tag (facultatif, "
                "doit exister). Le tag est vérifié sur l'URL du pin, pas "
                "sur ce dossier."
            ),
        )
        parser.add_argument(
            "--no-push",
            action="store_true",
            dest="no_push",
            help="Committer sans pousser (statut COMMITÉ).",
        )
        parser.add_argument(
            "--co-authored-by",
            dest="co_author",
            default=DEFAULT_CO_AUTHOR,
            help="Trailer Co-Authored-By (défaut : %(default)s).",
        )

    def execute(self, args: argparse.Namespace) -> None:
        """Vérifie l'environnement, monte chaque projet, rend le rapport.

        Sortie : 0 (succès), 1 (au moins un échec), 2 (usage ou
        environnement invalide).
        """
        try:
            outcomes = self._run(args)
        except _UsageError as exc:
            print(f"{APP_NAME} : {exc}", file=sys.stderr)
            sys.exit(2)
        if not outcomes:
            print("aucun consommateur à traiter")
        else:
            print(format_report(outcomes))
        sys.exit(exit_code(outcomes))

    # -- internes ------------------------------------------------------

    def _run(self, args: argparse.Namespace) -> list[BumpOutcome]:
        """Contrôles d'entrée puis boucle sur les consommateurs."""
        self._check_arguments(args)
        logger: Logger = (
            ConsoleLogger() if args.dry_run else self._file_logger()
        )
        executor = self._executor_factory(logger, args.dry_run)
        self._check_tools(executor)
        self._check_tag_exists(executor, args.tag, args.linuxtools_dir)
        try:
            consumers = discover_consumers(args.root, args.only, args.exclude)
        except ValueError as exc:
            raise _UsageError(str(exc)) from exc
        bumper = ConsumerBumper(
            executor,
            logger,
            tag=args.tag,
            root=args.root,
            dry_run=args.dry_run,
            push=not args.no_push,
            co_author=args.co_author,
        )
        return [bumper.bump(consumer) for consumer in consumers]

    @staticmethod
    def _check_arguments(args: argparse.Namespace) -> None:
        """Refus d'usage avant tout accès au système (exit 2)."""
        if os.geteuid() == 0:
            raise _UsageError("exécution en root refusée")
        defined = [n for n in FORBIDDEN_ENV if n in os.environ]
        if defined:
            raise _UsageError(
                "variable(s) d'environnement à retirer : " + ", ".join(defined)
            )
        if not TAG_RE.match(args.tag):
            raise _UsageError(f"tag invalide : {args.tag!r} (vX.Y.Z)")
        if not CO_AUTHOR_RE.match(args.co_author):
            raise _UsageError(f"co-auteur invalide : {args.co_author!r}")
        if not args.root.is_dir():
            raise _UsageError(f"dossier --root introuvable : {args.root}")

    @staticmethod
    def _file_logger() -> FileLogger:
        """Journal fichier horodaté sous le dossier de logs par défaut."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = default_log_dir(APP_NAME) / f"bump-consumers-{stamp}.log"
        return FileLogger(path)

    @staticmethod
    def _check_tools(executor: CommandExecutor) -> None:
        """Exige ``git`` >= 2.32 et ``uv``."""
        git = executor.probe(["git", "--version"])
        match = _GIT_VERSION_RE.search(git.stdout)
        if not git.success or match is None:
            raise _UsageError("git introuvable ou version illisible")
        if (int(match[1]), int(match[2])) < _MIN_GIT:
            raise _UsageError(
                f"git >= {_MIN_GIT[0]}.{_MIN_GIT[1]} requis "
                f"({git.stdout.strip()})"
            )
        if not executor.probe(["uv", "--version"]).success:
            raise _UsageError("uv introuvable")

    def _work_dir(self, option: Path | None) -> str | None:
        """Répertoire de travail de la vérification du tag (ou None)."""
        directory = option if option is not None else self._linuxtools_dir
        if directory is None:
            return None
        if not directory.is_dir():
            raise _UsageError(
                f"--linuxtools-dir : dossier inexistant ({directory})"
            )
        return str(directory)

    def _check_tag_exists(
        self, executor: CommandExecutor, tag: str, option: Path | None
    ) -> None:
        """Le tag doit exister sur le dépôt de l'URL du pin (Forgejo).

        Aucun dépôt local n'est requis : ``ls-remote`` interroge l'URL
        épinglée, qui ne peut donc pas désigner un autre dépôt.
        """
        result = executor.probe(
            ["git", "ls-remote", "--tags", LINUXTOOLS_URL, f"refs/tags/{tag}"],
            cwd=self._work_dir(option),
        )
        if not result.success:
            raise _UsageError(
                f"impossible de vérifier le tag {tag} : "
                f"{result.stderr.strip()}"
            )
        if not result.stdout.strip():
            raise _UsageError(f"le tag {tag} n'existe pas dans linuxtools")


def main() -> None:
    """Point d'entrée de ``python -m linuxtools.devtools``."""
    CliApplication(
        prog=APP_NAME,
        description="Outillage de mainteneur de linuxtools.",
        commands=[BumpConsumersCommand()],
    ).run()
