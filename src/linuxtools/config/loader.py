"""Fonctions de chargement de configuration."""

import json
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, TypeVar, overload

# T représente une dataclass de configuration retournée par load()
T = TypeVar("T")

# _TSchema représente le modèle Pydantic passé en `schema=` à
# ConfigLoader.load() / FileConfigLoader.load() — distinct de T
# ci-dessus (T est la dataclass renvoyée par ConfigFileLoader.load()).
# Volontairement non lié (pas de bound="BaseModel") : le contrat
# runtime (TypeError si schema n'est pas un BaseModel) est déjà
# vérifié par ConfigLoader.validate, et lier au
# typage introduirait une dépendance de typage à un extra optionnel
# pour un gain marginal — même choix que ConfigurationManager.validate
# (src/linuxtools/config/manager.py), TypeVar _T non lié.
_TSchema = TypeVar("_TSchema")


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
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


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

    @overload
    @abstractmethod
    def load(
        self,
        config_path: str | Path,
        schema: None = None,
    ) -> dict[str, Any]:
        """Charge un fichier de configuration en dict brut (sans schema)."""

    @overload
    @abstractmethod
    def load(
        self,
        config_path: str | Path,
        schema: type[_TSchema],
    ) -> _TSchema:
        """Charge un fichier de configuration et le valide via schema."""

    # ANN401 assumé : signature "réelle" recouvrant les deux overloads
    # ci-dessus — c'est elle que Python retient comme attribut de
    # classe (les deux stubs @overload sont invisibles à l'exécution,
    # réservés aux type checkers). Le retour effectif dépend de
    # `schema`, ce que les deux overloads expriment pour l'appelant ;
    # cette signature-ci reste volontairement large.
    @abstractmethod
    def load(
        self, config_path: str | Path, schema: type | None = None
    ) -> dict[str, Any] | Any:  # noqa: ANN401
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

    # ANN401 assumé : retourne une instance du modèle Pydantic fourni par
    # l'appelant. Pydantic est un extra optionnel, donc `BaseModel` ne
    # peut pas être importé au niveau module pour borner un TypeVar.
    @staticmethod
    def validate(data: dict[str, Any], schema: object) -> Any:  # noqa: ANN401
        """Valide un dict via un modèle Pydantic.

        Implémentation par défaut, partagée par tous les loaders —
        redéfinissable si un loader a besoin d'une validation
        différente. `schema` est typé `object` et non `type` :
        frontière d'exécution, l'API publique annonce `type | None`
        mais un appelant non typé peut passer n'importe quoi (une
        chaîne, une instance) et la garde ci-dessous doit rester
        vivante pour lever TypeError.

        Args:
            data: Dictionnaire brut à valider.
            schema: Classe Pydantic BaseModel attendue, non vérifiée
                par le typage statique.

        Returns:
            Instance du modèle validé.

        Raises:
            ImportError: Si pydantic n'est pas installé.
            TypeError: Si schema n'est pas un BaseModel.
        """
        try:
            from pydantic import BaseModel
        except ImportError as err:
            raise ImportError(
                "pydantic est requis pour la validation "
                "de schema. Installez-le avec: "
                "pip install linuxtools[validation]"
            ) from err

        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise TypeError(
                f"Le schema doit être une sous-classe de "
                f"pydantic.BaseModel, reçu: {schema}"
            )

        return schema.model_validate(data)


class FileConfigLoader(ConfigLoader):
    """
    Implémentation du chargeur de configuration depuis fichiers.

    Supporte les formats TOML et JSON, détectés automatiquement
    par l'extension du fichier. Supporte optionnellement la
    validation via un modèle Pydantic BaseModel.
    """

    @overload
    def load(
        self,
        config_path: str | Path,
        schema: None = None,
    ) -> dict[str, Any]:
        """Charge un fichier de configuration en dict brut (sans schema)."""

    @overload
    def load(
        self,
        config_path: str | Path,
        schema: type[_TSchema],
    ) -> _TSchema:
        """Charge un fichier de configuration et le valide via schema."""

    # ANN401 assumé : même raison que dans `ConfigLoader.load` ci-dessus
    # (le retour dépend de `schema`), signature imposée par le contrat.
    def load(
        self, config_path: str | Path, schema: type | None = None
    ) -> dict[str, Any] | Any:  # noqa: ANN401
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
                f"Extension non supportée: {suffix}. Utilisez {supported}"
            )

        raw_config = loader_fn(path)

        if schema is None:
            return raw_config

        return self.validate(raw_config, schema)


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
        config_loader: ConfigLoader | None = None,
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

    # ANN401 assumé : le retour peut être un dict (table TOML) ou une
    # liste (tableau de tables `[[section]]`), selon la structure du
    # fichier source. Les appelants vérifient eux-mêmes la forme reçue
    # (`isinstance`) avant usage — voir la docstring ci-dessous.
    def _get_raw_section(self, section: str) -> Any:  # noqa: ANN401
        """Extrait une section sans présumer de sa forme.

        `_get_section` annonce un dict, ce qui est faux pour un tableau
        de tables TOML (`[[section]]`) : celui-ci produit une liste. Les
        chargeurs qui acceptent les deux formes passent par ici et
        vérifient eux-mêmes ce qu'ils ont reçu (sinon le typage dict de
        `_get_section` fait passer leur garde `isinstance` pour du code
        inatteignable aux yeux de mypy).

        Args:
            section: Nom de la section à extraire.

        Returns:
            Contenu brut de la section (table, tableau de tables…).

        Raises:
            KeyError: Si la section n'existe pas dans le fichier.
        """
        if section not in self._config:
            available = list(self._config.keys())
            raise KeyError(
                f"Section '{section}' non trouvée dans le fichier. "
                f"Sections disponibles: {available}"
            )
        return self._config[section]

    def _get_section(self, section: str) -> dict[str, Any]:
        """Extrait une section du fichier de configuration.

        Args:
            section: Nom de la section à extraire (ex: "service", "timer").

        Returns:
            Dictionnaire contenant les données de la section.

        Raises:
            KeyError: Si la section n'existe pas dans le fichier.
        """
        result: dict[str, Any] = self._get_raw_section(section)
        return result

    # ANN401 assumé : navigation dynamique dans l'arborescence de
    # configuration. Le type dépend des clés passées à l'exécution, comme
    # pour `ConfigManager.get` — voir `linuxtools/config/base.py`.
    def _get_nested_value(
        self,
        *keys: str,
        default: Any = None,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Extrait une valeur imbriquée du fichier de configuration.

        Args:
            *keys: Clés successives pour naviguer dans la structure.
            default: Valeur par défaut si le chemin n'existe pas.

        Returns:
            Valeur trouvée ou default si non trouvée.

        Example:
            >>> loader._get_nested_value("paths", "log_file")
        """
        # `current` change de nature à chaque itération : il part d'un
        # dict puis prend la valeur de la clé, qui peut être un scalaire.
        # Sans l'annotation `Any`, mypy le croit dict pour toujours et
        # juge la garde `isinstance` inférieure morte (redundant-expr) —
        # alors qu'elle empêche `key not in current` de dégénérer en
        # recherche de sous-chaîne sur une str.
        current: Any = self._config
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
