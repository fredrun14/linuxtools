"""Installation d'un couple service+timer systemd sur la cible."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from linuxtools.deploy.models import PhaseOutcome
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.systemd.executor import SystemdExecutor, UserSystemdExecutor
from linuxtools.systemd.service import LinuxServiceUnitManager
from linuxtools.systemd.service_timer_installer import (
    SystemdServiceTimerInstaller,
)
from linuxtools.systemd.timer import LinuxTimerUnitManager
from linuxtools.systemd.user_service import LinuxUserServiceUnitManager
from linuxtools.systemd.user_timer import LinuxUserTimerUnitManager

if TYPE_CHECKING:
    from linuxtools.commands.base import CommandExecutor
    from linuxtools.deploy.models import DeployTarget, TimerDeploySpec
    from linuxtools.logging.base import Logger

# Nom d'utilisateur POSIX, relu sur la cible avant d'être réinjecté
_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*\$?$")


class TimerDeployer:
    """Installe un couple service+timer systemd sur la cible.

    Attributes:
        _logger: Logger optionnel.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise le déployeur de timer.

        Args:
            logger: Logger optionnel.
        """
        self._logger = logger

    def deploy(
        self,
        spec: TimerDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> PhaseOutcome:
        """Installe et active le service+timer de `spec` sur la cible.

        Le scope (`spec.scope`) détermine le chemin d'installation :
        "system" (défaut, /etc/systemd/system/, nécessite root) ou
        "user" (`$XDG_CONFIG_HOME/systemd/user/`, `~/.config/systemd/user/`
        par défaut, systemctl --user, sans élévation de privilèges).

        Args:
            spec: Spécification de l'unité (nom, ServiceConfig,
                TimerConfig, scope).
            target: Cible du déploiement (détermine local vs
                distant).
            executor: Exécuteur de commandes ciblant `target`.

        En scope "user", l'état du linger est signalé dans les messages
        de l'issue (lecture seule : `enable-linger` n'est jamais lancé).

        Returns:
            `PhaseOutcome(True, messages)` si l'installation et
            l'activation ont réussi, `PhaseOutcome(False)` sinon.
        """
        logger = self._logger or ConsoleLogger()
        if spec.scope == "user":
            if not self._deploy_user(spec, target, executor, logger):
                return PhaseOutcome(False)
            return PhaseOutcome(True, (self._probe_linger(executor, logger),))
        return PhaseOutcome(
            self._deploy_system(spec, target, executor, logger)
        )

    def _probe_linger(self, executor: CommandExecutor, logger: Logger) -> str:
        """Lit l'état du linger de l'utilisateur de la cible (lecture seule).

        Ne provoque jamais d'échec de phase et n'exécute jamais
        `enable-linger`. Le nom d'utilisateur lu sur la cible est validé
        (`_USER_RE`) avant d'être passé à `loginctl`.

        Args:
            executor: Exécuteur de commandes ciblant l'hôte.
            logger: Logger déjà résolu.

        Returns:
            Le message de rapport sur l'état du linger.
        """
        who = executor.run(["id", "-un"])
        user = who.stdout.strip() if who.success else ""
        if not _USER_RE.fullmatch(user):
            return "Linger indéterminé (utilisateur introuvable)."
        result = executor.run(
            ["loginctl", "show-user", user, "-p", "Linger", "--value"]
        )
        state = result.stdout.strip() if result.success else ""
        if state == "yes":
            return f"Linger actif pour {user}."
        if state == "no":
            message = (
                f"Linger inactif pour {user} : le timer ne tournera pas "
                f"hors session. À lancer : sudo loginctl enable-linger "
                f"{user}"
            )
            logger.log_warning(message)
            return message
        return f"Linger indéterminé pour {user}."

    def _deploy_system(
        self,
        spec: TimerDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
        logger: Logger,
    ) -> bool:
        """Installe le service+timer en mode système (comportement
        historique, inchangé).

        Args:
            spec: Spécification de l'unité.
            target: Cible du déploiement.
            executor: Exécuteur de commandes ciblant `target`.
            logger: Logger déjà résolu (jamais None ici).

        Returns:
            True si l'installation et l'activation ont réussi.
        """
        systemd_executor = SystemdExecutor(logger, executor)
        service_manager = LinuxServiceUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )
        timer_manager = LinuxTimerUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )
        installer = SystemdServiceTimerInstaller(
            logger, service_manager, timer_manager
        )
        return installer.install(
            spec.unit_name, spec.service_config, spec.timer_config
        )

    def _deploy_user(
        self,
        spec: TimerDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
        logger: Logger,
    ) -> bool:
        """Installe le service+timer en mode utilisateur (systemctl
        --user), sans élévation de privilèges.

        N'utilise volontairement pas `SystemdServiceTimerInstaller`
        (typé pour les ABCs système, incompatible mypy --strict avec
        les managers utilisateur) : orchestre directement les 3 appels
        dans le même ordre que `ServiceTimerInstaller.install()`
        (service -> timer -> enable).

        Args:
            spec: Spécification de l'unité.
            target: Cible du déploiement.
            executor: Exécuteur de commandes ciblant `target`.
            logger: Logger déjà résolu (jamais None ici).

        Returns:
            True si toutes les étapes ont réussi, False sinon.
        """
        systemd_executor = UserSystemdExecutor(logger, executor)
        service_manager = LinuxUserServiceUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )
        timer_manager = LinuxUserTimerUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )

        if not service_manager.install_service_unit_with_name(
            spec.unit_name, spec.service_config
        ):
            logger.log_error(
                f"Échec de l'installation du service utilisateur "
                f"{spec.unit_name}.service"
            )
            return False

        if not timer_manager.install_timer_unit(spec.timer_config):
            logger.log_error(
                f"Échec de l'installation du timer utilisateur "
                f"{spec.unit_name}.timer"
            )
            return False

        if not timer_manager.enable_timer(spec.unit_name):
            logger.log_error(
                f"Échec de l'activation du timer utilisateur "
                f"{spec.unit_name}.timer"
            )
            return False

        logger.log_info(
            f"Unités utilisateur {spec.unit_name}.service/.timer "
            "installées avec succès."
        )
        return True
