"""Module DotConf pour la gestion de fichiers de configuration INI.

Ce module fournit des outils pour représenter et manipuler des fichiers
de configuration au format INI (.conf) avec :
- Validation externe des valeurs (depuis TOML, dictionnaire, etc.)
- Dataclasses immuables pour la représentation des sections
- Gestion robuste des opérations lecture/écriture
- Édition ligne-à-ligne préservant commentaires et formatage
- Application déclarative de blocs de configuration via spec TOML
- Export d'un fichier conf existant vers un TOML TomlSpecLoader

Classes principales:
    - IniSection: Interface abstraite pour une section INI
    - IniConfig: Interface abstraite pour un fichier INI complet
    - IniConfigManager: Interface abstraite pour la gestion de fichiers
    - ValidatedSection: Dataclass de base avec validation externe
    - LinuxIniConfigManager: Implémentation du gestionnaire de fichiers
    - SectionAwareEditor: Éditeur ligne-à-ligne préservant les commentaires
    - ConfigBlock: Bloc de configuration issu d'une spec TOML
    - ConfigSpec: Spécification complète (chemin cible + blocs)
    - TomlSpecLoader: Charge un TOML de spec → ConfigSpec
    - ConfigApplier: Applique un ConfigSpec sur un fichier cible
    - ConfTomlExporter: Exporte un fichier conf existant vers un TOML

Fonctions utilitaires:
    - parse_validator: Convertit un validateur brut en fonction/liste
    - build_validators: Construit un dictionnaire de validateurs

Example:
    >>> from dataclasses import dataclass
    >>> from linuxtools.dotconf import (
    ...     ValidatedSection, LinuxIniConfigManager
    ... )
    >>> from linuxtools import FileLogger
    >>>
    >>> @dataclass(frozen=True)
    ... class CommandsSection(ValidatedSection):
    ...     upgrade_type: str = "default"
    ...     download_updates: str = "yes"
    ...
    ...     @staticmethod
    ...     def section_name() -> str:
    ...         return "commands"
    >>>
    >>> # Injecter les validators depuis le TOML
    >>> CommandsSection.set_validators({
    ...     "upgrade_type": ["default", "security"],
    ...     "download_updates": ["yes", "no"],
    ... })
    >>>
    >>> # Créer une section validée
    >>> section = CommandsSection(
    ...     upgrade_type="security", download_updates="yes"
    ... )
    >>>
    >>> # Écrire dans un fichier
    >>> logger = FileLogger("/var/log/test.log")
    >>> manager = LinuxIniConfigManager(logger)
    >>> manager.write_section(Path("/etc/test.conf"), section)
"""

from linuxtools.dotconf.applier import ConfigApplier
from linuxtools.dotconf.base import (
    IniConfig,
    IniConfigManager,
    IniSection,
)
from linuxtools.dotconf.conf_toml_exporter import ConfTomlExporter
from linuxtools.dotconf.line_editor import SectionAwareEditor
from linuxtools.dotconf.manager import LinuxIniConfigManager
from linuxtools.dotconf.section import (
    ValidatedSection,
    build_validators,
    parse_validator,
)
from linuxtools.dotconf.spec import ConfigBlock, ConfigSpec
from linuxtools.dotconf.toml_spec_loader import TomlSpecLoader

__all__ = [
    "ConfigApplier",
    "ConfigBlock",
    "ConfigSpec",
    "ConfTomlExporter",
    "IniConfig",
    "IniConfigManager",
    "IniSection",
    "LinuxIniConfigManager",
    "SectionAwareEditor",
    "TomlSpecLoader",
    "ValidatedSection",
    "build_validators",
    "parse_validator",
]
