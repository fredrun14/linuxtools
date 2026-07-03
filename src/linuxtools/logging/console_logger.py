"""Logger console sans effet de bord fichier.

Implémente l'interface Logger en écrivant uniquement sur stdout/stderr.
Adapté aux contextes légers : dry-run, scripts sans log fichier, tests.
"""

# stdlib
import sys

# local
from linuxtools.logging.ansi_colors import AnsiColors
from linuxtools.logging.base import Logger


class ConsoleLogger(Logger):
    """Logger écrivant sur stdout/stderr sans fichier de log.

    Les messages d'information et de succès sont écrits sur stdout.
    Les avertissements et erreurs sont écrits sur stderr.
    Aucun fichier n'est créé ou modifié.

    Example:
        >>> logger = ConsoleLogger()
        >>> logger.log_info("Démarrage...")   # affiché en bleu
        >>> logger.log_warning("Absent")     # affiché en orange sur stderr
        >>> logger.log_error("Échec")        # affiché en rouge sur stderr
        >>> logger.log_success("OK")         # affiché en vert
    """

    def log_info(self, message: str) -> None:
        """Écrit un message d'information en bleu sur stdout.

        Args:
            message: Message à afficher.
        """
        print(f"{AnsiColors.BLUE}{message}{AnsiColors.RESET}")

    def log_warning(self, message: str) -> None:
        """Écrit un avertissement en orange sur stderr.

        Args:
            message: Message à afficher.
        """
        print(
            f"{AnsiColors.ORANGE}WARNING: {message}{AnsiColors.RESET}",
            file=sys.stderr,
        )

    def log_error(self, message: str) -> None:
        """Écrit une erreur en rouge sur stderr.

        Args:
            message: Message à afficher.
        """
        print(
            f"{AnsiColors.RED}ERROR: {message}{AnsiColors.RESET}",
            file=sys.stderr,
        )

    def log_success(self, message: str) -> None:
        """Écrit un message de succès en vert sur stdout.

        Args:
            message: Message à afficher.
        """
        print(f"{AnsiColors.GREEN}{message}{AnsiColors.RESET}")
