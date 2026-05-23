"""Modèles de données pour les spécifications de configuration TOML."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConfigBlock:
    """Représente un bloc de configuration issu d'une spec TOML.

    Attributes:
        content: Ligne(s) de configuration active(s).
        comment: Ligne de commentaire précédant le bloc.
        section: Nom de la section INI cible. None pour fichiers plats.
    """

    content: str
    comment: str = ""
    section: str | None = None


@dataclass
class ConfigSpec:
    """Spécification complète d'une application de configuration.

    Attributes:
        file_path: Chemin absolu résolu du fichier cible.
        blocks: Liste ordonnée des blocs à appliquer.
    """

    file_path: Path
    blocks: list[ConfigBlock] = field(default_factory=list)
