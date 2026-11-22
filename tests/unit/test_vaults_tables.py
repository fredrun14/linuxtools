"""Tests du parseur privé de tableaux Markdown (`linuxtools.vaults._tables`)."""

import pytest

from linuxtools.vaults._tables import (
    Table,
    code_spans,
    find_section,
    find_table_by_header,
    first_table,
    split_row,
)


def test_split_row_decoupe_et_nettoie_les_cellules() -> None:
    assert split_row("|  A | b c |  |") == ("A", "b c", "")


def test_split_row_garde_la_barre_echappee() -> None:
    assert split_row(r"| a \| b | c |") == ("a | b", "c")


def test_find_section_rend_les_lignes_jusqu_au_titre_de_meme_niveau() -> None:
    text = "# Haut\n## Titre\nl1\nl2\n## Autre\nl3\n"

    assert find_section(text, "## Titre") == ["l1", "l2"]


def test_find_section_continue_apres_un_sous_titre() -> None:
    text = "## Titre\nl1\n### Sous\nl2\n## Autre\n"

    assert find_section(text, "## Titre") == ["l1", "### Sous", "l2"]


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_find_section_ignore_un_titre_dans_un_bloc_de_code(fence: str) -> None:
    text = f"## Titre\nl1\n{fence}\n## Faux\n{fence}\nl2\n## Autre\n"

    assert find_section(text, "## Titre") == ["l1", f"{fence}", "## Faux", fence, "l2"]


def test_find_section_rend_none_si_titre_absent() -> None:
    assert find_section("## Autre\nx\n", "## Titre") is None


def test_find_section_leve_si_titre_en_double() -> None:
    with pytest.raises(ValueError, match="en double"):
        find_section("## Titre\na\n## Titre\nb\n", "## Titre")


def test_find_section_leve_si_titre_sans_diese() -> None:
    with pytest.raises(ValueError, match="titre"):
        find_section("Titre\n", "Titre")


def test_first_table_rend_entete_et_lignes() -> None:
    lines = ["texte", "| A | B |", "|---|---|", "| 1 | 2 |", "| 3 | 4 |", "fin"]

    assert first_table(lines) == Table(("A", "B"), (("1", "2"), ("3", "4")))


def test_first_table_tolere_alignement_et_espaces() -> None:
    lines = ["|   A   |  B |", "|:----|----:|", "|  1  |   2 |"]

    assert first_table(lines) == Table(("A", "B"), (("1", "2"),))


def test_first_table_ignore_un_tableau_dans_un_bloc_de_code() -> None:
    lines = ["```", "| X |", "|---|", "```", "| A |", "|---|", "| 1 |"]

    assert first_table(lines) == Table(("A",), (("1",),))


def test_first_table_rend_none_sans_tableau() -> None:
    assert first_table(["rien", "ici"]) is None


@pytest.mark.parametrize("separator", [None, "| x | y |", "|---|"])
def test_first_table_leve_si_separateur_absent(separator: str | None) -> None:
    lines = ["| A | B |"] if separator is None else ["| A | B |", separator]

    with pytest.raises(ValueError, match="séparateur"):
        first_table(lines)


def test_first_table_leve_si_nombre_de_cellules_different() -> None:
    lines = ["| A | B |", "|---|---|", "| 1 |"]

    with pytest.raises(ValueError, match="cellules"):
        first_table(lines)


def test_find_table_by_header_trouve_l_entete_normalise() -> None:
    text = "intro\n|  A   x |  B |\n|---|---|\n| 1 | 2 |\n"

    assert find_table_by_header(text, "| A x | B |") == Table(
        ("A   x", "B"), (("1", "2"),)
    )


def test_find_table_by_header_rend_none_si_absent() -> None:
    assert find_table_by_header("| A |\n|---|\n", "| Z |") is None


def test_find_table_by_header_leve_si_en_double() -> None:
    text = "| A |\n|---|\n| 1 |\n\n| A |\n|---|\n| 2 |\n"

    with pytest.raises(ValueError, match="en double"):
        find_table_by_header(text, "| A |")


def test_code_spans_rend_les_segments_entre_backticks() -> None:
    assert code_spans("`a` · `b`, ` c `") == ["a", "b", "c"]


def test_code_spans_rend_liste_vide_sans_backticks() -> None:
    assert code_spans("") == []


def test_code_spans_leve_si_texte_hors_backticks() -> None:
    with pytest.raises(ValueError, match="hors backticks"):
        code_spans("`a` parasite")


@pytest.mark.parametrize(
    ("ouverture", "intrus", "fermeture"),
    [
        ("```", "~~~", "```"),
        ("````", "```", "````"),
        ("~~~", "```", "~~~"),
        ("```", "```python", "```"),
    ],
)
def test_find_section_ne_ferme_un_bloc_que_par_une_cloture_equivalente(
    ouverture: str, intrus: str, fermeture: str
) -> None:
    text = f"## Titre\n{ouverture}\n{intrus}\n## Faux\n{fermeture}\nl2\n## Autre\n"

    assert find_section(text, "## Titre") == [
        ouverture,
        intrus,
        "## Faux",
        fermeture,
        "l2",
    ]


def test_find_section_ferme_un_bloc_par_une_cloture_plus_longue() -> None:
    text = "## Titre\n```\n## Faux\n`````\n## Autre\nl\n"

    assert find_section(text, "## Titre") == ["```", "## Faux", "`````"]


def test_find_section_ne_prend_pas_une_ligne_a_backticks_pour_une_cloture() -> None:
    text = "## Titre\n```x```\n## Autre\nl\n"

    assert find_section(text, "## Titre") == ["```x```"]


@pytest.mark.parametrize("cell", ["` `", "`a` `  `"])
def test_code_spans_leve_si_un_segment_est_vide(cell: str) -> None:
    with pytest.raises(ValueError, match="vide"):
        code_spans(cell)


@pytest.mark.parametrize("indent", [" ", "  ", "   "])
def test_find_section_s_arrete_a_un_titre_indente_de_1_a_3_espaces(
    indent: str,
) -> None:
    text = f"## Titre\nl1\n{indent}## Autre\nl2\n"

    assert find_section(text, "## Titre") == ["l1"]


def test_find_section_ne_prend_pas_4_espaces_pour_un_titre() -> None:
    text = "## Titre\nl1\n    ## Code\nl2\n"

    assert find_section(text, "## Titre") == ["l1", "    ## Code", "l2"]


def test_find_section_ignore_un_titre_voulu_indente_de_quatre_espaces() -> None:
    assert find_section("    ## Titre\nl1\n", "## Titre") is None


def test_find_section_reconnait_un_titre_voulu_indente_de_trois_espaces() -> None:
    assert find_section("   ## Titre\nl1\n", "## Titre") == ["l1"]


def test_find_section_se_ferme_sur_un_titre_vide() -> None:
    assert find_section("## Titre\nl1\n#\nl2\n", "## Titre") == ["l1"]
