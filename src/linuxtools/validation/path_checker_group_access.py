"""Validateur d'accès groupe sur un répertoire."""

import grp
import os
import stat
from pathlib import Path

from linuxtools.validation.base import Validator


class PathCheckerGroupAccess(Validator):
    """Vérifie qu'un répertoire est accessible rwx par un groupe donné.

    Vérifie dans cet ordre :
    1. que le répertoire appartient au groupe spécifié,
    2. que le groupe possède les permissions rwx,
    3. optionnellement, que le bit setgid est positionné
       (héritage de groupe pour les nouveaux fichiers).

    Utilise ``os.stat`` (suit les liens symboliques) pour inspecter
    la cible réelle — adapté aux points de montage NFS.

    Lève des exceptions standard (FileNotFoundError, PermissionError,
    KeyError) pour rester générique. Le consommateur peut les wrapper
    vers ses propres exceptions métier.

    Example:
        >>> checker = PathCheckerGroupAccess(
        ...     "/media/nas/keepass",
        ...     "ff_home",
        ...     require_setgid=True,
        ... )
        >>> checker.validate()
    """

    def __init__(
        self,
        path: str | Path,
        group: str,
        *,
        require_setgid: bool = True,
    ) -> None:
        """Initialise le validateur.

        Args:
            path: Répertoire à vérifier.
            group: Nom du groupe Unix attendu (ex : ``'ff_home'``).
            require_setgid: Si ``True`` (défaut), vérifie que le bit
                setgid est positionné — les nouveaux fichiers héritent
                alors du groupe propriétaire (comportement attendu sur
                un partage NFS public).
        """
        self._path = Path(path)
        self._group = group
        self._require_setgid = require_setgid

    def validate(self) -> None:
        """Vérifie l'appartenance au groupe, les permissions rwx et setgid.

        Raises:
            FileNotFoundError: Si le répertoire n'existe pas.
            KeyError: Si le groupe n'existe pas sur le système.
            PermissionError: Si le répertoire n'appartient pas au groupe,
                si les permissions rwx sont insuffisantes, ou si le bit
                setgid est absent (quand ``require_setgid=True``).
        """
        expected_gid = grp.getgrnam(self._group).gr_gid

        try:
            st = os.stat(self._path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Répertoire introuvable : {self._path}"
            ) from exc

        if st.st_gid != expected_gid:
            actual = self._gid_to_name(st.st_gid)
            raise PermissionError(
                f"{self._path} appartient au groupe '{actual}'"
                f" (GID {st.st_gid}),"
                f" attendu '{self._group}' (GID {expected_gid})."
            )

        missing = self._missing_group_bits(st.st_mode)
        if missing:
            raise PermissionError(
                f"{self._path} : permissions groupe insuffisantes"
                f" (manquants : {missing})."
                f" Corrigez avec : chmod g+{missing} {self._path}"
            )

        if self._require_setgid and not (st.st_mode & stat.S_ISGID):
            raise PermissionError(
                f"{self._path} : bit setgid absent."
                f" Corrigez avec : chmod g+s {self._path}"
            )

    @staticmethod
    def _missing_group_bits(mode: int) -> str:
        """Retourne les bits rwx manquants pour le groupe.

        Args:
            mode: Mode de fichier (``st_mode``).

        Returns:
            Chaîne des bits manquants (ex : ``'wx'``), vide si complets.
        """
        missing = ""
        if not (mode & stat.S_IRGRP):
            missing += "r"
        if not (mode & stat.S_IWGRP):
            missing += "w"
        if not (mode & stat.S_IXGRP):
            missing += "x"
        return missing

    @staticmethod
    def _gid_to_name(gid: int) -> str:
        """Résout un GID en nom de groupe, ou retourne le GID si inconnu.

        Args:
            gid: Identifiant numérique du groupe.

        Returns:
            Nom du groupe ou représentation entière du GID.
        """
        try:
            return grp.getgrgid(gid).gr_name
        except KeyError:
            return str(gid)
