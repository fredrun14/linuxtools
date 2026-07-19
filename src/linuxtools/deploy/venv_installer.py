"""(Ré)installation dans un venv cible et gestion backup/rollback.

Toutes les commandes de ce module passent par l'exécuteur *cible*
injecté (LinuxCommandExecutor pour une cible locale, ou
SshCommandExecutor pour une cible distante) — VenvInstaller ne sait
jamais s'il opère en local ou à distance.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.exceptions import DeployError
from linuxtools.logging.base import Logger


class VenvInstaller:
    """(Ré)installe dans un venv et gère backup/rollback.

    Attributes:
        _executor: Exécuteur ciblant l'hôte (local ou
            SshCommandExecutor).
        _logger: Logger optionnel.
    """

    _PIP_TIMEOUT = 300

    def __init__(
        self,
        executor: CommandExecutor,
        logger: Logger | None = None,
    ) -> None:
        """Initialise l'installateur avec son exécuteur cible.

        Args:
            executor: Exécuteur de commandes ciblant l'hôte.
            logger: Logger optionnel.
        """
        self._executor = executor
        self._logger = logger

    def _log(self, message: str) -> None:
        """Envoie un message d'information au logger si disponible."""
        if self._logger:
            self._logger.log_info(message)

    def _log_error(self, message: str) -> None:
        """Envoie un message d'erreur au logger si disponible."""
        if self._logger:
            self._logger.log_error(message)

    def backup_venv(self, venv_path: Path) -> Path | None:
        """Sauvegarde le venv existant avant réinstallation.

        Args:
            venv_path: Chemin du venv à sauvegarder.

        Returns:
            Chemin du backup créé, ou None si le venv n'existait
            pas encore (rien à sauver — première installation).

        Raises:
            DeployError: Si le venv existe mais que la copie de
                sauvegarde échoue. On n'installe jamais sans filet.
        """
        exists = self._executor.run(
            ["test", "-d", str(venv_path)]
        )
        if not exists.success:
            self._log(
                f"Aucun venv existant à {venv_path} : "
                "pas de backup nécessaire."
            )
            return None

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = venv_path.parent / (
            f"{venv_path.name}.bak-{timestamp}"
        )

        result = self._executor.run(
            ["cp", "-a", str(venv_path), str(backup_path)]
        )
        if not result.success:
            self._log_error(
                f"Échec du backup de {venv_path} vers "
                f"{backup_path} : {result.stderr}"
            )
            raise DeployError(
                f"Backup du venv {venv_path} impossible : "
                f"{result.stderr}"
            )

        self._log(f"Venv sauvegardé : {venv_path} -> {backup_path}")
        return backup_path

    def install(
        self,
        venv_path: Path,
        source_dir: Path,
        recreate: bool = False,
    ) -> CommandResult:
        """(Ré)installe le source dans le venv cible.

        Utilise toujours `<venv>/bin/pip` (jamais `python3 -m pip`
        système) pour éviter l'erreur PEP 668
        `externally-managed-environment` (Fedora 41+).

        Args:
            venv_path: Chemin du venv cible.
            source_dir: Répertoire source à installer (déjà
                transporté sur l'hôte).
            recreate: Si True, recrée le venv avant d'installer
                (F-14, Could).

        Returns:
            CommandResult de la commande pip install. Si recreate
            échoue avant l'appel pip, retourne le CommandResult de
            l'étape en échec.
        """
        if recreate:
            version_result = self._executor.run(
                ["python3", "--version"]
            )
            version = (
                version_result.stdout.strip()
                or version_result.stderr.strip()
            )
            self._log(f"python3 de l'hôte : {version}")

            rm_result = self._executor.run(
                ["rm", "-rf", str(venv_path)]
            )
            if not rm_result.success:
                self._log_error(
                    f"Échec de suppression du venv {venv_path} : "
                    f"{rm_result.stderr}"
                )
                return rm_result

            venv_result = self._executor.run(
                ["python3", "-m", "venv", str(venv_path)]
            )
            if not venv_result.success:
                self._log_error(
                    f"Échec de création du venv {venv_path} : "
                    f"{venv_result.stderr}"
                )
                return venv_result

        pip = str(venv_path / "bin" / "pip")
        result = self._executor.run(
            [pip, "install", "--force-reinstall", str(source_dir)],
            timeout=self._PIP_TIMEOUT,
        )
        if result.success:
            self._log(f"Installation réussie dans {venv_path}.")
        else:
            self._log_error(
                f"Échec de l'installation dans {venv_path} : "
                f"{result.stderr}"
            )
        return result

    def restore_venv(
        self, venv_path: Path, backup_path: Path
    ) -> bool:
        """Restaure le venv depuis une sauvegarde (rollback).

        Ne détruit jamais le venv en place avant d'avoir confirmé la
        restauration : s'il existe, il est d'abord *renommé* en
        garde-fou (`<venv>.rollback-tmp-<horodatage>`), puis le
        backup est *copié* (jamais déplacé — le backup original
        reste disponible pour un nouvel essai) vers venv_path. Si la
        copie échoue, le garde-fou est remis en place : le venv
        n'est jamais laissé dans un état « supprimé sans
        remplaçant ».

        Args:
            venv_path: Chemin du venv à restaurer.
            backup_path: Chemin du backup à réinjecter.

        Returns:
            True si la restauration a réussi, False sinon.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        guard_path = venv_path.parent / (
            f"{venv_path.name}.rollback-tmp-{timestamp}"
        )

        exists = self._executor.run(
            ["test", "-d", str(venv_path)]
        )
        if exists.success:
            mv_result = self._executor.run(
                ["mv", str(venv_path), str(guard_path)]
            )
            if not mv_result.success:
                self._log_error(
                    f"Échec de la mise à l'écart de {venv_path} "
                    f"pendant le rollback : {mv_result.stderr}"
                )
                return False

        cp_result = self._executor.run(
            ["cp", "-a", str(backup_path), str(venv_path)]
        )
        if not cp_result.success:
            self._log_error(
                f"Échec de restauration du backup {backup_path} "
                f"vers {venv_path} : {cp_result.stderr}"
            )
            if exists.success:
                restore_result = self._executor.run(
                    ["mv", str(guard_path), str(venv_path)]
                )
                if not restore_result.success:
                    self._log_error(
                        "Échec de la remise en place du "
                        f"garde-fou {guard_path} : "
                        f"{restore_result.stderr}"
                    )
            return False

        if exists.success:
            self._executor.run(["rm", "-rf", str(guard_path)])

        self._log(f"Venv restauré depuis {backup_path}.")
        return True

    def prune_backup(self, backup_path: Path) -> None:
        """Supprime un backup devenu inutile (best-effort).

        Args:
            backup_path: Chemin du backup à supprimer.
        """
        result = self._executor.run(
            ["rm", "-rf", str(backup_path)]
        )
        if not result.success:
            self._log_error(
                f"Échec de suppression du backup {backup_path} "
                f"(non bloquant) : {result.stderr}"
            )
