"""Interfaces abstraites pour la gestion idempotente des identités Unix."""

import re
from abc import ABC, abstractmethod

# Convention useradd/groupadd : minuscules, chiffres, tiret, underscore.
# Premier caractère : lettre minuscule ou underscore (pas de tiret).
# Le tiret initial passerait comme option à useradd/groupadd.
_NOM_UNIX = re.compile(r"^[a-z_][a-z0-9_-]*\$?$")


def _valider_nom(nom: str) -> str:
    """Valide un nom Unix (utilisateur ou groupe).

    Args:
        nom: Nom à valider.

    Returns:
        Le nom inchangé si valide.

    Raises:
        ValueError: Si le nom ne respecte pas la convention Unix
            (minuscules, chiffres, tiret, underscore ; pas de tiret initial).
    """
    if not _NOM_UNIX.match(nom):
        raise ValueError(f"Nom Unix invalide : {nom!r}")
    return nom


class GroupManagerBase(ABC):
    """Interface abstraite pour la gestion idempotente des groupes Unix."""

    @abstractmethod
    def ensure_group(self, name: str, gid: int) -> None:
        """Crée ou corrige le groupe Unix avec le GID donné.

        Args:
            name: Nom du groupe.
            gid: GID souhaité.
        """


class UserManagerBase(ABC):
    """Interface abstraite pour la gestion idempotente des utilisateurs Unix."""

    @abstractmethod
    def ensure_user(
        self,
        name: str,
        uid: int,
        shell: str,
        comment: str,
        create_home: bool,
    ) -> None:
        """Crée ou corrige l'utilisateur Unix avec l'UID donné.

        Args:
            name: Nom d'utilisateur.
            uid: UID souhaité.
            shell: Shell de connexion.
            comment: Commentaire GECOS.
            create_home: Créer le répertoire home si absent.
        """

    @abstractmethod
    def ensure_user_groups(
        self,
        username: str,
        groups: list[str],
    ) -> None:
        """Ajoute l'utilisateur aux groupes manquants en une seule commande.

        Args:
            username: Nom d'utilisateur.
            groups: Liste des groupes secondaires souhaités.
        """
