"""Tests de l'ajout d'entrée CHANGELOG (linuxtools.devtools.changelog)."""

from __future__ import annotations

import pytest

from linuxtools.devtools.changelog import add_modified_entry

_ENTREE = "chore(deps): `linuxtools` épinglée en v2.11.1 (était v2.10.0)"


def test_ajoute_dans_modifie_existant() -> None:
    texte = (
        "# Changelog\n\n## [Non publié]\n\n### Modifié\n\n- ancienne\n\n"
        "## [1.0.0] - 2026-01-01\n"
    )

    resultat = add_modified_entry(texte, _ENTREE)

    assert resultat == (
        "# Changelog\n\n## [Non publié]\n\n### Modifié\n\n"
        f"- {_ENTREE}\n- ancienne\n\n## [1.0.0] - 2026-01-01\n"
    )


def test_ajoute_dans_modifie_colle_au_titre() -> None:
    texte = "## [Non publié]\n### Modifié\n- ancienne\n"

    resultat = add_modified_entry(texte, _ENTREE)

    assert resultat == (
        f"## [Non publié]\n### Modifié\n- {_ENTREE}\n- ancienne\n"
    )


def test_cree_modifie_apres_ajoute_avant_corrige() -> None:
    texte = (
        "## [Non publié]\n\n### Ajouté\n\n- a\n\n### Corrigé\n\n- c\n\n"
        "## [1.0.0] - 2026-01-01\n"
    )

    resultat = add_modified_entry(texte, _ENTREE)

    assert resultat == (
        "## [Non publié]\n\n### Ajouté\n\n- a\n\n"
        f"### Modifié\n\n- {_ENTREE}\n\n"
        "### Corrigé\n\n- c\n\n## [1.0.0] - 2026-01-01\n"
    )


def test_cree_modifie_dans_section_vide() -> None:
    texte = "# Changelog\n\n## [Non publié]\n\n## [1.0.0] - 2026-01-01\n"

    resultat = add_modified_entry(texte, _ENTREE)

    assert resultat == (
        "# Changelog\n\n## [Non publié]\n\n### Modifié\n\n"
        f"- {_ENTREE}\n\n## [1.0.0] - 2026-01-01\n"
    )


def test_cree_modifie_apres_la_derniere_sous_section() -> None:
    texte = "## [Non publié]\n\n### Ajouté\n\n- a\n\n## [1.0.0]\n"

    resultat = add_modified_entry(texte, _ENTREE)

    assert resultat == (
        "## [Non publié]\n\n### Ajouté\n\n- a\n\n"
        f"### Modifié\n\n- {_ENTREE}\n\n## [1.0.0]\n"
    )


def test_section_non_publie_absente_leve_valueerror() -> None:
    with pytest.raises(ValueError, match="Non publié"):
        add_modified_entry("# Changelog\n\n## [1.0.0]\n", _ENTREE)


@pytest.mark.parametrize(
    "texte",
    [
        "## [Non publié]\n",
        "## [Non publié]",
        "## [Non publié]\n\n### Ajouté\n\n- a",
        "## [Non publié]\n\n### Modifié\n\n- a",
    ],
)
def test_conserve_fin_de_fichier(texte: str) -> None:
    resultat = add_modified_entry(texte, _ENTREE)

    assert resultat.endswith("\n") == texte.endswith("\n")


def test_conserve_fins_de_ligne_crlf() -> None:
    texte = "## [Non publié]\r\n\r\n### Ajouté\r\n\r\n- a\r\n"

    resultat = add_modified_entry(texte, _ENTREE)

    assert "\n" not in resultat.replace("\r\n", "")
    assert f"- {_ENTREE}\r\n" in resultat
