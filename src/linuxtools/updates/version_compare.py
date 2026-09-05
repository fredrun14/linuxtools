"""Comparaison de numéros de version au format dotté (X.Y.Z).

Pas de dépendance sur `packaging` (non stdlib) : une comparaison
volontairement minimale, suffisante pour des tags Forgejo au format
`vX.Y.Z` ou `X.Y.Z` — pas de gestion des identifiants de pré-release
(`-rc1`, `-beta`) au-delà de leur troncature silencieuse.
"""

from __future__ import annotations

import re

_VERSION_PATTERN = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Parse une chaîne de version en triplet (major, minor, patch).

    Args:
        text: Chaîne de version, ex. "1.26.0", "v1.26.0", "1.26".

    Returns:
        Triplet d'entiers, composants manquants à 0 (ex. "1.2" ->
        (1, 2, 0)). None si aucun chiffre de tête n'est reconnu
        (format totalement non numérique, ex. "latest", "").
    """
    match = _VERSION_PATTERN.match(text.strip())
    if match is None or match.group(1) is None:
        return None

    major = int(match.group(1))
    minor = int(match.group(2) or "0")
    patch = int(match.group(3) or "0")
    return (major, minor, patch)


def is_newer(candidate: str, current: str) -> bool | None:
    """Indique si candidate est une version strictement plus récente.

    Args:
        candidate: Version à comparer (ex. dernière release Forgejo).
        current: Version de référence (ex. version installée).

    Returns:
        True si candidate > current, False si candidate <= current,
        None si l'une des deux chaînes ne peut pas être parsée (cas
        où la comparaison n'est pas fiable — ne jamais deviner).
    """
    candidate_tuple = parse_version(candidate)
    current_tuple = parse_version(current)
    if candidate_tuple is None or current_tuple is None:
        return None

    return candidate_tuple > current_tuple
