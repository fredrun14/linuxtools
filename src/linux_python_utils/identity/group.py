"""Gestion idempotente des groupes Unix."""

import grp

from linux_python_utils.commands import CommandBuilder, LinuxCommandExecutor
from linux_python_utils.identity.base import GroupManagerBase, _valider_nom
from linux_python_utils.logging import Logger


class LinuxGroupManager(GroupManagerBase):
    """Crée ou corrige les groupes Unix via groupadd / groupmod."""

    def __init__(
        self,
        executor: LinuxCommandExecutor,
        logger: Logger,
    ) -> None:
        """Initialise le gestionnaire avec ses dépendances.

        Args:
            executor: Exécuteur de commandes Linux.
            logger: Logger pour les messages d'information.
        """
        self._executor = executor
        self._logger = logger
        self._prefix = "[LinuxGroupManager]"

    def ensure_group(self, name: str, gid: int) -> None:
        """Crée ou corrige le groupe Unix avec le GID donné.

        Args:
            name: Nom du groupe (convention Unix : minuscules, chiffres,
                tiret, underscore ; pas de tiret initial).
            gid: GID souhaité.

        Raises:
            ValueError: Si ``name`` ne respecte pas la convention Unix.
        """
        _valider_nom(name)
        try:
            existing = grp.getgrnam(name)
            if existing.gr_gid != gid:
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
                self._executor.run(cmd)
            else:
                self._logger.log_info(
                    f"{self._prefix} Groupe '{name}' "
                    f"(GID {gid}) déjà présent — skip"
                )
        except KeyError:
            self._logger.log_info(
                f"{self._prefix} Création du groupe '{name}' (GID {gid})"
            )
            cmd = (
                CommandBuilder("groupadd")
                .with_options(["--gid", str(gid)])
                .with_args([name])
                .build()
            )
            self._executor.run(cmd)
