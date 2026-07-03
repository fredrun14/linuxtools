"""Support du mode dry-run pour les CLIs linuxtools."""

# stdlib
import argparse

_DRY_RUN_PREFIX = "[DRY-RUN]"


class DryRunContext:
    """Contexte d'exécution simulée — aucune modification disque.

    Centralise l'affichage des opérations qui auraient été effectuées
    lorsque le flag --dry-run est actif.

    Pas d'injection de Logger : toutes les méthodes ``would_*`` sont de
    purs effets de bord ``print()`` vers stdout. Injecter un Logger
    ajouterait une dépendance externe sans valeur ajoutée — cette classe
    est une couche de présentation, pas une couche applicative.

    Attributes:
        dry_run: True si le mode simulation est actif.

    Example:
        >>> ctx = DryRunContext(dry_run=True)
        >>> ctx.would_write("/etc/foo.conf", "key=value")
        [DRY-RUN] Écriture dans /etc/foo.conf :
        key=value
    """

    def __init__(self, dry_run: bool = False) -> None:
        """Initialise le contexte dry-run.

        Args:
            dry_run: Active la simulation si True.
        """
        self.dry_run = dry_run

    def would_write(self, path: str, content: str) -> None:
        """Affiche ce qui aurait été écrit sans modifier le disque.

        N'affiche rien si dry_run est False.

        Args:
            path: Chemin du fichier cible.
            content: Contenu qui aurait été écrit.
        """
        if not self.dry_run:
            return
        print(f"{_DRY_RUN_PREFIX} Écriture dans {path} :")
        print(content)

    def would_create(self, path: str) -> None:
        """Annonce la création simulée d'un fichier.

        N'affiche rien si dry_run est False.

        Args:
            path: Chemin du fichier qui aurait été créé.
        """
        if not self.dry_run:
            return
        print(f"{_DRY_RUN_PREFIX} Création du fichier {path}")

    def would_modify(self, path: str, line: str) -> None:
        """Annonce la modification simulée d'une ligne.

        N'affiche rien si dry_run est False.

        Args:
            path: Chemin du fichier cible.
            line: Ligne qui aurait été ajoutée ou modifiée.
        """
        if not self.dry_run:
            return
        print(f"{_DRY_RUN_PREFIX} Modification dans {path} : {line}")

    def would_delete(self, path: str) -> None:
        """Annonce la suppression simulée d'un fichier ou répertoire.

        N'affiche rien si dry_run est False.

        Args:
            path: Chemin qui aurait été supprimé.
        """
        if not self.dry_run:
            return
        print(f"{_DRY_RUN_PREFIX} Suppression de {path}")

    def would_run_command(self, cmd: str) -> None:
        """Annonce l'exécution simulée d'une commande système.

        N'affiche rien si dry_run est False.

        Args:
            cmd: Commande qui aurait été exécutée.
        """
        if not self.dry_run:
            return
        print(f"{_DRY_RUN_PREFIX} Commande : {cmd}")


def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    """Ajoute les flags --dry-run / -n à un ArgumentParser.

    Après l'appel, ``args.dry_run`` sera True si le flag est passé,
    False sinon.

    Args:
        parser: Instance argparse à enrichir.

    Example:
        >>> import argparse
        >>> parser = argparse.ArgumentParser()
        >>> add_dry_run_argument(parser)
        >>> args = parser.parse_args(["--dry-run"])
        >>> args.dry_run
        True
    """
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        dest="dry_run",
        default=False,
        help="Simuler les modifications sans écrire sur le disque.",
    )
