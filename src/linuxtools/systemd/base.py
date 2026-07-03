"""Interfaces abstraites pour la gestion des unités systemd."""

import errno as _errno
import json
import os
import shlex
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from linuxtools.systemd.base_config import (
    AutomountConfig,
    BaseSystemdConfig,
    MountConfig,
    ServiceConfig,
    TimerConfig,
)
from linuxtools.systemd.validators import (
    path_to_unit_name as _path_to_unit_name,
    validate_service_name,
    validate_unit_name,
)

if TYPE_CHECKING:
    from linuxtools.logging.base import Logger
    from linuxtools.systemd.executor import (
        SystemdExecutor,
        UserSystemdExecutor,
    )

# Re-exports pour compatibilité des imports existants
__all__ = [
    "BaseSystemdConfig",
    "MountConfig",
    "AutomountConfig",
    "TimerConfig",
    "ServiceConfig",
    "_BaseUnitManagerMixin",
    "UnitManager",
    "MountUnitManager",
    "_TimerUnitContract",
    "TimerUnitManager",
    "_ServiceUnitContract",
    "ServiceUnitManager",
    "UserUnitManager",
    "UserTimerUnitManager",
    "UserServiceUnitManager",
    "_ServiceOperationsHost",
    "_ServiceOperationsMixin",
    "_TimerOperationsHost",
    "_TimerOperationsMixin",
]

# Les dataclasses (BaseSystemdConfig, MountConfig, AutomountConfig,
# TimerConfig, ServiceConfig) sont définies dans base_config.py et
# réexportées ici pour préserver la compatibilité des imports.


# =============================================================================
# Helpers d'écriture sécurisée (O_NOFOLLOW)
# =============================================================================

def _write_unit_content(
    unit_path: str,
    content: str,
    logger: "Logger",
    *,
    log_label: str = "",
) -> bool:
    """Écrit le contenu d'une unité via fd O_NOFOLLOW (TOCTOU-safe).

    Args:
        unit_path: Chemin absolu du fichier à écrire.
        content: Contenu à écrire (UTF-8).
        logger: Logger pour les messages d'erreur/info.
        log_label: Suffixe de log optionnel (ex: " utilisateur").

    Returns:
        True si succès, False sinon.
    """
    try:
        fd = os.open(
            unit_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o644,
        )
    except OSError as e:
        if e.errno == _errno.ELOOP:  # lien symbolique
            logger.log_error(
                f"Refus d'écrire {unit_path} : lien symbolique détecté"
            )
        elif isinstance(e, PermissionError):
            logger.log_error(
                f"Permission refusée pour écrire {unit_path}. "
                "Exécution en tant que root requise."
            )
        else:
            logger.log_error(
                f"Erreur lors de l'écriture de {unit_path}: {e}"
            )
        return False
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        logger.log_error(
            f"Erreur lors de l'écriture de {unit_path}: {e}"
        )
        return False
    logger.log_info(f"Fichier unit{log_label} créé: {unit_path}")
    return True


def _remove_unit_content(
    unit_path: str,
    logger: "Logger",
    *,
    log_label: str = "",
) -> bool:
    """Supprime un fichier unit (TOCTOU-safe via try/except).

    Args:
        unit_path: Chemin absolu du fichier à supprimer.
        logger: Logger pour les messages d'erreur/info.
        log_label: Suffixe optionnel dans le message de log.

    Returns:
        True si succès ou fichier inexistant, False si erreur.
    """
    try:
        os.remove(unit_path)
        logger.log_info(f"Fichier unit{log_label} supprimé: {unit_path}")
    except FileNotFoundError:
        pass
    except PermissionError:
        logger.log_error(
            f"Permission refusée pour supprimer {unit_path}. "
            "Exécution en tant que root requise."
        )
        return False
    except OSError as e:
        logger.log_error(
            f"Erreur lors de la suppression de {unit_path}: {e}"
        )
        return False
    return True


# =============================================================================
# Mixins de comportement partagé système ↔ utilisateur
# =============================================================================

