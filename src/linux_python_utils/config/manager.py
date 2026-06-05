"""Gestionnaire de configuration avancé."""

import json
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from linux_python_utils.config.base import ConfigManager
from linux_python_utils.config.loader import ConfigLoader, FileConfigLoader
from linux_python_utils.logging.base import Logger


class ConfigurationManager(ConfigManager):
    """
    Gestionnaire de configuration avec fonctionnalités avancées.

    Fonctionnalités:
    - Support TOML et JSON
    - Recherche automatique dans plusieurs emplacements
    - Fusion profonde avec configuration par défaut
    - Accès par chemin pointé (ex: "backup.rsync.options")
    - Gestion de profils

    Respecte le principe DIP en acceptant un ConfigLoader
    en injection de dépendance, facilitant les tests unitaires.
    """

    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        default_config: Optional[Dict[str, Any]] = None,
        search_paths: Optional[List[Union[str, Path]]] = None,
        config_loader: Optional[ConfigLoader] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """
        Initialise le gestionnaire de configuration.

        Args:
            config_path: Chemin vers le fichier de configuration
            default_config: Configuration par défaut (fusion avec fichier)
            search_paths: Liste de chemins de recherche du fichier
            config_loader: Instance de ConfigLoader (optionnel).
                Si non fourni, utilise FileConfigLoader par défaut.
            logger: Logger optionnel pour tracer les erreurs de
                chargement. Si None, les erreurs sont silencieuses.
        """
        self.default_config = default_config or {}
        self.search_paths = search_paths or []
        self._loader = config_loader or FileConfigLoader()
        self._logger = logger

        if config_path is None and self.search_paths:
            config_path = self._find_config_file()

        if config_path:
            self.config_path = Path(config_path).expanduser()
        else:
            self.config_path = None

        self.config = self._load_config()

    def _log_warning(self, message: str) -> None:
        """Logue un avertissement si un logger est configuré.

        Args:
            message: Message à logguer.
        """
        if self._logger:
            self._logger.log_warning(message)

    def _log_info(self, message: str) -> None:
        """Logue un message informatif si un logger est configuré.

        Args:
            message: Message à logguer.
        """
        if self._logger:
            self._logger.log_info(message)

    def _find_config_file(self) -> Optional[Path]:
        """Cherche le fichier de config dans les emplacements définis."""
        for path in self.search_paths:
            path = Path(path).expanduser()
            if path.exists():
                return path
        return None

    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier via le loader injecté."""
        if self.config_path and self.config_path.exists():
            try:
                user_config = self._loader.load(self.config_path)
                # Fusionner avec la config par défaut
                base = self.default_config.copy()
                return self._deep_merge(base, user_config)
            except (
                OSError,
                tomllib.TOMLDecodeError,
                json.JSONDecodeError,
                ValueError,
            ) as e:
                self._log_warning(
                    f"Config illisible ({self.config_path}) : {e}"
                    " — utilisation de la configuration par défaut."
                )
                return self.default_config.copy()
        else:
            if self.config_path:
                self._log_warning(
                    f"Fichier de configuration non trouvé : "
                    f"{self.config_path} — "
                    "utilisation de la configuration par défaut."
                )
            return self.default_config.copy()

    def _deep_merge(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fusionne récursivement deux dictionnaires."""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Récupère une valeur par chemin pointé.

        Args:
            key_path: Chemin vers la clé (ex: "backup.rsync.options")
            default: Valeur par défaut si la clé n'existe pas

        Returns:
            La valeur trouvée ou la valeur par défaut
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Récupère une section complète de la configuration.

        Args:
            section: Nom de la section

        Returns:
            Dictionnaire de la section ou dict vide
        """
        return self.config.get(section, {})

    def get_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Récupère un profil de la configuration.

        Args:
            profile_name: Nom du profil

        Returns:
            Dictionnaire du profil avec chemins expandés

        Raises:
            ValueError: Si le profil n'existe pas
        """
        profiles = self.get('profiles', {})

        if profile_name not in profiles:
            available = list(profiles.keys())
            if available:
                profiles_list = ", ".join(f"'{p}'" for p in available)
                raise ValueError(
                    f"Profil '{profile_name}' non trouvé. "
                    f"Disponibles: {profiles_list}"
                )
            else:
                raise ValueError(
                    f"Profil '{profile_name}' non trouvé. "
                    "Aucun profil défini."
                )

        profile = profiles[profile_name].copy()

        # Expander les chemins
        for key in ['source', 'destination', 'path']:
            if key in profile:
                profile[key] = str(Path(profile[key]).expanduser())

        return profile

    def list_profiles(self) -> List[str]:
        """Liste tous les profils disponibles."""
        return list(self.get('profiles', {}).keys())

    def create_default_config(
        self,
        output_path: Optional[Path] = None
    ) -> None:
        """
        Crée un fichier de configuration par défaut.

        Args:
            output_path: Chemin de sortie (utilise config_path si non spécifié)
        """
        path = output_path or self.config_path
        if not path:
            raise ValueError("Aucun chemin de configuration spécifié")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        suffix = path.suffix.lower()
        if suffix == ".json":
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.default_config, f, indent=2, ensure_ascii=False)
        elif suffix == ".toml":
            # tomllib ne supporte pas l'écriture, on utilise un format simple
            self._write_toml(path, self.default_config)
        else:
            raise ValueError(f"Extension non supportée: {suffix}")

        self._log_info(f"Configuration créée : {path}")

    def _write_toml(
        self,
        path: Path,
        data: Dict[str, Any],
    ) -> None:
        """Écrit un dict en TOML valide via ConfTomlExporter."""
        from linux_python_utils.dotconf.conf_toml_exporter import (
            ConfTomlExporter,
        )
        content = ConfTomlExporter().export_mapping(data)
        path.write_text(content + "\n", encoding="utf-8")
