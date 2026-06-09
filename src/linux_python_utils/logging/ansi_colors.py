"""Constantes ANSI pour la colorisation de la sortie console."""
from enum import StrEnum


class AnsiColors(StrEnum):
    """Codes ANSI de colorisation terminale.

    Attributes:
        BLUE: Texte bleu — messages d'information.
        ORANGE: Texte orange/jaune — avertissements.
        RED: Texte rouge — erreurs.
        GREEN: Texte vert — succès.
        RESET: Réinitialise la couleur.

    Example:
        >>> print(f"{AnsiColors.GREEN}OK{AnsiColors.RESET}")
        \x1b[32mOK\x1b[0m
    """

    BLUE = "\033[34m"
    ORANGE = "\033[33m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    RESET = "\033[0m"
