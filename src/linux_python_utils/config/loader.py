"""Fonctions de chargement de configuration."""

import json
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

# T représente une dataclass de configuration retournée par load()
T = TypeVar("T")


def _load_toml(path: Path) -> dict[str, Any]:
    """Charge un fichier TOML et retourne son contenu.

    Args:
        path: Chemin vers le fichier TOML.

    Returns:
        Dictionnaire de configuration.
    """
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_json(path: Path) -> dict[str, Any]:
    """Charge un fichier JSON et retourne son contenu.

    Args:
        path: Chemin vers le fichier JSON.

    Returns:
        Dictionnaire de configuration.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_LOADERS: dict[str, Callable[[Path], dict[str, Any]]] = {
    ".toml": _load_toml,
    ".json": _load_json,
}


class ConfigLoader(ABC):
    """
    Interface abstraite pour le chargement de configuration.

    Permet l'injection de dépendance et facilite les tests
    en permettant de substituer l'implémentation réelle par un mock.
    """

    @abstractmethod
    def load(
        self,
        config_path: str | Path,
        schema: type | None = None
    ) -> dict[str, Any] | Any:
        """Charge un fichier de configuration.

        Args:
            config_path: Chemin vers le fichier de configuration.
            schema: Classe Pydantic BaseModel optionnelle pour
                validation. Si fourni, retourne une instance
                du modèle. Si None, retourne un dict brut.

        Returns:
            Dictionnaire de configuration ou instance du schema.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si le format n'est pas supporté.
            ImportError: Si schema fourni mais pydantic absent.
            TypeError: Si schema n'est pas un BaseModel.
        """
        ...  # pragma: no cover


class FileConfigLoader(ConfigLoader):
    """
    Implémentation du chargeur de configuration depuis fichiers.

    Supporte les formats TOML et JSON, détectés automatiquement
    par l'extension du fichier. Supporte optionnellement la
    validation via un modèle Pydantic BaseModel.
    """

    def load(
        self,
        config_path: str | Path,
        schema: type | None = None
    ) -> dict[str, Any] | Any:
        """Charge un fichier de configuration TOML ou JSON.

        Le format est détecté automatiquement par l'extension
        du fichier. Si un schema Pydantic est fourni, le dict
        brut est validé et une instance du modèle est retournée.

        Args:
            config_path: Chemin vers le fichier de configuration.
            schema: Classe Pydantic BaseModel optionnelle.

        Returns:
            Dictionnaire de configuration ou instance du schema.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError: Si l'extension n'est pas supportée.
            ImportError: Si schema fourni mais pydantic absent.
            TypeError: Si schema n'est pas un BaseModel.
        """
        path = Path(config_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Fichier de configuration non trouvé: {path}"
            )

        suffix = path.suffix.lower()
        loader_fn = _LOADERS.get(suffix)

        if loader_fn is None:
            supported = ", ".join(_LOADERS)
            raise ValueError(
                f"Extension non supportée: {suffix}. "
                f"Utilisez {supported}"
            )

        raw_config = loader_fn(path)

        if schema is None:
            return raw_config

        return self._validate_with_schema(raw_config, schema)

    @staticmethod
    def _validate_with_schema(
        data: dict[str, Any], schema: type
    ) -> Any:
        """Valide un dict via un modèle Pydantic.

        Args:
            data: Dictionnaire brut à valider.
            schema: Classe Pydantic BaseModel.

        Returns:
            Instance du modèle validé.

        Raises:
            ImportError: Si pydantic n'est pas installé.
            TypeError: Si schema n'est pas un BaseModel.
        """
        try:
            from pydantic import BaseModel
        except ImportError:
            raise ImportError(
                "pydantic est requis pour la validation "
                "de schema. Installez-le avec: "
                "pip install linux-python-utils[validation]"
            )

        if not (
            isinstance(schema, type)
            and issubclass(schema, BaseModel)
        ):
            raise TypeError(
                f"Le schema doit être une sous-classe de "
                f"pydantic.BaseModel, reçu: {schema}"
            )

        return schema.model_validate(data)


class ConfigFileLoader(ABC, Generic[T]):
    """Classe de base abstraite pour les chargeurs de configuration typés.

    Cette classe fournit l'infrastructure commune pour charger un fichier
    de configuration (TOML ou JSON) et extraire une section spécifique
    pour créer une dataclass.

    Le format est automatiquement détecté par l'extension du fichier:
    - .toml : Format TOML
    - .json : Format JSON

    Attributes:
        _config: Dictionnaire de configuration chargé depuis le fichier.

    Example:
        >>> class ServiceLoader(ConfigFileLoader[ServiceConfig]):
        ...     def load(self, section: str = "service") -> ServiceConfig:
        ...         data = self._get_section(section)
        ...         return ServiceConfig(**data)
    """

    def __init__(
        self,
        config_path: str | Path,
        config_loader: ConfigLoader | None = None
    ) -> None:
        """Initialise le loader en chargeant le fichier de configuration.

        Args:
            config_path: Chemin vers le fichier de configuration
                (.toml ou .json).
            config_loader: Chargeur de configuration injectable
                (DIP). Si None, utilise FileConfigLoader par défaut.

        Raises:
            FileNotFoundError: Si le fichier de configuration n'existe pas.
            ValueError: Si l'extension du fichier n'est pas supportée.
            tomllib.TOMLDecodeError: Si le TOML est invalide.
            json.JSONDecodeError: Si le JSON est invalide.
        """
        loader = config_loader or FileConfigLoader()
        self._config: dict[str, Any] = loader.load(config_path)

    @property
    def config(self) -> dict[str, Any]:
        """Retourne le dictionnaire de configuration brut.

        Returns:
            Dictionnaire complet de la configuration.
        """
        return self._config

    def _get_section(self, section: str) -> dict[str, Any]:
        """Extrait une section du fichier de configuration.

        Args:
            section: Nom de la section à extraire (ex: "service", "timer").

        Returns:
            Dictionnaire contenant les données de la section.

        Raises:
            KeyError: Si la section n'existe pas dans le fichier.
        """
        if section not in self._config:
            available = list(self._config.keys())
            raise KeyError(
                f"Section '{section}' non trouvée dans le fichier. "
                f"Sections disponibles: {available}"
            )
        result: dict[str, Any] = self._config[section]
        return result

    def _get_nested_value(
        self,
        *keys: str,
        default: Any = None
    ) -> Any:
        """Extrait une valeur imbriquée du fichier de configuration.

        Args:
            *keys: Clés successives pour naviguer dans la structure.
            default: Valeur par défaut si le chemin n'existe pas.

        Returns:
            Valeur trouvée ou default si non trouvée.

        Example:
            >>> loader._get_nested_value("paths", "log_file")
        """
        current = self._config
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    @abstractmethod
    def load(self, section: str | None = None) -> T:
        """Charge et retourne la dataclass de configuration.

        Args:
            section: Nom de la section à charger. Si None, utilise
                la section par défaut du loader.

        Returns:
            Instance de la dataclass de configuration.

        Raises:
            KeyError: Si la section requise n'existe pas.
            TypeError: Si les données ne correspondent pas à la dataclass.
        """
        ...  # pragma: no cover
