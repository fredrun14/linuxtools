"""Module de gestion des unités systemd.

Ce module fournit des classes pour gérer les unités systemd :

Exécuteurs systemctl:
- SystemdExecutor: Exécuteur de commandes systemctl (mode système)
- UserSystemdExecutor: Exécuteur de commandes systemctl --user

Unités système (root, /etc/systemd/system):
- LinuxMountUnitManager: Gestion des unités .mount et .automount
- LinuxTimerUnitManager: Gestion des unités .timer
- LinuxServiceUnitManager: Gestion des unités .service

Unités utilisateur (sans root, ~/.config/systemd/user):
- LinuxUserTimerUnitManager: Gestion des unités .timer utilisateur
- LinuxUserServiceUnitManager: Gestion des unités .service utilisateur

Orchestration:
- SystemdScheduledTaskInstaller: Installation complète script + service + timer

Export / restauration portables:
- SystemdUnitExporter: Exporte un fichier unit existant vers TOML (verbatim)
- SystemdUnitRestorer: Restaure un fichier unit depuis TOML

Chargeurs de configuration (TOML/JSON → dataclass):
- ServiceConfigLoader, TimerConfigLoader, MountConfigLoader
- BashScriptConfigLoader

Exemple d'utilisation (système):
    from linuxtools import FileLogger
    from linuxtools.systemd import (
        SystemdExecutor,
        LinuxMountUnitManager,
        MountConfig,
    )

    logger = FileLogger("/var/log/app.log")
    executor = SystemdExecutor(logger)
    mount_manager = LinuxMountUnitManager(logger, executor)

    config = MountConfig(
        description="Partage NAS",
        what="192.168.1.10:/share",
        where="/media/nas",
        type="nfs",
        options="rw,soft",
    )
    mount_manager.install_mount_unit(config, with_automount=True)

Exemple d'utilisation (utilisateur):
    from linuxtools import FileLogger
    from linuxtools.systemd import (
        UserSystemdExecutor,
        LinuxUserTimerUnitManager,
        TimerConfig,
    )

    logger = FileLogger("~/.local/log/app.log")
    executor = UserSystemdExecutor(logger)
    timer_manager = LinuxUserTimerUnitManager(logger, executor)

    config = TimerConfig(
        description="Backup quotidien",
        unit="backup.service",
        on_calendar="daily",
        persistent=True,
    )
    timer_manager.install_timer_unit(config)
"""

# Classes abstraites et configurations
from linuxtools.systemd.base import (
    # Système
    UnitManager,
    MountUnitManager,
    TimerUnitManager,
    ServiceUnitManager,
    # Utilisateur
    UserUnitManager,
    UserTimerUnitManager,
    UserServiceUnitManager,
    # Configurations
    MountConfig,
    AutomountConfig,
    TimerConfig,
    ServiceConfig,
)

# Exécuteurs systemctl
from linuxtools.systemd.executor import (
    SystemdExecutor,
    UserSystemdExecutor,
)

# Implémentations Linux système
from linuxtools.systemd.mount import LinuxMountUnitManager
from linuxtools.systemd.timer import LinuxTimerUnitManager
from linuxtools.systemd.service import LinuxServiceUnitManager

# Implémentations Linux utilisateur
from linuxtools.systemd.user_timer import LinuxUserTimerUnitManager
from linuxtools.systemd.user_service import LinuxUserServiceUnitManager

# Installateur de tâches planifiées
from linuxtools.systemd.scheduled_task import (
    ScheduledTaskInstaller,
    SystemdScheduledTaskInstaller,
)

# Chargeurs de configuration TOML
from linuxtools.systemd.config_loaders import (
    ServiceConfigLoader,
    TimerConfigLoader,
    MountConfigLoader,
    BashScriptConfigLoader,
)

# Export / restauration génériques (préservation verbatim des sections INI)
from linuxtools.systemd.unit_porter import (
    SystemdUnitExporter,
    SystemdUnitRestorer,
)

# Rétrocompatibilité avec l'ancienne API
# (LinuxSystemdServiceManager est remplacé par SystemdExecutor)
LinuxSystemdServiceManager = SystemdExecutor

__all__ = [
    # Classes abstraites système
    "UnitManager",
    "MountUnitManager",
    "TimerUnitManager",
    "ServiceUnitManager",
    # Classes abstraites utilisateur
    "UserUnitManager",
    "UserTimerUnitManager",
    "UserServiceUnitManager",
    # Configurations
    "MountConfig",
    "AutomountConfig",
    "TimerConfig",
    "ServiceConfig",
    # Exécuteurs
    "SystemdExecutor",
    "UserSystemdExecutor",
    # Implémentations système
    "LinuxMountUnitManager",
    "LinuxTimerUnitManager",
    "LinuxServiceUnitManager",
    # Implémentations utilisateur
    "LinuxUserTimerUnitManager",
    "LinuxUserServiceUnitManager",
    # Installateur de tâches planifiées
    "ScheduledTaskInstaller",
    "SystemdScheduledTaskInstaller",
    # Chargeurs de configuration
    "ServiceConfigLoader",
    "TimerConfigLoader",
    "MountConfigLoader",
    "BashScriptConfigLoader",
    # Rétrocompatibilité
    "LinuxSystemdServiceManager",
    # Export / restauration génériques
    "SystemdUnitExporter",
    "SystemdUnitRestorer",
]
