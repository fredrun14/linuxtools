"""Module DotConf pour la gestion de fichiers de configuration INI.

Ce module fournit des outils pour représenter et manipuler des fichiers
de configuration au format INI (.conf) avec :
- Validation externe des valeurs (depuis TOML, dictionnaire, etc.)
- Dataclasses immuables pour la représentation des sections
- Gestion robuste des opérations lecture/écriture
- Édition ligne-à-ligne préservant commentaires et formatage
- Application déclarative de blocs de configuration via spec TOML

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

Fonctions utilitaires:
    - parse_validator: Convertit un validateur brut en fonction/liste
    - build_validators: Construit un dictionnaire de validateurs

Example:
    >>> from dataclasses import dataclass
    >>> from linux_python_utils.dotconf import (
    ...     ValidatedSection, LinuxIniConfigManager
    ... )
    >>> from linux_python_utils import FileLogger
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

from linux_python_utils.dotconf.applier import ConfigApplier
from linux_python_utils.dotconf.base import (
    IniConfig,
    IniConfigManager,
    IniSection,
)
from linux_python_utils.dotconf.line_editor import SectionAwareEditor
from linux_python_utils.dotconf.manager import LinuxIniConfigManager
from linux_python_utils.dotconf.section import (
    ValidatedSection,
    build_validators,
    parse_validator,
)
from linux_python_utils.dotconf.spec import ConfigBlock, ConfigSpec
from linux_python_utils.dotconf.toml_spec_loader import TomlSpecLoader

__all__ = [
    # Interfaces abstraites
    "IniSection",
    "IniConfig",
    "IniConfigManager",
    # Implémentations
    "ValidatedSection",
    "LinuxIniConfigManager",
    "SectionAwareEditor",
    # Spec TOML + applier
    "ConfigBlock",
    "ConfigSpec",
    "TomlSpecLoader",
    "ConfigApplier",
    # Fonctions utilitaires
    "parse_validator",
    "build_validators",
]
