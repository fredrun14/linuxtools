"""Contrôle du diff d'un ``uv.lock`` après la montée du pin."""

# stdlib
import tomllib
from typing import Any

_Index = dict[str, tuple[str, str]]
_Graph = dict[str, set[str]]


def _index(text: str) -> tuple[_Index, _Graph]:
    """Indexe les paquets d'un lock : (version, source) et dépendances."""
    packages = tomllib.loads(text).get("package", [])
    index: _Index = {}
    graph: _Graph = {}
    for pkg in packages:
        name = pkg["name"]
        index[name] = (pkg.get("version", ""), repr(pkg.get("source")))
        deps = {d["name"] for d in pkg.get("dependencies", [])}
        optional: dict[str, Any] = pkg.get("optional-dependencies", {})
        for group in optional.values():
            deps.update(d["name"] for d in group)
        graph[name] = deps
    return index, graph


def _closure(graph: _Graph, root: str) -> set[str]:
    """Fermeture transitive de ``root`` (racine incluse si présente)."""
    if root not in graph:
        return set()
    seen: set[str] = set()
    todo = [root]
    while todo:
        name = todo.pop()
        if name in seen or name not in graph:
            continue
        seen.add(name)
        todo.extend(graph[name])
    return seen


def unexpected_lock_changes(
    old: str,
    new: str,
    root: str = "linuxtools",
) -> list[str]:
    """Paquets modifiés hors fermeture transitive de `root`.

    Un paquet est modifié si sa version ou sa source diffère, ou s'il
    est ajouté ou retiré. La fermeture de ``root`` est calculée dans
    l'ancien et le nouveau lock ; leur union est autorisée. L'en-tête
    ``revision`` n'est pas comparé.

    Args:
        old: Contenu de l'ancien ``uv.lock``.
        new: Contenu du nouveau ``uv.lock``.
        root: Paquet dont la fermeture transitive peut changer.

    Returns:
        Noms des paquets modifiés non autorisés, triés.
    """
    old_index, old_graph = _index(old)
    new_index, new_graph = _index(new)
    allowed = _closure(old_graph, root) | _closure(new_graph, root)
    changed = {
        name
        for name in old_index.keys() | new_index.keys()
        if old_index.get(name) != new_index.get(name)
    }
    return sorted(changed - allowed)
