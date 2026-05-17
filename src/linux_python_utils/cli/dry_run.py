"""Support du mode dry-run pour les CLIs linux_python_utils."""

# stdlib
import argparse


class DryRunContext:
    """Contexte d'exécution simulée — aucune modification disque.

    Centralise l'affichage des opérations qui auraient été effectuées
    lorsque le flag --dry-run est actif.

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

        Args:
            path: Chemin du fichier cible.
            content: Contenu qui aurait été écrit.
        """
        print(f"[DRY-RUN] Écriture dans {path} :")
        print(content)

    def would_create(self, path: str) -> None:
        """Annonce la création simulée d'un fichier.

        Args:
            path: Chemin du fichier qui aurait été créé.
        """
        print(f"[DRY-RUN] Création du fichier {path}")

    def would_modify(self, path: str, line: str) -> None:
        """Annonce la modification simulée d'une ligne.

        Args:
            path: Chemin du fichier cible.
            line: Ligne qui aurait été ajoutée ou modifiée.
        """
        print(f"[DRY-RUN] Modification dans {path} : {line}")


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
