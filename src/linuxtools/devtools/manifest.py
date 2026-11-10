"""Lecture et réécriture du pyproject d'un projet consommateur.

Tout le savoir sur le ``pyproject.toml`` d'un consommateur (pin de
linuxtools, dépendances maison, contrat ``[tool.linuxtools.consumer]``)
reste ici : regex, ``tomllib`` et invariant de réécriture.
"""

# stdlib
import re
import tomllib
from dataclasses import dataclass
from typing import Any

_TAG = r"v\d+\.\d+\.\d+"
_PIN_HEAD = (
    r"linuxtools(?:\[[^\]]*\])?\s*@\s*"
    r"git\+https://git\.ricfasohel\.fr/fred/linuxtools\.git@"
)
# Pin complet d'une requirement (ancré) : extras et tag capturés.
_PIN_RE = re.compile(
    r"^linuxtools(?:\[(?P<extras>[^\]]*)\])?\s*@\s*"
    r"git\+https://git\.ricfasohel\.fr/fred/linuxtools\.git@"
    rf"(?P<tag>{_TAG})$"
)
# Pin repéré dans le texte brut, tag exclu (groupe `head` conservé).
_PIN_TEXT_RE = re.compile(rf"(?P<head>{_PIN_HEAD}){_TAG}")
_SIBLING_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*@\s*"
    r"git\+(?P<url>https://git\.ricfasohel\.fr/fred/[^@\s]+\.git)"
    r"@(?P<tag>\S+)$"
)
_TAG_RE = re.compile(rf"^{_TAG}$")
_ARGV0_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class ManifestError(Exception):
    """Pyproject consommateur inexploitable (motif dans le message)."""


@dataclass(frozen=True)
class SiblingDep:
    """Dépendance maison épinglée (nom, URL git, tag)."""

    name: str
    url: str
    tag: str


@dataclass(frozen=True)
class ConsumerManifest:
    """Contenu utile du pyproject d'un consommateur."""

    name: str
    extras: tuple[str, ...]
    tag: str
    siblings: tuple[SiblingDep, ...]
    sync_args: tuple[str, ...]
    checks: tuple[tuple[str, ...], ...]

    @classmethod
    def parse(cls, text: str) -> "ConsumerManifest":
        """Analyse le texte d'un pyproject consommateur.

        Args:
            text: Contenu du ``pyproject.toml``.

        Returns:
            Manifeste avec pin, dépendances maison et contrat.

        Raises:
            ManifestError: TOML invalide, nom absent, pin absent ou
                double, contrat consommateur absent ou invalide.
        """
        data = _load(text)
        project = data.get("project", {})
        name = project.get("name")
        if not isinstance(name, str) or not name:
            raise ManifestError("[project] name absent")

        requirements = _requirements(project)
        pins = [m for r in requirements if (m := _PIN_RE.match(r))]
        if len(pins) != 1:
            raise ManifestError(
                f"pin linuxtools attendu en un seul exemplaire, "
                f"trouvé {len(pins)}"
            )
        extras_raw = pins[0].group("extras") or ""
        extras = tuple(e.strip() for e in extras_raw.split(",") if e.strip())

        siblings = tuple(
            SiblingDep(m["name"], m["url"], m["tag"])
            for r in requirements
            if (m := _SIBLING_RE.match(r)) and m["name"] != "linuxtools"
        )
        sync_args, checks = _contract(data)
        return cls(
            name=name,
            extras=extras,
            tag=pins[0].group("tag"),
            siblings=siblings,
            sync_args=sync_args,
            checks=checks,
        )


def _load(text: str) -> dict[str, Any]:
    """Charge un TOML ou lève ``ManifestError``."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"TOML invalide : {exc}") from exc


def _requirements(project: dict[str, Any]) -> list[str]:
    """Liste les requirements de ``dependencies`` et des extras."""
    result: list[str] = [
        r for r in project.get("dependencies", []) if isinstance(r, str)
    ]
    for group in project.get("optional-dependencies", {}).values():
        result.extend(r for r in group if isinstance(r, str))
    return result


def _contract(
    data: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Extrait et valide ``[tool.linuxtools.consumer]``."""
    section = data.get("tool", {}).get("linuxtools", {}).get("consumer")
    if not isinstance(section, dict):
        raise ManifestError("contrat consommateur absent ou invalide : table")
    sync_args = section.get("sync-args", [])
    checks = section.get("checks")
    if not _is_str_list(sync_args):
        raise ManifestError(
            "contrat consommateur absent ou invalide : sync-args"
        )
    if (
        not isinstance(checks, list)
        or not checks
        or not all(_is_str_list(c) and c for c in checks)
    ):
        raise ManifestError("contrat consommateur absent ou invalide : checks")
    for check in checks:
        if not _ARGV0_RE.match(check[0]):
            raise ManifestError(
                "contrat consommateur absent ou invalide : "
                f"commande {check[0]!r} refusée"
            )
    return (
        tuple(sync_args),
        tuple(tuple(c) for c in checks),
    )


def _is_str_list(value: object) -> bool:
    """Indique si ``value`` est une liste de chaînes."""
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _substitute(value: Any, new_tag: str) -> Any:  # noqa: ANN401
    """Remplace le tag du pin dans toute valeur TOML (récursif)."""
    if isinstance(value, str):
        match = _PIN_RE.match(value)
        if match:
            return value[: match.start("tag")] + new_tag
        return value
    if isinstance(value, list):
        return [_substitute(v, new_tag) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, new_tag) for k, v in value.items()}
    return value


def rewrite_pin(text: str, new_tag: str) -> str:
    """Remplace uniquement le tag du pin linuxtools.

    La forme de la ligne est conservée. Après réécriture, le contenu
    TOML ne doit différer que par la chaîne du pin.

    Args:
        text: Contenu du ``pyproject.toml``.
        new_tag: Nouveau tag ``vX.Y.Z``.

    Returns:
        Texte réécrit.

    Raises:
        ManifestError: Tag invalide, pin absent ou en double, ou
            réécriture modifiant autre chose que le pin.
    """
    if not _TAG_RE.match(new_tag):
        raise ManifestError(f"tag invalide : {new_tag!r}")
    old_data = _load(text)
    data_pins = [
        r
        for r in _requirements(old_data.get("project", {}))
        if _PIN_RE.match(r)
    ]
    if len(_PIN_TEXT_RE.findall(text)) != 1 or len(data_pins) != 1:
        raise ManifestError("pin linuxtools absent ou en double")
    result = _PIN_TEXT_RE.sub(
        lambda m: m.group("head") + new_tag,
        text,
    )
    if _load(result) != _substitute(old_data, new_tag):
        raise ManifestError("la réécriture modifie plus que le pin")
    return result


def pinned_linuxtools_tags(text: str) -> tuple[str, ...]:
    """Liste les tags de linuxtools épinglés dans un pyproject.

    Sert à vérifier une dépendance maison : aucun contrat consommateur
    n'est exigé.

    Args:
        text: Contenu d'un ``pyproject.toml``.

    Returns:
        Tags ``vX.Y.Z`` trouvés (vide si aucun pin).

    Raises:
        ManifestError: TOML invalide.
    """
    project = _load(text).get("project", {})
    return tuple(
        m.group("tag")
        for r in _requirements(project)
        if (m := _PIN_RE.match(r))
    )
