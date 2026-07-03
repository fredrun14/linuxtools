"""Module d'exécution de commandes système.

Ce module fournit des classes pour construire et exécuter
des commandes système de manière structurée.

Classes disponibles :
    AnsiCommandFormatter : Formatage ANSI coloré (console).
    CommandBuilder : Constructeur fluent de commandes.
    CommandExecutor : Interface abstraite pour les exécuteurs.
    CommandFormatter : Interface abstraite de formatage.
    CommandResult : Résultat immuable d'une exécution.
    LinuxCommandExecutor : Exécuteur concret via subprocess.
    PlainCommandFormatter : Formatage texte brut (logs fichier).
"""

from linuxtools.commands.base import (
    CommandExecutor,
    CommandResult,
)
from linuxtools.commands.builder import CommandBuilder
from linuxtools.commands.formatter import (
    AnsiCommandFormatter,
    CommandFormatter,
    PlainCommandFormatter,
)
from linuxtools.commands.runner import LinuxCommandExecutor

__all__ = [
    "AnsiCommandFormatter",
    "CommandBuilder",
    "CommandExecutor",
    "CommandFormatter",
    "CommandResult",
    "LinuxCommandExecutor",
    "PlainCommandFormatter",
]
