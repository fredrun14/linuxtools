"""Exécuteur de commandes systemctl."""

import json
from typing import ClassVar

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.logging.base import Logger
from linuxtools.systemd.validators import validate_full_unit_name


class SystemdExecutor:
    """Exécuteur de commandes systemctl.

    Délègue l'exécution réelle à un CommandExecutor injecté — local
    par défaut (comportement identique aux versions précédentes), ou
    SshCommandExecutor pour cibler un hôte distant (cf.
    linuxtools.deploy).

    Attributes:
        logger: Instance de Logger pour le logging.
    """

    _label: ClassVar[str] = ""

    def __init__(
        self,
        logger: Logger,
        executor: CommandExecutor | None = None,
    ) -> None:
        """Initialise l'exécuteur systemd.

        Args:
            logger: Instance de Logger pour le logging.
            executor: Exécuteur de commandes ciblant l'hôte (local ou
                SSH). Si None, un LinuxCommandExecutor local est créé
                — comportement identique aux versions précédentes de
                cette classe.
        """
        self.logger = logger
        self._executor = executor or LinuxCommandExecutor(logger=logger)

    def _run_systemctl(self, args: list[str]) -> CommandResult:
        """Exécute une commande systemctl via l'executor injecté.

        Args:
            args: Arguments de la commande systemctl.

        Returns:
            CommandResult de l'exécution (jamais d'exception levée
            sur un code de retour non nul — à l'appelant de vérifier
            `.success`).
        """
        return self._executor.run(["systemctl", *args])

    def run_raw(
        self, command: list[str], stdin: str | None = None
    ) -> CommandResult:
        """Exécute une commande arbitraire via l'executor injecté.

        Passe-plat utilisé par UnitManager (systemd/base.py) pour
        écrire un fichier d'unité sur une cible distante via
        `stdin=` — la cible locale garde son écriture TOCTOU-safe
        directe et n'appelle jamais cette méthode.

        Args:
            command: Commande à exécuter.
            stdin: Contenu à envoyer sur l'entrée standard, ou None.

        Returns:
            CommandResult de l'exécution.
        """
        return self._executor.run(command, stdin=stdin)

    def reload_systemd(self) -> bool:
        """
        Recharge la configuration systemd (daemon-reload).

        Returns:
            True si succès, False sinon
        """
        result = self._run_systemctl(["daemon-reload"])
        if not result.success:
            self.logger.log_error(
                f"Erreur lors du rechargement de systemd{self._label}: "
                f"{result.stderr}"
            )
            return False
        self.logger.log_info(f"Systemd{self._label} rechargé avec succès.")
        return True

    def enable_unit(self, unit_name: str, now: bool = True) -> bool:
        """
        Active une unité systemd.

        Args:
            unit_name: Nom de l'unité (ex: "media-nas.mount")
            now: Démarrer immédiatement l'unité

        Returns:
            True si succès, False sinon
        """
        validate_full_unit_name(unit_name)
        args = ["enable"]
        if now:
            args.append("--now")
        args.append(unit_name)
        result = self._run_systemctl(args)
        if not result.success:
            self.logger.log_error(
                f"Erreur lors de l'activation de l'unité {unit_name}: "
                f"{result.stderr}"
            )
            return False
        msg = f"Unité {unit_name} activée"
        if now:
            msg += " et démarrée"
        self.logger.log_info(f"{msg} avec succès.")
        return True

    def disable_unit(
        self,
        unit_name: str,
        now: bool = True,
        ignore_errors: bool = False,
    ) -> bool:
        """
        Désactive une unité systemd.

        Args:
            unit_name: Nom de l'unité
            now: Arrêter immédiatement l'unité
            ignore_errors: Ignorer les erreurs (unité inexistante, etc.)

        Returns:
            True si succès, False sinon
        """
        validate_full_unit_name(unit_name)
        args = ["disable"]
        if now:
            args.append("--now")
        args.append(unit_name)
        result = self._run_systemctl(args)
        if not result.success:
            if ignore_errors:
                self.logger.log_warning(
                    f"Impossible de désactiver {unit_name}: {result.stderr}"
                )
                return True
            self.logger.log_error(
                f"Erreur lors de la désactivation de {unit_name}: "
                f"{result.stderr}"
            )
            return False
        self.logger.log_info(f"Unité {unit_name} désactivée et arrêtée.")
        return True

    def _simple_action(
        self,
        verb: str,
        unit_name: str,
        msg_ok: str,
        msg_err: str,
    ) -> bool:
        """Exécute une action systemctl simple (start/stop/restart).

        Args:
            verb: Commande systemctl (start, stop, restart…).
            unit_name: Nom de l'unité (déjà validé par l'appelant).
            msg_ok: Message de log en cas de succès.
            msg_err: Préfixe du message de log en cas d'échec.

        Returns:
            True si succès, False sinon.
        """
        result = self._run_systemctl([verb, unit_name])
        if not result.success:
            self.logger.log_error(f"{msg_err}: {result.stderr}")
            return False
        self.logger.log_info(msg_ok)
        return True

    def start_unit(self, unit_name: str) -> bool:
        """
        Démarre une unité systemd.

        Args:
            unit_name: Nom de l'unité

        Returns:
            True si succès, False sinon
        """
        validate_full_unit_name(unit_name)
        return self._simple_action(
            "start",
            unit_name,
            f"Unité {unit_name} démarrée.",
            f"Erreur lors du démarrage de {unit_name}",
        )

    def stop_unit(self, unit_name: str) -> bool:
        """
        Arrête une unité systemd.

        Args:
            unit_name: Nom de l'unité

        Returns:
            True si succès, False sinon
        """
        validate_full_unit_name(unit_name)
        return self._simple_action(
            "stop",
            unit_name,
            f"Unité {unit_name} arrêtée.",
            f"Erreur lors de l'arrêt de {unit_name}",
        )

    def restart_unit(self, unit_name: str) -> bool:
        """
        Redémarre une unité systemd.

        Args:
            unit_name: Nom de l'unité

        Returns:
            True si succès, False sinon
        """
        validate_full_unit_name(unit_name)
        return self._simple_action(
            "restart",
            unit_name,
            f"Unité {unit_name} redémarrée.",
            f"Erreur lors du redémarrage de {unit_name}",
        )

    def get_status(self, unit_name: str) -> str:
        """
        Récupère le statut d'une unité systemd.

        Args:
            unit_name: Nom de l'unité

        Returns:
            Statut de l'unité (active, inactive, failed, etc.), ou
            chaîne vide si la commande échoue (CommandExecutor.run()
            ne lève jamais — une erreur système est déjà convertie en
            CommandResult avec un stdout vide).
        """
        validate_full_unit_name(unit_name)
        result = self._run_systemctl(["is-active", unit_name])
        return result.stdout.strip()

    def is_active(self, unit_name: str) -> bool:
        """
        Vérifie si une unité systemd est active.

        Args:
            unit_name: Nom de l'unité

        Returns:
            True si active, False sinon
        """
        return self.get_status(unit_name) == "active"

    def is_enabled(self, unit_name: str) -> bool:
        """
        Vérifie si une unité systemd est activée au démarrage.

        Args:
            unit_name: Nom de l'unité

        Returns:
            True si activée, False sinon (y compris si la commande
            échoue).
        """
        validate_full_unit_name(unit_name)
        result = self._run_systemctl(["is-enabled", unit_name])
        return result.stdout.strip() == "enabled"

    def is_masked(self, unit_name: str) -> bool:
        """Vérifie si une unité systemd est masquée.

        Args:
            unit_name: Nom complet de l'unité
                (ex: ``packagekit.service``).

        Returns:
            True si masquée, False sinon (y compris si la commande
            échoue).
        """
        validate_full_unit_name(unit_name)
        result = self._run_systemctl(["is-enabled", unit_name])
        return result.stdout.strip() == "masked"

    def list_units(self) -> list[dict[str, str]]:
        """Liste toutes les unités systemd connues.

        Utilise ``--output=json`` pour un parsing fiable, avec
        fallback sur le parsing texte si le format JSON n'est pas
        supporté par la version de systemd installée — même
        stratégie que ``list_timers()`` côté managers de timer.

        Returns:
            Liste de dictionnaires (``unit``, ``load``, ``active``,
            ``sub``, ``description``) — pass-through direct du
            schéma de ``systemctl list-units --output=json``.

        Raises:
            RuntimeError: Si l'exécution de systemctl échoue pour
                une raison autre que l'absence de support JSON.
        """
        result = self._run_systemctl(
            ["list-units", "--no-pager", "--output=json"]
        )

        if result.return_code != 0:
            if (
                "unknown option" in result.stderr.lower()
                or "invalid option" in result.stderr.lower()
            ):
                return self._list_units_text_fallback()
            raise RuntimeError(
                f"Erreur systemctl list-units : {result.stderr}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return self._list_units_text_fallback()

        units = []
        for entry in data:
            units.append(
                {
                    "unit": entry.get("unit", ""),
                    "load": entry.get("load", ""),
                    "active": entry.get("active", ""),
                    "sub": entry.get("sub", ""),
                    "description": entry.get("description", ""),
                }
            )
        return units

    def _list_units_text_fallback(self) -> list[dict[str, str]]:
        """Fallback texte pour list_units sur vieux systemd.

        Returns:
            Liste de dictionnaires (mêmes clés que list_units()).

        Raises:
            RuntimeError: Si l'exécution de systemctl échoue.
        """
        result = self._run_systemctl(
            ["list-units", "--no-pager", "--no-legend", "--plain"]
        )

        if result.return_code != 0:
            raise RuntimeError(
                f"Erreur systemctl list-units : {result.stderr}"
            )

        units = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(maxsplit=4)
            if len(parts) < 4:
                continue
            units.append(
                {
                    "unit": parts[0],
                    "load": parts[1],
                    "active": parts[2],
                    "sub": parts[3],
                    "description": parts[4] if len(parts) > 4 else "",
                }
            )
        return units

    def mask_unit(self, unit_name: str) -> bool:
        """Masque une unité systemd.

        Args:
            unit_name: Nom complet de l'unité
                (ex: ``packagekit.service``).

        Returns:
            True si succès, False sinon.
        """
        validate_full_unit_name(unit_name)
        return self._simple_action(
            "mask",
            unit_name,
            f"Unité {unit_name} masquée.",
            f"Erreur lors du masquage de {unit_name}",
        )

    def unmask_unit(self, unit_name: str) -> bool:
        """Démasque une unité systemd.

        Args:
            unit_name: Nom complet de l'unité
                (ex: ``packagekit.service``).

        Returns:
            True si succès, False sinon.
        """
        validate_full_unit_name(unit_name)
        return self._simple_action(
            "unmask",
            unit_name,
            f"Unité {unit_name} démasquée.",
            f"Erreur lors du démasquage de {unit_name}",
        )


class UserSystemdExecutor(SystemdExecutor):
    """Exécuteur de commandes systemctl --user.

    Encapsule toutes les opérations bas niveau systemctl pour les
    unités utilisateur (daemon-reload, enable, disable, start, stop,
    status).

    Les unités utilisateur ne nécessitent pas de privilèges root et
    sont stockées dans ~/.config/systemd/user/.

    Attributes:
        logger: Instance de Logger pour le logging.
    """

    _label = " utilisateur"

    def _run_systemctl(self, args: list[str]) -> CommandResult:
        """
        Exécute une commande systemctl --user via l'executor injecté.

        Args:
            args: Arguments de la commande systemctl.

        Returns:
            CommandResult de l'exécution.
        """
        return self._executor.run(["systemctl", "--user", *args])
