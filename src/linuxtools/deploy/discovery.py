"""Auto-détection du répertoire source d'un projet Python.

Fonctions pures et sans effet de bord, réutilisées par le Deployer
(V1) pour résoudre `DeployConfig.source_dir` quand il n'est pas
fourni explicitement. Logique inspirée d'`UsbExportManager`
(fedora_post_install), corrigée : boucle `while` au lieu d'un
`range(N)` fragile qui suppose une profondeur de fichier fixe.
"""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path


def find_project_source(start: Path | None = None) -> Path | None:
    """Remonte depuis `start` jusqu'à un répertoire pyproject.toml.

    Args:
        start: Point de départ (défaut : répertoire courant,
            Path.cwd()).

    Returns:
        Le premier répertoire ancêtre contenant pyproject.toml, ou
        None si la remontée jusqu'à la racine n'en trouve aucun.
    """
    candidate = (start or Path.cwd()).resolve()
    while candidate != candidate.parent:
        if (candidate / "pyproject.toml").is_file():
            return candidate
        candidate = candidate.parent
    # Dernière vérification sur la racine elle-même (candidate == /).
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return None


def find_editable_source(distribution: str) -> Path | None:
    """Localise le source d'une distribution installée en mode éditable.

    Lit direct_url.json de la distribution : si l'install est
    éditable (dir_info.editable) et pointe un file://, retourne le
    Path local.

    Args:
        distribution: Nom de la distribution (ex. "linuxtools").

    Returns:
        Chemin du source éditable, ou None si absent/non-éditable.
    """
    try:
        dist = metadata.distribution(distribution)
    except metadata.PackageNotFoundError:
        return None

    raw = dist.read_text("direct_url.json")
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not data.get("dir_info", {}).get("editable"):
        return None

    url = data.get("url", "")
    if not url.startswith("file://"):
        return None

    return Path(url[len("file://"):])
