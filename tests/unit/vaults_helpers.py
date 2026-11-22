"""Aides de test du module ``linuxtools.vaults`` (noms de vault neutres)."""

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

Settings = dict[str, dict[str, object]]

DEFAULT_SETTINGS: Settings = {
    "sources": {
        "emplacements": "~/sources/emplacements.md",
        "conventions": "~/sources/conventions.md",
    },
    "emplacements": {
        "section": "## Emplacements",
        "roles": {
            "perso": "vault perso",
            "pro": "vault pro",
            "foyer": "vault foyer",
        },
    },
    "conventions": {"table_header": "| Vault | Valeurs |"},
}


class SettingsWriter(Protocol):
    """Écrit le TOML de configuration (réglages neutres si ``None``)."""

    def __call__(self, settings: Settings | None = None) -> None:
        """Écrit les réglages donnés, ou ceux par défaut."""


@dataclass
class VaultsEnv:
    """Environnement isolé des tests de ``linuxtools.vaults``."""

    home: Path
    config_file: Path
    write_settings: SettingsWriter
    write_emplacements: Callable[[dict[str, str]], None]
    write_conventions: Callable[[dict[str, list[str]]], None]


def _toml_value(value: object) -> str:
    """Rend la valeur TOML d'un objet Python (str, int, list ou dict)."""
    if isinstance(value, dict):
        items = ", ".join(
            f"{json.dumps(k)} = {_toml_value(v)}" for k, v in value.items()
        )
        return "{ " + items + " }" if items else "{}"
    return json.dumps(value)


def render_vaults_toml(settings: Settings) -> str:
    """Sérialise des réglages en TOML (tables de premier niveau)."""
    lines: list[str] = []
    for table, content in settings.items():
        lines.append(f"[{table}]")
        lines.extend(f"{key} = {_toml_value(value)}" for key, value in content.items())
        lines.append("")
    return "\n".join(lines)


def without_key(settings: Settings, dotted_key: str) -> Settings:
    """Rend une copie profonde sans la clé pointée (table entière si sans point)."""
    result = copy.deepcopy(settings)
    table, _, key = dotted_key.partition(".")
    if key:
        del result[table][key]
    else:
        del result[table]
    return result


def with_value(settings: Settings, dotted_key: str, value: object) -> Settings:
    """Rend une copie profonde où la clé pointée vaut ``value``."""
    result = copy.deepcopy(settings)
    table, _, key = dotted_key.partition(".")
    result[table][key] = value
    return result


def emplacements_md(rows: dict[str, str]) -> str:
    """Rend un fichier d'emplacements : section et tableau Chemin | Contenu."""
    lines = ["## Emplacements", "", "| Chemin | Contenu |", "|---|---|"]
    lines.extend(f"| `{path}` | {label} |" for path, label in rows.items())
    return "\n".join(lines) + "\n"


def conventions_md(rows: dict[str, list[str]]) -> str:
    """Rend un fichier de conventions : tableau Vault | Valeurs."""
    lines = ["| Vault | Valeurs |", "|---|---|"]
    for vault, values in rows.items():
        cell = " · ".join(f"`{v}`" for v in values)
        lines.append(f"| {vault} | {cell} |")
    return "\n".join(lines) + "\n"
