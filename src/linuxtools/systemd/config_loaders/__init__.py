"""Chargeurs de configuration pour les unités systemd.

Ce module fournit des classes pour charger des fichiers de configuration
(TOML ou JSON) et créer les dataclasses systemd correspondantes.

Classes disponibles:
    ServiceConfigLoader: Charge un fichier vers ServiceConfig.
    TimerConfigLoader: Charge un fichier vers TimerConfig.
    MountConfigLoader: Charge un fichier vers MountConfig.
    BashScriptConfigLoader: Charge un fichier vers BashScriptConfig.

Example:
    Chargement d'une configuration de service depuis TOML:

        from linuxtools.systemd.config_loaders import (
            ServiceConfigLoader,
        )

        loader = ServiceConfigLoader("config/app.toml")
        service_config = loader.load()

    Chargement d'une configuration de timer:

        from linuxtools.systemd.config_loaders import TimerConfigLoader

        loader = TimerConfigLoader("config/app.toml")
        timer_config = loader.load_for_service("my-service")

"""

from linuxtools.systemd.config_loaders.mount_loader import (
    AutomountSettings,
    MountConfigLoader,
)
from linuxtools.systemd.config_loaders.script_loader import (
    BashScriptConfigLoader,
)
from linuxtools.systemd.config_loaders.service_loader import (
    ServiceConfigLoader,
)
from linuxtools.systemd.config_loaders.timer_loader import (
    TimerConfigLoader,
)

__all__ = [
    "ServiceConfigLoader",
    "TimerConfigLoader",
    "MountConfigLoader",
    "AutomountSettings",
    "BashScriptConfigLoader",
]
