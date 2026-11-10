"""Tests du manifeste consommateur (linuxtools.devtools.manifest)."""

from __future__ import annotations

import tomllib

import pytest

from linuxtools.devtools.manifest import (
    ConsumerManifest,
    ManifestError,
    SiblingDep,
    pinned_linuxtools_tags,
    rewrite_pin,
)

_PIN = (
    "linuxtools[credentials] @ "
    "git+https://git.ricfasohel.fr/fred/linuxtools.git@v2.10.0"
)

_CONTRAT = """
[tool.linuxtools.consumer]
sync-args = ["--extra", "dev"]
checks = [["pytest"], ["mypy", "src/app/"]]
"""


def _pyproject(
    deps: tuple[str, ...] = (_PIN,),
    contrat: str = _CONTRAT,
    name: str = "demo",
) -> str:
    """Construit un pyproject consommateur minimal."""
    lignes = ",\n    ".join(f'"{d}"' for d in deps)
    return (
        f'[project]\nname = "{name}"\nversion = "1.0"\n'
        f"dependencies = [\n    {lignes},\n]\n{contrat}"
    )


def test_parse_extrait_extras_et_tag() -> None:
    manifest = ConsumerManifest.parse(_pyproject())

    assert manifest.name == "demo"
    assert manifest.extras == ("credentials",)
    assert manifest.tag == "v2.10.0"
    assert manifest.siblings == ()
    assert manifest.sync_args == ("--extra", "dev")
    assert manifest.checks == (("pytest",), ("mypy", "src/app/"))


def test_parse_pin_sans_extras_dans_optional_dependencies() -> None:
    texte = (
        '[project]\nname = "demo"\n'
        "[project.optional-dependencies]\n"
        'dev = ["linuxtools @ git+https://git.ricfasohel.fr/fred/'
        'linuxtools.git@v1.2.3"]\n' + _CONTRAT
    )

    manifest = ConsumerManifest.parse(texte)

    assert manifest.extras == ()
    assert manifest.tag == "v1.2.3"


def test_parse_refuse_toml_invalide() -> None:
    with pytest.raises(ManifestError):
        ConsumerManifest.parse("[project\nname =")


def test_parse_refuse_sans_nom_de_projet() -> None:
    with pytest.raises(ManifestError):
        ConsumerManifest.parse(
            f'[project]\ndependencies = ["{_PIN}"]\n{_CONTRAT}'
        )


def test_parse_refuse_sans_pin() -> None:
    with pytest.raises(ManifestError, match="pin"):
        ConsumerManifest.parse(_pyproject(deps=("requests>=2",)))


def test_parse_refuse_pin_en_double() -> None:
    with pytest.raises(ManifestError, match="pin"):
        ConsumerManifest.parse(_pyproject(deps=(_PIN, _PIN)))


@pytest.mark.parametrize(
    "contrat",
    [
        "",
        "[tool.linuxtools.consumer]\nsync-args = []\n",
        "[tool.linuxtools.consumer]\nchecks = []\n",
        '[tool.linuxtools.consumer]\nchecks = ["pytest"]\n',
        "[tool.linuxtools.consumer]\nchecks = [[]]\n",
        '[tool.linuxtools.consumer]\nchecks = [["pytest"]]\nsync-args = [1]\n',
        '[tool.linuxtools.consumer]\nchecks = [["pytest", 2]]\n',
        '[tool.linuxtools.consumer]\nchecks = [["pytest"]]\nsync-args = "x"\n',
    ],
)
def test_parse_refuse_contrat_absent_ou_invalide(contrat: str) -> None:
    with pytest.raises(ManifestError, match="contrat consommateur"):
        ConsumerManifest.parse(_pyproject(contrat=contrat))


def test_parse_sync_args_par_defaut_vide() -> None:
    contrat = '[tool.linuxtools.consumer]\nchecks = [["pytest"]]\n'

    manifest = ConsumerManifest.parse(_pyproject(contrat=contrat))

    assert manifest.sync_args == ()


@pytest.mark.parametrize("argv0", ["../bin/x", "a b", ";", "/bin/sh", ""])
def test_parse_refuse_argv0_avec_separateur(argv0: str) -> None:
    contrat = f'[tool.linuxtools.consumer]\nchecks = [["{argv0}"]]\n'

    with pytest.raises(ManifestError, match="contrat consommateur"):
        ConsumerManifest.parse(_pyproject(contrat=contrat))


