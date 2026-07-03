"""Framework CLI basé sur le Command Pattern.

Fournit une interface abstraite CliCommand et un orchestrateur
CliApplication pour structurer les CLIs argparse selon SOLID.
"""

# stdlib
import argparse
from abc import ABC, abstractmethod
# Any est inévitable : argparse._SubParsersAction est une API privée stdlib
from typing import Any

# local
from linuxtools.logging.base import Logger


class CliCommand(ABC):
    """Interface abstraite pour une sous-commande CLI.

    Chaque commande est responsable de :
    - Déclarer son nom (name)
    - S'enregistrer dans argparse (register)
    - S'exécuter (execute)

    Example:
        >>> class MyCommand(CliCommand):
        ...     @property
        ...     def name(self) -> str:
        ...         return "my-cmd"
        ...     def register(self, subparsers: Any) -> None:
        ...         subparsers.add_parser(self.name, help="Ma commande")
        ...     def execute(self, args: argparse.Namespace) -> None:
        ...         print("Exécuté !")
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Retourne le nom de la sous-commande (ex: 'sync')."""
        ...

    @abstractmethod
    def register(self, subparsers: Any) -> None:
        """Enregistre la commande et ses arguments dans argparse.

        Args:
            subparsers: Objet retourné par ``ArgumentParser.add_subparsers()``.
                Typé ``Any`` car ``argparse._SubParsersAction`` est une API
                privée non exposée par la stdlib.
        """
        ...

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> None:
        """Exécute la commande avec les arguments parsés.

        Args:
            args: Namespace argparse après parse_args().
        """
        ...


class CliApplication:
    """Orchestrateur CLI basé sur le Command Pattern.

    Enregistre une liste de CliCommand, parse les arguments
    et dispatche vers la commande appropriée.

    Attributes:
        _prog: Nom du programme (ex: 'fedora-post-install').
        _description: Description affichée dans --help.
        _commands: Liste des commandes enregistrées.

    Example:
        >>> app = CliApplication(
        ...     prog="mon-outil",
        ...     description="Mon outil CLI",
        ...     commands=[SyncCommand(factory), ListCommand(factory)],
        ... )
        >>> app.run()
    """

    def __init__(
        self,
        prog: str,
        description: str,
        commands: list[CliCommand],
        logger: Logger | None = None,
    ) -> None:
        """Initialise l'application avec ses commandes.

        Args:
            prog: Nom du programme pour --help.
            description: Description courte pour --help.
            commands: Liste des commandes disponibles.
            logger: Logger optionnel pour tracer les erreurs de dispatch.
        """
        self._prog = prog
        self._description = description
        self._commands = commands
        self._logger = logger

    def run(self) -> None:
        """Parse sys.argv et dispatche à la commande appropriée.

        Construit le mapping {nom: commande}, parse les arguments,
        puis appelle execute() sur la commande sélectionnée.
        """
        parser = argparse.ArgumentParser(
            prog=self._prog,
            description=self._description,
        )
        subparsers = parser.add_subparsers(
            dest="command",
            required=True,
        )

        command_map: dict[str, CliCommand] = {}
        for cmd in self._commands:
            cmd.register(subparsers)
            command_map[cmd.name] = cmd

        args = parser.parse_args()
        command_map[args.command].execute(args)
