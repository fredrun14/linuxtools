"""Gestion idempotente des groupes Unix."""

import grp

from linuxtools.commands import CommandBuilder, LinuxCommandExecutor
from linuxtools.commands.base import CommandExecutor
from linuxtools.identity.base import (
    GroupManagerBase,
    _run_or_raise,
    _valider_nom,
)
from linuxtools.logging import Logger


class LinuxGroupManager(GroupManagerBase):
    """Crée ou corrige les groupes Unix via groupadd / groupmod."""

    def __init__(
        self,
        logger: Logger | None = None,
        executor: CommandExecutor | None = None,
    ) -> None:
        """Initialise le gestionnaire avec ses dépendances.

        Args:
            logger: Logger optionnel pour les messages d'information.
            executor: Exécuteur de commandes optionnel ; construit par
                défaut si absent.
        """
        self._logger = logger
        self._executor = executor or LinuxCommandExecutor(logger=logger)
        self._prefix = "[LinuxGroupManager]"

    def ensure_group(self, name: str, gid: int) -> None:
        """Crée ou corrige le groupe Unix avec le GID donné.

        Args:
            name: Nom du groupe (convention Unix : minuscules, chiffres,
                tiret, underscore ; pas de tiret initial).
            gid: GID souhaité.

        Raises:
            ValueError: Si ``name`` ne respecte pas la convention Unix.
            CommandExecutionError: Si groupadd/groupmod retourne un code
                non nul.
        """
        _valider_nom(name)
        try:
            existing = grp.getgrnam(name)
            if existing.gr_gid != gid:
                if self._logger:
                    self._logger.log_info(
                        f"{self._prefix} Groupe '{name}' "
                        f"a le GID {existing.gr_gid} "
                        f"(attendu {gid}) — correction"
                    )
                cmd = (
                    CommandBuilder("groupmod")
                    .with_options(["--gid", str(gid)])
                    .with_args([name])
                    .build()
                )
                _run_or_raise(
                    self._executor,
                    cmd,
                    f"{self._prefix} groupmod '{name}' a échoué",
                )
            else:
                if self._logger:
                    self._logger.log_info(
                        f"{self._prefix} Groupe '{name}' "
                        f"(GID {gid}) déjà présent — skip"
                    )
        except KeyError:
            if self._logger:
                self._logger.log_info(
                    f"{self._prefix} Création du groupe '{name}' (GID {gid})"
                )
            cmd = (
                CommandBuilder("groupadd")
                .with_options(["--gid", str(gid)])
                .with_args([name])
                .build()
            )
            _run_or_raise(
                self._executor,
                cmd,
                f"{self._prefix} groupadd '{name}' a échoué",
            )
