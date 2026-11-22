"""Parseur privé de tableaux Markdown (fonctions pures, aucune E/S).

Échec fermé : tout ce qui n'est pas reconnu avec certitude est refusé. Ainsi un
séparateur de tableau réduit à ``|-|`` (une seule colonne, un seul tiret) est
refusé : ``|---|`` au moins par colonne est exigé, comme ``|:---|`` ou ``|---:|``.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

# Séparateurs admis : ceux du tableau des conventions (backticks, « · », « , »).
# Clôture CommonMark 4.5 : 0 à 3 espaces, 3 caractères ou plus, texte d'info.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:\s|$)")
_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_SPAN = re.compile(r"`([^`]+)`")
_ALLOWED_OUTSIDE = re.compile(r"^[\s·,]*$")


@dataclass(frozen=True)
class Table:
    """Tableau Markdown découpé en cellules.

    Attributes:
        header: Cellules de la ligne d'en-tête, nettoyées.
        rows: Lignes du corps (sans le séparateur), une liste de cellules chacune.
    """

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def split_row(line: str) -> tuple[str, ...]:
    r"""Découpe une ligne de tableau Markdown en cellules nettoyées.

    Les barres de bord sont retirées, ``\|`` est une barre littérale et chaque
    cellule est débarrassée de ses espaces de bord.

    Args:
        line: Ligne commençant par ``|``.

    Returns:
        Les cellules, dans l'ordre.
    """
    body = line.strip()
    body = body.removeprefix("|")
    body = body.removesuffix("|")
    return tuple(c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", body))


def _outside_code(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Rend ``(index, ligne)`` pour les lignes situées hors bloc de code.

    Les lignes de clôture elles-mêmes ne sont pas rendues. Un bloc ne se ferme
    que par une clôture du même caractère, d'une longueur au moins égale à celle
    d'ouverture et sans texte d'info (CommonMark 4.5).

    Args:
        lines: Lignes à parcourir.

    Yields:
        L'index d'origine et la ligne.
    """
    opening: str | None = None  # clôture d'ouverture du bloc en cours
    for index, line in enumerate(lines):
        match = _FENCE.match(line)
        if opening is not None:
            if (
                match is not None
                and match.group(1)[0] == opening[0]
                and len(match.group(1)) >= len(opening)
                and not match.group(2).strip()
            ):
                opening = None
        elif match is not None and not (
            match.group(1)[0] == "`" and "`" in match.group(2)
        ):
            opening = match.group(1)
        else:
            yield index, line


def find_section(text: str, heading: str) -> list[str] | None:
    """Rend les lignes d'une section Markdown, titre exclu.

    La section commence à la ligne égale à ``heading`` (après ``strip()``),
    indentée de 0 à 3 espaces (4 ou plus : bloc de code, pas un titre), et
    s'arrête au titre suivant de niveau inférieur ou égal (``#`` seul compris).
    Les titres situés dans un bloc de code (``` ou ~~~) ne comptent pas.

    Args:
        text: Contenu complet du fichier Markdown.
        heading: Titre exact, dièses compris (ex. ``"## Titre"``).

    Returns:
        Les lignes de la section, ou None si le titre est absent.

    Raises:
        ValueError: Si ``heading`` ne commence pas par ``#``, ou si le titre
            apparaît plusieurs fois hors bloc de code.
    """
    wanted = heading.strip()
    match = _HEADING.match(wanted)
    if match is None:
        msg = f"titre invalide (dièses attendus) : {heading}"
        raise ValueError(msg)
    level = len(match.group(1))
    lines = text.splitlines()
    start: int | None = None
    end = len(lines)
    for index, line in _outside_code(lines):
        found = _HEADING.match(line)
        if found and line.strip() == wanted:
            if start is not None:
                msg = f"titre en double : {heading}"
                raise ValueError(msg)
            start = index + 1
        elif start is not None and found and len(found.group(1)) <= level:
            end = min(end, index)
    if start is None:
        return None
    return lines[start:end]


