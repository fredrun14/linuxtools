"""Exécuteur de commandes systemctl."""

import subprocess  # nosec B404
from typing import ClassVar

from linuxtools.logging.base import Logger
from linuxtools.systemd.validators import validate_full_unit_name


class SystemdExecutor:
    """Exécuteur de commandes systemctl.

    Encapsule toutes les opérations bas niveau systemctl
    (daemon-reload, enable, disable, start, stop, status).

    Attributes:
        logger: Instance de Logger pour le logging.
    """

    _label: ClassVar[str] = ""

    def __init__(self, logger: Logger) -> None:
        """
        Initialise l'exécuteur systemd.

        Args:
            logger: Instance de Logger pour le logging
        """
        self.logger = logger

    def _run_systemctl(
        self,
        args: list[str],
        check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """
        Exécute une commande systemctl.

        Args:
            args: Arguments de la commande systemctl
            check: Lever une exception si la commande échoue

        Returns:
            Résultat de la commande
        """
        cmd = ["systemctl"] + args
        return subprocess.run(  # nosec B603
            cmd, check=check, capture_output=True, text=True
        )

    def reload_systemd(self) -> bool:
        """
        Recharge la configuration systemd (daemon-reload).

        Returns:
            True si succès, False sinon
        """
        try:
            self._run_systemctl(["daemon-reload"])
            self.logger.log_info(
                f"Systemd{self._label} rechargé avec succès."
            )
            return True
        except subprocess.CalledProcessError as e:
            self.logger.log_error(
                f"Erreur lors du rechargement de systemd{self._label}: {e}"
            )
            return False

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
        try:
            args = ["enable"]
            if now:
                args.append("--now")
            args.append(unit_name)
            self._run_systemctl(args)
            msg = f"Unité {unit_name} activée"
            if now:
                msg += " et démarrée"
            self.logger.log_info(f"{msg} avec succès.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.log_error(
                f"Erreur lors de l'activation de l'unité {unit_name}: {e}"
            )
            return False

    def disable_unit(
        self,
        unit_name: str,
        now: bool = True,
        ignore_errors: bool = False
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
        try:
            args = ["disable"]
            if now:
                args.append("--now")
            args.append(unit_name)
            self._run_systemctl(args, check=not ignore_errors)
            self.logger.log_info(
                f"Unité {unit_name} désactivée et arrêtée."
            )
            return True
        except subprocess.CalledProcessError as e:
            if ignore_errors:
                self.logger.log_warning(
                    f"Impossible de désactiver {unit_name}: {e}"
                )
                return True
            self.logger.log_error(
                f"Erreur lors de la désactivation de {unit_name}: {e}"
            )
            return False

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
        try:
            self._run_systemctl([verb, unit_name])
            self.logger.log_info(msg_ok)
            return True
        except subprocess.CalledProcessError as e:
            self.logger.log_error(f"{msg_err}: {e}")
            return False

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
            "start", unit_name,
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
            "stop", unit_name,
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
            "restart", unit_name,
            f"Unité {unit_name} redémarrée.",
            f"Erreur lors du redémarrage de {unit_name}",
        )

    def get_status(self, unit_name: str) -> str | None:
        """
        Récupère le statut d'une unité systemd.

        Args:
            unit_name: Nom de l'unité

        Returns:
            Statut de l'unité (active, inactive, failed, etc.) ou None
        """
        validate_full_unit_name(unit_name)
        try:
            result = self._run_systemctl(
                ["is-active", unit_name],
                check=False
            )
            return result.stdout.strip()
        except (subprocess.SubprocessError, OSError) as e:
            self.logger.log_error(
                f"Erreur lors de la récupération du statut "
                f"de {unit_name}: {e}"
            )
            return None

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
            True si activée, False sinon
        """
        validate_full_unit_name(unit_name)
        try:
            result = self._run_systemctl(
                ["is-enabled", unit_name],
                check=False
            )
            return result.stdout.strip() == "enabled"
        except (subprocess.SubprocessError, OSError) as e:
            self.logger.log_error(
                f"Erreur lors de la vérification de {unit_name}: {e}"
            )
            return False

    def is_masked(self, unit_name: str) -> bool:
        """Vérifie si une unité systemd est masquée.

        Args:
            unit_name: Nom complet de l'unité
                (ex: ``packagekit.service``).

        Returns:
            True si masquée, False sinon.
        """
        validate_full_unit_name(unit_name)
        try:
            result = self._run_systemctl(
                ["is-enabled", unit_name],
                check=False
            )
            return result.stdout.strip() == "masked"
        except (subprocess.SubprocessError, OSError) as e:
            self.logger.log_error(
                f"Erreur lors de la vérification de {unit_name}: {e}"
            )
            return False

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
            "mask", unit_name,
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
            "unmask", unit_name,
            f"Unité {unit_name} démasquée.",
            f"Erreur lors du démasquage de {unit_name}",
        )


class UserSystemdExecutor(SystemdExecutor):
    """Exécuteur de commandes systemctl --user.

    Encapsule toutes les opérations bas niveau systemctl pour les
    unités utilisateur (daemon-reload, enable, disable, start, stop, status).

    Les unités utilisateur ne nécessitent pas de privilèges root et sont
    stockées dans ~/.config/systemd/user/.

    Attributes:
        logger: Instance de Logger pour le logging.
    """

    _label = " utilisateur"

    def _run_systemctl(
        self,
        args: list[str],
        check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """
        Exécute une commande systemctl --user.

        Args:
            args: Arguments de la commande systemctl
            check: Lever une exception si la commande échoue

        Returns:
            Résultat de la commande
        """
        cmd = ["systemctl", "--user"] + args
        return subprocess.run(  # nosec B603
            cmd, check=check, capture_output=True, text=True
        )