def test_parse_detecte_dependance_maison() -> None:
    maison = (
        "webapitools @ git+https://git.ricfasohel.fr/fred/"
        "webapitools.git@v0.13.0"
    )

    manifest = ConsumerManifest.parse(_pyproject(deps=(_PIN, maison)))

    assert manifest.siblings == (
        SiblingDep(
            name="webapitools",
            url="https://git.ricfasohel.fr/fred/webapitools.git",
            tag="v0.13.0",
        ),
    )


def test_rewrite_pin_ne_change_que_le_tag() -> None:
    texte = _pyproject()

    nouveau = rewrite_pin(texte, "v2.11.1")

    assert nouveau == texte.replace("v2.10.0", "v2.11.1")
    assert tomllib.loads(nouveau)["project"]["dependencies"] == [
        _PIN.replace("v2.10.0", "v2.11.1")
    ]


def test_rewrite_pin_refuse_pin_en_double() -> None:
    with pytest.raises(ManifestError):
        rewrite_pin(_pyproject(deps=(_PIN, _PIN)), "v2.11.1")


def test_rewrite_pin_refuse_pin_absent() -> None:
    with pytest.raises(ManifestError):
        rewrite_pin(_pyproject(deps=("requests>=2",)), "v2.11.1")


def test_rewrite_pin_refuse_tag_invalide() -> None:
    with pytest.raises(ManifestError):
        rewrite_pin(_pyproject(), "v2.11.1; rm")


def test_rewrite_pin_refuse_toml_invalide() -> None:
    with pytest.raises(ManifestError):
        rewrite_pin("[project\n", "v2.11.1")


def test_rewrite_pin_refuse_pin_seulement_en_commentaire() -> None:
    texte = (
        '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        "# linuxtools @ git+https://git.ricfasohel.fr/fred/"
        "linuxtools.git@v2.10.0\n"
    )

    with pytest.raises(ManifestError):
        rewrite_pin(texte, "v2.11.1")


@pytest.mark.parametrize(
    "copie",
    [
        "# linuxtools @ git+https://git.ricfasohel.fr/fred/"
        "linuxtools.git@v2.10.0\n",
        '[tool.autre]\nnote = "linuxtools @ git+https://git.ricfasohel.fr/'
        'fred/linuxtools.git@v2.10.0"\n',
    ],
    ids=["commentaire", "table-tool"],
)
def test_rewrite_pin_refuse_pin_valide_et_meme_chaine_ailleurs(
    copie: str,
) -> None:
    # Le pin réel est unique côté TOML, mais la chaîne figure deux fois
    # dans le texte : la substitution textuelle toucherait les deux.
    texte = _pyproject() + copie

    with pytest.raises(ManifestError, match="absent ou en double"):
        rewrite_pin(texte, "v2.11.1")


def test_rewrite_pin_refuse_reecriture_qui_deborde() -> None:
    # Le pin réel est écrit avec une séquence d'échappement (invisible
    # pour la regex texte) ; seul le commentaire serait réécrit.
    texte = (
        '[project]\nname = "demo"\n'
        'dependencies = ["linuxtools\\u0020@ git+https://git.ricfasohel.fr/'
        'fred/linuxtools.git@v2.10.0"]\n'
        "# linuxtools @ git+https://git.ricfasohel.fr/fred/"
        "linuxtools.git@v2.10.0\n"
    )

    with pytest.raises(ManifestError, match="plus que le pin"):
        rewrite_pin(texte, "v2.11.1")


def test_rewrite_pin_conserve_listes_et_tables_ailleurs() -> None:
    texte = _pyproject() + '\n[tool.autre]\nx = [1, {a = "b"}]\n'

    nouveau = rewrite_pin(texte, "v2.11.1")

    assert tomllib.loads(nouveau)["tool"]["autre"] == {"x": [1, {"a": "b"}]}


def test_pinned_linuxtools_tags_liste_les_pins() -> None:
    texte = _pyproject(contrat="")

    assert pinned_linuxtools_tags(texte) == ("v2.10.0",)
    assert pinned_linuxtools_tags(_pyproject(deps=("requests",))) == ()


def test_pinned_linuxtools_tags_refuse_toml_invalide() -> None:
    with pytest.raises(ManifestError):
        pinned_linuxtools_tags("[project\n")
