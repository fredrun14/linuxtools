"""Découverte des dépôts consommateurs de linuxtools."""

# stdlib
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_PIN_MARKER = "linuxtools.git@"


@dataclass(frozen=True)
class Consumer:
    """Dépôt consommateur de linuxtools."""

    name: str  # [project] name
    path: Path  # racine du dépôt


def _as_consumer(directory: Path) -> Consumer | None:
    """Retourne le consommateur de ``directory``, ou None."""
    pyproject = directory / "pyproject.toml"
    if not (directory / ".git").exists() or not pyproject.is_file():
        return None
    text = pyproject.read_text(encoding="utf-8")
    if _PIN_MARKER not in text:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    name = data.get("project", {}).get("name") or directory.name
    if name == "linuxtools":
        return None
    return Consumer(name=str(name), path=directory)


def discover_consumers(
    root: Path,
    only: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> list[Consumer]:
    """Liste les consommateurs directs de ``root``, triés par dossier.

    Un consommateur est un sous-dossier direct contenant ``.git`` et un
    ``pyproject.toml`` qui référence ``linuxtools.git@``. Le dépôt
    linuxtools lui-même (``[project] name == "linuxtools"``) est exclu.
    ``only`` et ``exclude`` désignent un projet par son nom ou celui de
    son dossier.

    Args:
        root: Dossier contenant les dépôts.
        only: Ne garder que ces projets.
        exclude: Retirer ces projets.

    Returns:
        Consommateurs triés alphabétiquement par nom de dossier.

    Raises:
        ValueError: ``only`` et ``exclude`` donnés ensemble, ou nom
            inconnu.
    """
    if only and exclude:
        raise ValueError("--only et --exclude sont mutuellement exclusifs")
    found = [
        (child, consumer)
        for child in sorted(root.iterdir(), key=lambda p: p.name)
        if child.is_dir() and (consumer := _as_consumer(child))
    ]
    known = {c.name for _, c in found} | {d.name for d, _ in found}
    unknown = sorted((set(only) | set(exclude)) - known)
    if unknown:
        raise ValueError(f"projet inconnu : {', '.join(unknown)}")

    def selected(directory: Path, consumer: Consumer) -> bool:
        names = {directory.name, consumer.name}
        if only:
            return bool(names & set(only))
        return not names & set(exclude)

    return [c for d, c in found if selected(d, c)]
