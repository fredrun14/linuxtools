"""Interfaces abstraites pour la gestion des erreurs.

Hiérarchie d'exceptions commune.
"""

import sys
from abc import ABC, abstractmethod


class ErrorHandler(ABC):
    """Interface de base pour les handlers d'erreurs.

    Chaque implémentation concrète définit une stratégie
    de traitement des erreurs (affichage console, logging, etc.).
    """

    @abstractmethod
    def handle(self, error: Exception) -> None:
        """Traite une erreur.

        Args:
            error: L'exception à traiter.
        """
        ...


class ErrorHandlerChain:
    """Diffuse les erreurs à tous les handlers enregistrés.

    Chaque erreur est transmise à tous les handlers dans l'ordre
    d'ajout (ex: console puis logger).
    """

    def __init__(self) -> None:
        """Initialise la chaîne avec une liste vide de handlers."""
        self.handlers: list[ErrorHandler] = []

    def add_handler(self, handler: ErrorHandler) -> None:
        """Ajoute un handler à la chaîne.

        Args:
            handler: Le handler d'erreurs à ajouter.
        """
        self.handlers.append(handler)

    def handle(self, error: Exception) -> None:
        """Fait passer l'erreur à travers tous les handlers.

        Args:
            error: L'exception à diffuser.
        """
        for handler in self.handlers:
            handler.handle(error)

    def handle_and_exit(self, error: Exception, exit_code: int = 1) -> None:
        """Gère l'erreur et termine le programme.

        Args:
            error: L'exception à traiter avant la sortie.
            exit_code: Code de sortie du programme (défaut: 1).
        """
        self.handle(error)
        sys.exit(exit_code)
