"""Gestionnaire de fichiers de configuration INI.

Ce module fournit LinuxIniConfigManager, une implémentation robuste
pour la lecture, l'écriture et la mise à jour de fichiers INI.
"""

import configparser
import os
from io import StringIO
from pathlib import Path
from typing import Any

from linuxtools.dotconf.base import (
    IniConfig,
    IniConfigManager,
    IniSection,
)
from linuxtools.logging.base import Logger


class LinuxIniConfigManager(IniConfigManager):
    """Gestionnaire de fichiers de configuration INI pour Linux.

    Utilise configparser pour les opérations de lecture/écriture
    avec support de logging et validation optionnelle.

    Attributes:
        _logger: Instance de Logger pour tracer les opérations.

    Example:
        >>> from linuxtools import FileLogger
        >>> logger = FileLogger("/var/log/config.log")
        >>> manager = LinuxIniConfigManager(logger)
        >>> config = manager.read(Path("/etc/dnf/dnf.conf"))
        >>> print(config["main"]["fastestmirror"])
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise le gestionnaire avec un logger optionnel.

        Args:
            logger: Instance de Logger pour les messages (optionnel).
        """
        self._logger = logger

    @staticmethod
    def _load_parser(path: Path) -> configparser.ConfigParser:
        """Crée un ConfigParser et charge le fichier si existant."""
        parser = configparser.ConfigParser()
        if path.exists():
            parser.read(path, encoding="utf-8")
        return parser

    @staticmethod
    def _save_parser(
        parser: configparser.ConfigParser, path: Path
    ) -> None:
        """Écrit le parser dans path et applique chmod 0o644."""
        with open(path, "w", encoding="utf-8") as f:
            parser.write(f)
        os.chmod(path, 0o644)

    def read(self, path: Path) -> dict[str, dict[str, str]]:
        """Lit un fichier INI et retourne son contenu.

        Args:
            path: Chemin du fichier INI.

        Returns:
            Dictionnaire imbriqué {section: {clé: valeur}}.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
        """
        if not path.exists():
            raise FileNotFoundError(f"Fichier non trouvé : {path}")

        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")

        result: dict[str, dict[str, str]] = {}
        for section in parser.sections():
            result[section] = dict(parser[section])

        if self._logger:
            self._logger.log_info(f"Fichier {path} lu avec succès.")
        return result

    def write(self, path: Path, config: IniConfig) -> None:
        """Écrit une configuration dans un fichier INI.

        Args:
            path: Chemin du fichier de destination.
            config: Configuration à écrire.
        """
        parser = configparser.ConfigParser()
        for section in config.sections():
            parser[section.section_name()] = section.to_dict()
        self._save_parser(parser, path)
        if self._logger:
            self._logger.log_info(f"Fichier {path} écrit avec succès.")

    def write_section(self, path: Path, section: IniSection) -> None:
        """Écrit ou met à jour une section dans un fichier INI.

        Si le fichier existe, la section est mise à jour.
        Sinon, un nouveau fichier est créé.

        Args:
            path: Chemin du fichier INI.
            section: Section à écrire.
        """
        parser = self._load_parser(path)
        parser[section.section_name()] = section.to_dict()
        self._save_parser(parser, path)
        if self._logger:
            self._logger.log_info(
                f"Section [{section.section_name()}] écrite dans {path}."
            )

    def update_section(
        self,
        path: Path,
        section: IniSection,
        validators: dict[str, Any] | None = None,
    ) -> bool:
        """Met à jour une section dans un fichier INI existant.

        Compare les valeurs actuelles avec les nouvelles et n'écrit
        que si des modifications sont nécessaires.

        Args:
            path: Chemin du fichier INI.
            section: Section avec les nouvelles valeurs.
            validators: Validateurs optionnels (ignorés car la validation
                       est faite dans ValidatedSection).

        Returns:
            True si des modifications ont été effectuées, False sinon.
        """
        parser = self._load_parser(path)
        section_name = section.section_name()
        new_values = section.to_dict()

        if section_name not in parser:
            parser[section_name] = {}

        updated = False
        for key, new_value in new_values.items():
            current_value = parser[section_name].get(key)
            if current_value != new_value:
                parser[section_name][key] = new_value
                updated = True
                if self._logger:
                    self._logger.log_info(
                        f"Modification : {key} mis à jour"
                    )

        if updated:
            self._save_parser(parser, path)
            if self._logger:
                self._logger.log_info(f"Fichier {path} mis à jour.")
        else:
            if self._logger:
                self._logger.log_info(
                    f"Fichier {path} déjà configuré avec les valeurs cibles."
                )

        return updated

    def is_section_configured(
        self,
        path: Path,
        section: IniSection,
    ) -> bool:
        """Vérifie si une section est configurée avec les valeurs attendues.

        Compare uniquement les clés définies dans section.to_dict() avec
        les valeurs présentes dans le fichier. Les clés supplémentaires
        du fichier sont ignorées.

        Args:
            path: Chemin du fichier INI à vérifier.
            section: Section contenant les valeurs cibles.

        Returns:
            True si toutes les clés de la section ont déjà les valeurs
            attendues, False si le fichier est absent, si la section
            manque, ou si au moins une valeur diffère.
        """
        if not path.exists():
            return False

        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")

        section_name = section.section_name()
        if not parser.has_section(section_name):
            return False

        current = dict(parser[section_name])
        expected = section.to_dict()
        return all(
            current.get(key) == value for key, value in expected.items()
        )

    @staticmethod
    def _parser_to_string(parser: configparser.ConfigParser) -> str:
        """Sérialise un ConfigParser en chaîne INI."""
        output = StringIO()
        parser.write(output)
        return output.getvalue()

    def section_to_ini(self, section: IniSection) -> str:
        """Génère le contenu INI d'une section.

        Args:
            section: Section à convertir.

        Returns:
            Contenu INI formaté de la section.
        """
        parser = configparser.ConfigParser()
        parser[section.section_name()] = section.to_dict()
        return self._parser_to_string(parser)

    def config_to_ini(self, config: IniConfig) -> str:
        """Génère le contenu INI d'une configuration complète.

        Args:
            config: Configuration à convertir.

        Returns:
            Contenu INI formaté complet.
        """
        parser = configparser.ConfigParser()
        for section in config.sections():
            parser[section.section_name()] = section.to_dict()
        return self._parser_to_string(parser)
