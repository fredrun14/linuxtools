"""Réexports paresseux (PEP 562) pour les noms dépendant d'un extra."""

import sys
from collections.abc import Callable
from importlib import import_module
from typing import Any


def make_lazy_getattr(
    package: str,
    targets: dict[str, str],
) -> Callable[[str], Any]:
    """Construit le `__getattr__` (PEP 562) d'un paquet à réexports paresseux.

    Args:
        package: Nom du paquet hôte (`__name__` de l'appelant), utilisé
            pour le message d'`AttributeError` et le cache.
        targets: Table `nom_public -> module_qui_le_définit`.

    Returns:
        Une fonction `__getattr__(name)` à affecter au module hôte.
    """

    def _getattr_paresseux(name: str) -> Any:  # noqa: ANN401
        if name not in targets:
            raise AttributeError(
                f"module {package!r} has no attribute {name!r}"
            )
        # Une ImportError (extra absent) remonte telle quelle (Q-02).
        valeur = getattr(import_module(targets[name]), name)
        # Cache dans le module hôte : les accès suivants court-circuitent
        # `__getattr__`.
        sys.modules[package].__dict__[name] = valeur
        return valeur

    return _getattr_paresseux
