"""Module de configuration typée et XDG.

Fournit deux familles de chargeurs de configuration : un accès générique
par chemin pointé (ConfigManager / ConfigurationManager) et un chargement
typé de section TOML/JSON vers dataclass (ConfigLoader / ConfigFileLoader).
Complété par XdgAppConfig pour résoudre le répertoire de configuration
XDG (``~/.config/<app_name>/``) d'une application.

Accès par chemin pointé:
- ConfigManager: Interface abstraite (get, get_section par chemin pointé)
- ConfigurationManager: Implémentation TOML/JSON avec cache

Chargement typé (fichier → dataclass):
- ConfigLoader: Interface abstraite (load(path, section, schema))
- FileConfigLoader: Implémentation TOML/JSON de ConfigLoader
- ConfigFileLoader: Classe de base à sous-classer pour un chargeur dédié
  à une dataclass de configuration (un par type de config)

Répertoire XDG:
- XdgAppConfig: Résout ``~/.config/<app_name>/`` et initialise un fichier

Exemple d'utilisation (accès par chemin pointé):
    from pathlib import Path
    from linuxtools.config import ConfigurationManager

    manager = ConfigurationManager(Path("/etc/mon-outil/config.toml"))
    options = manager.get("backup.rsync.options", default="-az")

Exemple d'utilisation (chargeur typé):
    from dataclasses import dataclass
    from linuxtools.config import ConfigFileLoader

    @dataclass(frozen=True)
    class ServiceConfig:
        name: str

    class ServiceLoader(ConfigFileLoader[ServiceConfig]):
        def load(self, section: str = "service") -> ServiceConfig:
            return ServiceConfig(**self._get_section(section))

Exemple d'utilisation (répertoire XDG):
    from linuxtools.config import XdgAppConfig

    cfg = XdgAppConfig("mon-outil")
    cfg.init_config_file("[log]\\nlevel = 'INFO'\\n")
"""

from linuxtools.config.base import ConfigManager
from linuxtools.config.loader import (
    ConfigFileLoader,
    ConfigLoader,
    FileConfigLoader,
)
from linuxtools.config.manager import ConfigurationManager
from linuxtools.config.xdg import XdgAppConfig

__all__ = [
    "ConfigFileLoader",
    "ConfigLoader",
    "ConfigManager",
    "ConfigurationManager",
    "FileConfigLoader",
    "XdgAppConfig",
]