class _ServiceOperationsHost(Protocol):
    """Contrat d'interface requis par _ServiceOperationsMixin.

    Déclare les attributs et méthodes que la classe hôte concrète doit
    fournir pour que _ServiceOperationsMixin puisse fonctionner.
    Utilisé uniquement pour la vérification statique (TYPE_CHECKING).
    """

    logger: "Logger"
    executor: "SystemdExecutor"

    def enable(self, unit_name: str) -> bool:
        ...

    def disable(
        self, unit_name: str, ignore_errors: bool = False
    ) -> bool:
        ...

    def get_status(self, unit_name: str) -> "str | None":
        ...

    def reload_systemd(self) -> bool:
        ...

    def _write_unit_file(
        self, unit_name: str, content: str
    ) -> bool:
        ...

    def _remove_unit_file(self, unit_name: str) -> bool:
        ...


class _ServiceOperationsMixin:
    """Mixin d'opérations service communes aux managers systemd.

    Requiert que la classe héritante fournisse :
    ``logger``, ``executor``, ``enable()``, ``disable()``,
    ``get_status()``, ``reload_systemd()``, ``_write_unit_file()``,
    ``_remove_unit_file()``.
    """

    _service_label: str = "Service"

    if TYPE_CHECKING:
        logger: "Logger"
        executor: "SystemdExecutor"

        def enable(self, unit_name: str) -> bool:
            ...

        def disable(
            self, unit_name: str, ignore_errors: bool = False
        ) -> bool:
            ...

        def get_status(
            self, unit_name: str
        ) -> "str | None":
            ...

        def reload_systemd(self) -> bool:
            ...

        def _write_unit_file(
            self, unit_name: str, content: str
        ) -> bool:
            ...

        def _remove_unit_file(self, unit_name: str) -> bool:
            ...

    @staticmethod
    def _extract_service_name_from_config(config: ServiceConfig) -> str:
        """Extrait le nom du service depuis exec_start.

        Args:
            config: Configuration du service.

        Returns:
            Nom du service dérivé du binaire exec_start.
        """
        return os.path.basename(
            shlex.split(config.exec_start)[0]
        ).replace(".", "-")

    def _validated_service_file(
        self, service_name: str
    ) -> "str | None":
        """Valide le nom de service et retourne le nom de fichier unit.

        Args:
            service_name: Nom du service (sans extension).

        Returns:
            ``"{service_name}.service"`` ou None si le nom est invalide.
        """
        try:
            validate_service_name(service_name)
        except ValueError as e:
            self.logger.log_error(
                f"Nom de service invalide : {e}"
            )
            return None
        return f"{service_name}.service"

    def install_service_unit(self, config: ServiceConfig) -> bool:
        """Installe une unité .service en dérivant le nom depuis exec_start.

        Args:
            config: Configuration du service.

        Returns:
            True si succès, False sinon.
        """
        service_name = self._extract_service_name_from_config(config)
        service_file = self._validated_service_file(service_name)
        if service_file is None:
            return False
        if not self._write_unit_file(
            service_file, config.to_unit_file()
        ):
            return False
        if not self.reload_systemd():
            return False
        self.logger.log_info(
            f"{self._service_label} {service_file} installé"
        )
        return True

    def install_service_unit_with_name(
        self, service_name: str, config: ServiceConfig
    ) -> bool:
        """Installe une unité .service avec un nom spécifique.

        Args:
            service_name: Nom du service (sans extension).
            config: Configuration du service.

        Returns:
            True si succès, False sinon.
        """
        service_file = self._validated_service_file(service_name)
        if service_file is None:
            return False
        if not self._write_unit_file(
            service_file, config.to_unit_file()
        ):
            return False
        if not self.reload_systemd():
            return False
        self.logger.log_info(
            f"{self._service_label} {service_file} installé"
        )
        return True

    def start_service(self, service_name: str) -> bool:
        """Démarre un service.

        Args:
            service_name: Nom du service (sans extension .service).

        Returns:
            True si succès, False sinon.
        """
        validate_service_name(service_name)
        return self.executor.start_unit(
            f"{service_name}.service"
        )

    def stop_service(self, service_name: str) -> bool:
        """Arrête un service.

        Args:
            service_name: Nom du service (sans extension .service).

        Returns:
            True si succès, False sinon.
        """
        validate_service_name(service_name)
        return self.executor.stop_unit(
            f"{service_name}.service"
        )

    def restart_service(self, service_name: str) -> bool:
        """Redémarre un service.

        Args:
            service_name: Nom du service (sans extension .service).

        Returns:
            True si succès, False sinon.
        """
        validate_service_name(service_name)
        return self.executor.restart_unit(
            f"{service_name}.service"
        )

    def enable_service(self, service_name: str) -> bool:
        """Active un service.

        Args:
            service_name: Nom du service (sans extension .service).

        Returns:
            True si succès, False sinon.
        """
        validate_service_name(service_name)
        return self.enable(
            f"{service_name}.service"
        )

    def disable_service(self, service_name: str) -> bool:
        """Désactive un service.

        Args:
            service_name: Nom du service (sans extension .service).

        Returns:
            True si succès, False sinon.
        """
        validate_service_name(service_name)
        return self.disable(
            f"{service_name}.service"
        )

    def remove_service_unit(self, service_name: str) -> bool:
        """Supprime un fichier .service.

        Args:
            service_name: Nom du service (sans extension).

        Returns:
            True si succès, False sinon.
        """
        validate_service_name(service_name)
        if not self.disable_service(service_name):
            self.logger.log_warning(
                f"disable_service échoué pour {service_name!r} "
                "(service peut-être déjà inactif) — "
                "suppression du fichier unit quand même"
            )
        if not self._remove_unit_file(
            f"{service_name}.service"
        ):
            return False
        self.reload_systemd()
        self.logger.log_info(
            f"{self._service_label} {service_name}.service supprimé"
        )
        return True

    def get_service_status(self, service_name: str) -> "str | None":
        """Récupère le statut d'un service.

        Args:
            service_name: Nom du service (sans extension).

        Returns:
            Statut du service ou None si erreur.
        """
        validate_service_name(service_name)
        return self.get_status(
            f"{service_name}.service"
        )

    def is_service_active(self, service_name: str) -> bool:
        """Vérifie si un service est actif.

        Args:
            service_name: Nom du service (sans extension).

        Returns:
            True si actif, False sinon.
        """
        return self.get_service_status(service_name) == "active"

    def is_service_enabled(self, service_name: str) -> bool:
        """Vérifie si un service est activé au démarrage.

        Args:
            service_name: Nom du service (sans extension).

        Returns:
            True si activé, False sinon.
        """
        validate_service_name(service_name)
        return self.executor.is_enabled(
            f"{service_name}.service"
        )


