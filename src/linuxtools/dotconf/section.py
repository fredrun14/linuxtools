"""Implémentation de sections INI avec validation externe.

Ce module fournit ValidatedSection, une dataclass de base pour représenter
des sections de fichiers INI avec validation des valeurs depuis une source
externe (fichier TOML, dictionnaire, etc.).
"""

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any, ClassVar

from linuxtools.dotconf.base import IniSection


def parse_validator(
    value: Any,
) -> list[str]:
    """Convertit une valeur de validateur en liste de valeurs autorisées.

    Args:
        value: Liste de valeurs autorisées (ex: ["yes", "no"]).

    Returns:
        Liste de valeurs autorisées.

    Raises:
        ValueError: Si le format du validateur est invalide.
    """
    if isinstance(value, list):
        return value
    raise ValueError(f"Format de validateur invalide : {value!r}")


def build_validators(
    validators_dict: dict[str, Any],
) -> dict[str, list[str] | Callable[[str], bool]]:
    """Construit un dictionnaire de validateurs depuis une configuration.

    Args:
        validators_dict: Dictionnaire brut des validateurs (depuis TOML).

    Returns:
        Dictionnaire des validateurs prêts à l'emploi.
    """
    return {
        key: parse_validator(value) for key, value in validators_dict.items()
    }


@dataclass(frozen=True)
class ValidatedSection(IniSection):
    """Classe de base pour une section INI avec validation externe.

    Cette dataclass immuable permet de représenter une section de fichier INI
    tout en validant les valeurs selon des règles définies externellement
    (fichier TOML, dictionnaire Python, etc.).

    Les validators sont injectés via la méthode de classe `set_validators()`
    avant la création des instances.

    Attributes:
        _validators: Dictionnaire de classe contenant les règles de validation.
            Clé : nom du champ
            Valeur : liste de valeurs autorisées OU fonction de validation.

    Example:
        >>> # Définir une section concrète
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
        >>> # Créer une instance (validation automatique)
        >>> section = CommandsSection(upgrade_type="security")
    """

    _validators: ClassVar[dict[str, list[str] | Callable[[str], bool]]] = {}

    @classmethod
    def set_validators(
        cls,
        validators: dict[str, list[str] | Callable[[str], bool]],
    ) -> None:
        """Injecte les validateurs depuis une source externe.

        Cette méthode doit être appelée avant de créer des instances
        pour activer la validation.

        Les listes de valeurs autorisées peuvent être passées via
        ``build_validators()`` (depuis TOML). Les fonctions callable
        doivent être passées directement en Python.

        Args:
            validators: Dictionnaire des règles de validation.
                Valeur : liste de valeurs autorisées OU callable.

        Example:
            >>> MySection.set_validators({
            ...     "field1": ["opt1", "opt2"],
            ...     "field2": lambda x: x.isdigit(),
            ... })
        """
        processed: dict[str, list[str] | Callable[[str], bool]] = {}
        for key, value in validators.items():
            if callable(value):
                processed[key] = value
            else:
                processed[key] = parse_validator(value)
        cls._validators = processed

    @classmethod
    def clear_validators(cls) -> None:
        """Efface les validateurs (utile pour les tests)."""
        cls._validators = {}

    def __post_init__(self) -> None:
        """Valide tous les champs selon les validateurs injectés.

        Appelé automatiquement après l'initialisation de la dataclass.

        Raises:
            ValueError: Si une valeur ne passe pas la validation.
        """
        for f in fields(self):
            if f.name.startswith("_"):
                continue

            value = getattr(self, f.name)
            validator = self._validators.get(f.name)

            if validator is None:
                continue

            if isinstance(validator, list):
                if value not in validator:
                    raise ValueError(
                        f"{f.name}={value!r} invalide. "
                        f"Valeurs autorisées : {validator}"
                    )
            elif not validator(value):
                raise ValueError(f"{f.name}={value!r} échoue la validation.")

    @staticmethod
    def section_name() -> str:
        """Retourne le nom de la section.

        Doit être redéfini dans les classes dérivées.

        Returns:
            Nom de la section.

        Raises:
            NotImplementedError: Si non redéfini.
        """
        raise NotImplementedError("section_name() doit être redéfini")

    def to_dict(self) -> dict[str, str]:
        """Convertit la section en dictionnaire clé-valeur.

        Exclut les champs privés (commençant par '_').

        Returns:
            Dictionnaire des paires clé=valeur.
        """
        return {
            f.name: str(getattr(self, f.name))
            for f in fields(self)
            if not f.name.startswith("_")
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "ValidatedSection":
        """Crée une instance depuis un dictionnaire.

        Args:
            data: Dictionnaire des paires clé=valeur.

        Returns:
            Instance de la section avec validation.

        Raises:
            TypeError: Si des champs requis sont manquants.
            ValueError: Si la validation échoue.
        """
        return cls(**data)
