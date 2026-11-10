"""Ajout d'une entrée « Modifié » dans un CHANGELOG Keep a Changelog."""

_UNRELEASED = "## [Non publié]"
_MODIFIED = "### Modifié"
# Ordre Keep a Changelog des sous-sections.
_ORDER = (
    "### Ajouté",
    "### Modifié",
    "### Obsolète",
    "### Retiré",
    "### Corrigé",
    "### Sécurité",
)


def add_modified_entry(text: str, entry: str) -> str:
    """Ajoute `entry` sous `### Modifié` de `## [Non publié]`.

    Les fins de ligne et la ligne finale du fichier d'origine sont
    conservées. La sous-section est créée à sa place dans l'ordre
    Keep a Changelog si elle n'existe pas.

    Args:
        text: Contenu du CHANGELOG.
        entry: Texte de la puce (sans le tiret).

    Returns:
        Nouveau contenu du CHANGELOG.

    Raises:
        ValueError: Si `## [Non publié]` est absent.
    """
    cr = "\r" if "\r\n" in text else ""
    lines = text.split("\n")
    start = next(
        (i for i, ln in enumerate(lines) if ln.rstrip("\r") == _UNRELEASED),
        None,
    )
    if start is None:
        raise ValueError(f"section « {_UNRELEASED} » absente du CHANGELOG")
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("## ")
        ),
        len(lines),
    )
    bullet = f"- {entry}{cr}"
    blank = cr

    titles = {
        lines[i].rstrip("\r"): i
        for i in range(start + 1, end)
        if lines[i].startswith("### ")
    }
    if _MODIFIED in titles:
        pos = titles[_MODIFIED] + 1
        if pos < end and lines[pos].strip() == "":
            pos += 1
        lines.insert(pos, bullet)
    else:
        after = _ORDER[_ORDER.index(_MODIFIED) + 1 :]
        later = [titles[t] for t in after if t in titles]
        if later:
            lines[min(later) : min(later)] = [
                f"{_MODIFIED}{cr}",
                blank,
                bullet,
                blank,
            ]
        else:
            pos = end
            while pos > start + 1 and lines[pos - 1].strip() == "":
                pos -= 1
            lines[pos:pos] = [blank, f"{_MODIFIED}{cr}", blank, bullet]
    return "\n".join(lines)