class _TimerOperationsHost(Protocol):
    """Contrat d'interface requis par _TimerOperationsMixin.

    Déclare les attributs et méthodes que la classe hôte concrète doit
    fournir pour que _TimerOperationsMixin puisse fonctionner.
    Utilisé uniquement pour la vérification statique (TYPE_CHECKING).
    """

    logger: "Logger"
    executor: "SystemdExecutor"

    def enable(self, unit_name: str) -> bool:
        ...

    def disable(
        self, unit_name: str, ignore_errors: bool = False
    ) -> bool:
        ...

    def get_status(self, unit_name: str) -> "str | None":
        ...

    def reload_systemd(self) -> bool:
        ...

    def _write_unit_file(
        self, unit_name: str, content: str
    ) -> bool:
        ...

    def _remove_unit_file(self, unit_name: str) -> bool:
        ...


class _TimerOperationsMixin:
    """Mixin des opérations timer communes aux managers système et utilisateur.

    Requiert que la classe héritante fournisse :
    ``logger``, ``executor``, ``enable()``, ``disable()``,
    ``get_status()``, ``reload_systemd()``, ``_write_unit_file()``,
    ``_remove_unit_file()``.
    """

    _timer_label: str = "Timer"

    if TYPE_CHECKING:
        logger: "Logger"
        executor: "SystemdExecutor"

        def enable(self, unit_name: str) -> bool:
            ...

        def disable(
            self, unit_name: str, ignore_errors: bool = False
        ) -> bool:
            ...

        def get_status(
            self, unit_name: str
        ) -> "str | None":
            ...

        def reload_systemd(self) -> bool:
            ...

        def _write_unit_file(
            self, unit_name: str, content: str
        ) -> bool:
            ...

        def _remove_unit_file(self, unit_name: str) -> bool:
            ...

    def install_timer_unit(self, config: TimerConfig) -> bool:
        """Installe une unité .timer.

        Args:
            config: Configuration du timer.

        Returns:
            True si succès, False sinon.
        """
        timer_file = f"{config.timer_name}.timer"
        if not self._write_unit_file(
            timer_file, config.to_unit_file()
        ):
            return False
        if not self.reload_systemd():
            return False
        self.logger.log_info(
            f"{self._timer_label} {timer_file} installé pour {config.unit}"
        )
        return True

    def enable_timer(self, timer_name: str) -> bool:
        """Active un timer.

        Args:
            timer_name: Nom du timer (sans extension .timer).

        Returns:
            True si succès, False sinon.
        """
        validate_unit_name(timer_name)
        return self.enable(
            f"{timer_name}.timer"
        )

    def disable_timer(self, timer_name: str) -> bool:
        """Désactive un timer.

        Args:
            timer_name: Nom du timer (sans extension .timer).

        Returns:
            True si succès, False sinon.
        """
        validate_unit_name(timer_name)
        return self.disable(
            f"{timer_name}.timer"
        )

    def remove_timer_unit(self, timer_name: str) -> bool:
        """Supprime un fichier .timer.

        Args:
            timer_name: Nom du timer (sans extension).

        Returns:
            True si succès, False sinon.
        """
        validate_unit_name(timer_name)
        if not self.disable_timer(timer_name):
            self.logger.log_warning(
                f"disable_timer échoué pour {timer_name!r} "
                "(unité peut-être déjà inactive) — "
                "suppression du fichier unit quand même"
            )
        if not self._remove_unit_file(
            f"{timer_name}.timer"
        ):
            return False
        self.reload_systemd()
        self.logger.log_info(
            f"{self._timer_label} {timer_name}.timer supprimé"
        )
        return True

    def get_timer_status(self, timer_name: str) -> "str | None":
        """Récupère le statut d'un timer.

        Args:
            timer_name: Nom du timer (sans extension).

        Returns:
            Statut du timer ou None si erreur.
        """
        validate_unit_name(timer_name)
        return self.get_status(
            f"{timer_name}.timer"
        )

    def list_timers(self) -> "list[dict[str, str]]":
        """Liste tous les timers actifs.

        Utilise ``--output=json`` pour un parsing fiable, avec
        fallback sur le parsing texte si le format JSON n'est pas
        supporté par la version de systemd installée.

        Returns:
            Liste de dictionnaires avec les infos des timers.

        Raises:
            RuntimeError: Si l'exécution de systemctl échoue.
        """
        try:
            result = self.executor._run_systemctl(  # type: ignore
                ["list-timers", "--no-pager", "--output=json"],
                check=False,
            )
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(
                f"Impossible d'exécuter systemctl : {e}"
            ) from e

        if result.returncode != 0:
            if "unknown option" in result.stderr.lower() \
                    or "invalid option" in result.stderr.lower():
                return self._list_timers_text_fallback()
            raise RuntimeError(
                f"Erreur systemctl list-timers : {result.stderr}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return self._list_timers_text_fallback()

        timers = []
        for entry in data:
            timers.append({
                "unit": entry.get("unit", ""),
                "activates": entry.get("activates", ""),
                "next": entry.get("next", ""),
                "left": entry.get("left", ""),
                "last": entry.get("last", ""),
                "passed": entry.get("passed", ""),
            })
        return timers

    def _list_timers_text_fallback(self) -> "list[dict[str, str]]":
        """Fallback texte pour list_timers sur vieux systemd.

        Returns:
            Liste de dictionnaires avec les infos des timers.

        Raises:
            RuntimeError: Si l'exécution de systemctl échoue.
        """
        try:
            result = self.executor._run_systemctl(  # type: ignore
                ["list-timers", "--no-pager", "--plain"],
                check=False,
            )
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(
                f"Impossible d'exécuter systemctl : {e}"
            ) from e

        if result.returncode != 0:
            raise RuntimeError(
                f"Erreur systemctl list-timers : {result.stderr}"
            )

        timers = []
        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:
            if not line.strip() or line.startswith(" "):
                continue
            parts = line.split()
            if len(parts) >= 2:
                timers.append({
                    "unit": parts[-2],
                    "activates": parts[-1],
                })
        return timers

    def is_timer_active(self, timer_name: str) -> bool:
        """Vérifie si un timer est actif.

        Args:
            timer_name: Nom du timer (sans extension).

        Returns:
            True si actif, False sinon.
        """
        return self.get_timer_status(timer_name) == "active"


# =============================================================================
# Mixin de base commun UnitManager / UserUnitManager
# =============================================================================

class _BaseUnitManagerMixin:
    """Mixin portant les méthodes communes aux managers système et utilisateur.

    Factorise __init__, reload_systemd, enable, disable, get_status et
    is_active qui sont identiques entre UnitManager et UserUnitManager.

    Attributes:
        logger: Instance de Logger pour le logging.
        executor: Instance de SystemdExecutor pour les opérations systemctl.
    """

    def __init__(
        self,
        logger: "Logger",
        executor: "SystemdExecutor",
    ) -> None:
        """Initialise le gestionnaire avec logger et executor.

        Args:
            logger: Instance de Logger pour le logging.
            executor: Instance de SystemdExecutor pour les opérations.
        """
        self.logger = logger
        self.executor = executor

    def reload_systemd(self) -> bool:
        """
        Recharge la configuration systemd (daemon-reload).

        Returns:
            True si succès, False sinon
        """
        return self.executor.reload_systemd()

    def enable(self, unit_name: str) -> bool:
        """
        Active une unité systemd.

        Args:
            unit_name: Nom de l'unité (ex: "flatpak-update.timer")

        Returns:
            True si succès, False sinon
        """
        return self.executor.enable_unit(unit_name)

    def disable(
        self, unit_name: str, ignore_errors: bool = False
    ) -> bool:
        """
        Désactive une unité systemd.

        Args:
            unit_name: Nom de l'unité (ex: "media-nas.mount")
            ignore_errors: Ignorer les erreurs (unité inexistante, etc.)

        Returns:
            True si succès, False sinon
        """
        return self.executor.disable_unit(
            unit_name, ignore_errors=ignore_errors
        )

    def get_status(self, unit_name: str) -> str | None:
        """
        Récupère le statut d'une unité.

        Args:
            unit_name: Nom de l'unité (ex: "media-nas.mount")

        Returns:
            Statut de l'unité ou None si erreur
        """
        return self.executor.get_status(unit_name)

    def is_active(self, unit_name: str) -> bool:
        """
        Vérifie si une unité est active.

        Args:
            unit_name: Nom de l'unité

        Returns:
            True si active, False sinon
        """
        return self.executor.is_active(unit_name)


# =============================================================================
# Classes abstraites — gestionnaires système
# =============================================================================

class UnitManager(_BaseUnitManagerMixin):
    """Classe de base pour tous les gestionnaires d'unités systemd.

    Fournit les opérations communes via l'injection d'un SystemdExecutor
    et les helpers d'écriture/suppression TOCTOU-safe.

    Attributes:
        logger: Instance de Logger pour le logging.
        executor: Instance de SystemdExecutor pour les opérations systemctl.
        SYSTEMD_UNIT_PATH: Chemin du répertoire des unités systemd.
    """

    SYSTEMD_UNIT_PATH: str = "/etc/systemd/system"

    def _write_unit_file(
        self, unit_name: str, content: str
    ) -> bool:
        """Écrit un fichier unit dans le répertoire systemd (O_NOFOLLOW).

        Args:
            unit_name: Nom du fichier (avec extension).
            content: Contenu du fichier.

        Returns:
            True si succès, False sinon.
        """
        unit_path = os.path.join(self.SYSTEMD_UNIT_PATH, unit_name)
        return _write_unit_content(unit_path, content, self.logger)

    def _remove_unit_file(self, unit_name: str) -> bool:
        """Supprime un fichier unit du répertoire systemd (TOCTOU-safe).

        Args:
            unit_name: Nom du fichier (avec extension).

        Returns:
            True si succès ou fichier inexistant, False si erreur.
        """
        unit_path = os.path.join(self.SYSTEMD_UNIT_PATH, unit_name)
        return _remove_unit_content(unit_path, self.logger)


class MountUnitManager(ABC, UnitManager):
    """Interface pour la gestion des unités .mount et .automount systemd."""

    @staticmethod
    def path_to_unit_name(mount_path: str) -> str:
        """Convertit un chemin de montage en nom d'unité systemd.

        Exemple: /media/nas/backup → media-nas-backup

        Args:
            mount_path: Chemin du point de montage.

        Returns:
            Nom de l'unité systemd (sans extension).
        """
        return _path_to_unit_name(mount_path)

    @abstractmethod
    def install_mount_unit(
        self,
        config: MountConfig,
        with_automount: bool = False,
        automount_timeout: int = 0
    ) -> bool:
        """
        Installe une unité .mount (et optionnellement .automount).

        Args:
            config: Configuration du montage
            with_automount: Créer aussi une unité .automount
            automount_timeout: Délai d'inactivité avant démontage (secondes)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def enable_mount(
        self, mount_path: str, with_automount: bool = False
    ) -> bool:
        """
        Active une unité .mount (ou .automount si spécifié).

        Args:
            mount_path: Chemin du point de montage
            with_automount: Activer l'unité .automount au lieu de .mount

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def disable_mount(self, mount_path: str) -> bool:
        """
        Désactive et arrête les unités .mount et .automount.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def remove_mount_unit(self, mount_path: str) -> bool:
        """
        Supprime les fichiers .mount et .automount.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def get_mount_status(self, mount_path: str) -> str | None:
        """
        Récupère le statut d'une unité .mount.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            Statut de l'unité ou None si erreur
        """
        ...

    @abstractmethod
    def is_mounted(self, mount_path: str) -> bool:
        """
        Vérifie si un point de montage est actif.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            True si monté, False sinon
        """
        ...


class _TimerUnitContract(ABC):
    """Contrat abstrait partagé par TimerUnitManager et UserTimerUnitManager.

    Élimine la duplication des 6 signatures abstraites entre les deux
    familles système et utilisateur.
    """

    @abstractmethod
    def install_timer_unit(self, config: TimerConfig) -> bool:
        """
        Installe une unité .timer.

        Args:
            config: Configuration du timer

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def enable_timer(self, timer_name: str) -> bool:
        """
        Active un timer systemd.

        Args:
            timer_name: Nom du timer (sans extension .timer)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def disable_timer(self, timer_name: str) -> bool:
        """
        Désactive un timer systemd.

        Args:
            timer_name: Nom du timer (sans extension .timer)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def remove_timer_unit(self, timer_name: str) -> bool:
        """
        Supprime un fichier .timer.

        Args:
            timer_name: Nom du timer (sans extension)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def get_timer_status(self, timer_name: str) -> str | None:
        """
        Récupère le statut d'un timer.

        Args:
            timer_name: Nom du timer (sans extension)

        Returns:
            Statut du timer ou None si erreur
        """
        ...

    @abstractmethod
    def list_timers(self) -> list[dict[str, str]]:
        """
        Liste tous les timers actifs.

        Returns:
            Liste de dictionnaires avec les infos des timers
        """
        ...


class _ServiceUnitContract(ABC):
    """Contrat abstrait partagé par ServiceUnitManager/UserServiceUnitManager.

    Élimine la duplication des 9 signatures abstraites entre les deux
    familles système et utilisateur. Inclut install_service_unit_with_name
    pour permettre l'injection d'abstractions dans
    SystemdScheduledTaskInstaller.
    """

    @abstractmethod
    def install_service_unit(self, config: ServiceConfig) -> bool:
        """
        Installe une unité .service.

        Args:
            config: Configuration du service

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def install_service_unit_with_name(
        self, service_name: str, config: ServiceConfig
    ) -> bool:
        """
        Installe une unité .service avec un nom spécifique.

        Args:
            service_name: Nom du service (sans extension)
            config: Configuration du service

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def start_service(self, service_name: str) -> bool:
        """
        Démarre un service systemd.

        Args:
            service_name: Nom du service (sans extension .service)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def stop_service(self, service_name: str) -> bool:
        """
        Arrête un service systemd.

        Args:
            service_name: Nom du service (sans extension .service)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def restart_service(self, service_name: str) -> bool:
        """
        Redémarre un service systemd.

        Args:
            service_name: Nom du service (sans extension .service)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def enable_service(self, service_name: str) -> bool:
        """
        Active un service systemd.

        Args:
            service_name: Nom du service (sans extension .service)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def disable_service(self, service_name: str) -> bool:
        """
        Désactive un service systemd.

        Args:
            service_name: Nom du service (sans extension .service)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def remove_service_unit(self, service_name: str) -> bool:
        """
        Supprime un fichier .service.

        Args:
            service_name: Nom du service (sans extension)

        Returns:
            True si succès, False sinon
        """
        ...

    @abstractmethod
    def get_service_status(self, service_name: str) -> str | None:
        """
        Récupère le statut d'un service.

        Args:
            service_name: Nom du service (sans extension)

        Returns:
            Statut du service ou None si erreur
        """
        ...


class TimerUnitManager(_TimerUnitContract, UnitManager):
    """Interface pour la gestion des unités .timer systemd."""


class ServiceUnitManager(_ServiceUnitContract, UnitManager):
    """Interface pour la gestion des unités .service systemd."""


# =============================================================================
# Classes abstraites — gestionnaires utilisateur
# =============================================================================

class UserUnitManager(_BaseUnitManagerMixin):
    """Classe de base pour les gestionnaires d'unités systemd utilisateur.

    Les unités utilisateur sont stockées dans ~/.config/systemd/user/
    et ne nécessitent pas de privilèges root.

    Attributes:
        logger: Instance de Logger pour le logging.
        executor: Instance de UserSystemdExecutor pour les opérations.
        SYSTEMD_USER_UNIT_PATH: Chemin du répertoire des unités utilisateur.
    """

    SYSTEMD_USER_UNIT_PATH: str = "~/.config/systemd/user"

    def __init__(
        self,
        logger: "Logger",
        executor: "UserSystemdExecutor"
    ) -> None:
        """
        Initialise le gestionnaire d'unités utilisateur.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de UserSystemdExecutor pour les opérations
        """
        super().__init__(logger, executor)
        self._unit_path = os.path.expanduser(self.SYSTEMD_USER_UNIT_PATH)

    @property
    def unit_path(self) -> str:
        """Retourne le chemin absolu du répertoire des unités."""
        return self._unit_path

    def _ensure_unit_directory(self) -> bool:
        """Crée le répertoire des unités utilisateur s'il n'existe pas.

        Returns:
            True si le répertoire existe ou a été créé, False sinon.
        """
        try:
            Path(self._unit_path).mkdir(parents=True, exist_ok=True)
            return True
        except OSError as e:
            self.logger.log_error(
                f"Erreur lors de la création du répertoire "
                f"{self._unit_path}: {e}"
            )
            return False

    def _write_unit_file(
        self, unit_name: str, content: str
    ) -> bool:
        """Écrit un fichier unit dans le répertoire utilisateur (O_NOFOLLOW).

        Args:
            unit_name: Nom du fichier (avec extension).
            content: Contenu du fichier.

        Returns:
            True si succès, False sinon.
        """
        if not self._ensure_unit_directory():
            return False
        unit_path = os.path.join(self._unit_path, unit_name)
        return _write_unit_content(
            unit_path, content, self.logger, log_label=" utilisateur"
        )

    def _remove_unit_file(self, unit_name: str) -> bool:
        """Supprime un fichier unit du répertoire utilisateur (TOCTOU-safe).

        Args:
            unit_name: Nom du fichier (avec extension).

        Returns:
            True si succès ou fichier inexistant, False si erreur.
        """
        unit_path = os.path.join(self._unit_path, unit_name)
        return _remove_unit_content(
            unit_path, self.logger, log_label=" utilisateur"
        )


class UserTimerUnitManager(_TimerUnitContract, UserUnitManager):
    """Interface pour la gestion des unités .timer utilisateur."""


class UserServiceUnitManager(_ServiceUnitContract, UserUnitManager):
    """Interface pour la gestion des unités .service utilisateur."""