def _normalize(cells: tuple[str, ...]) -> tuple[str, ...]:
    """Réduit les espaces internes de chaque cellule à un seul.

    Args:
        cells: Cellules déjà débarrassées de leurs espaces de bord.

    Returns:
        Les cellules normalisées.
    """
    return tuple(" ".join(cell.split()) for cell in cells)


def _parse_table(lines: list[str], index: int) -> Table:
    """Lit le tableau dont la ligne d'en-tête est ``lines[index]``.

    Args:
        lines: Lignes contenant le tableau.
        index: Position de la ligne d'en-tête.

    Returns:
        Le tableau lu.

    Raises:
        ValueError: Si le séparateur est absent ou invalide, ou si une ligne a un
            nombre de cellules différent de l'en-tête.
    """
    header = split_row(lines[index])
    following = lines[index + 1 : index + 2]
    separator = split_row(following[0]) if following else ()
    if len(separator) != len(header) or not all(
        _SEPARATOR_CELL.match(cell) for cell in separator
    ):
        msg = f"séparateur de tableau absent ou invalide après : {lines[index]}"
        raise ValueError(msg)
    rows: list[tuple[str, ...]] = []
    for body_line in lines[index + 2 :]:
        if not body_line.strip().startswith("|"):
            break
        cells = split_row(body_line)
        if len(cells) != len(header):
            msg = (
                f"ligne de tableau à {len(cells)} cellules, "
                f"{len(header)} attendues : {body_line}"
            )
            raise ValueError(msg)
        rows.append(cells)
    return Table(header, tuple(rows))


def first_table(lines: list[str]) -> Table | None:
    """Rend le premier tableau trouvé hors bloc de code.

    Args:
        lines: Lignes à parcourir (ex. le retour de ``find_section``).

    Returns:
        Le tableau, ou None s'il n'y en a aucun.

    Raises:
        ValueError: Si le tableau est mal formé (séparateur absent ou invalide,
            ligne au nombre de cellules différent de l'en-tête).
    """
    for index, line in _outside_code(lines):
        if line.strip().startswith("|"):
            return _parse_table(lines, index)
    return None


def find_table_by_header(text: str, header: str) -> Table | None:
    """Rend l'unique tableau dont l'en-tête égale ``header``, hors blocs de code.

    La comparaison porte sur les cellules normalisées (espaces de bord retirés,
    espaces internes réduits à un), donc tolère l'alignement.

    Args:
        text: Contenu complet du fichier Markdown.
        header: Ligne d'en-tête attendue (ex. ``"| A | B |"``).

    Returns:
        Le tableau, ou None si aucun en-tête ne correspond.

    Raises:
        ValueError: Si plusieurs tableaux correspondent, ou si le tableau trouvé
            est mal formé.
    """
    wanted = _normalize(split_row(header))
    lines = text.splitlines()
    found: list[Table] = []
    for index, line in _outside_code(lines):
        if line.strip().startswith("|") and _normalize(split_row(line)) == wanted:
            found.append(_parse_table(lines, index))
    if len(found) > 1:
        msg = f"en-tête de tableau en double : {header}"
        raise ValueError(msg)
    return found[0] if found else None


def code_spans(cell: str) -> list[str]:
    """Rend les segments entre backticks d'une cellule.

    Hors backticks, seuls les espaces, ``·`` et ``,`` sont admis.

    Args:
        cell: Contenu d'une cellule.

    Returns:
        Les segments, sans les backticks, dans l'ordre ; liste vide si aucun.

    Raises:
        ValueError: Si du texte autre que les séparateurs admis figure hors
            backticks, ou si un segment est vide une fois ses espaces retirés.
    """
    if not _ALLOWED_OUTSIDE.match(_SPAN.sub("", cell)):
        msg = f"texte hors backticks dans la cellule : {cell}"
        raise ValueError(msg)
    spans = [span.strip() for span in _SPAN.findall(cell)]
    if not all(spans):
        msg = f"segment vide entre backticks dans la cellule : {cell}"
        raise ValueError(msg)
    return spans
