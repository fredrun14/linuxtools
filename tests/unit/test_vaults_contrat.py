"""Contrat de lecture des sources du catalogue des vaults (F-08c, Q-02)."""

import re
import shutil
from pathlib import Path

import pytest

from linuxtools.config.xdg import XdgAppConfig
from linuxtools.vaults import VaultCatalog, VaultCatalogError, _tables
from tests.unit.vaults_helpers import DEFAULT_SETTINGS, VaultsEnv

FIXTURES = Path(__file__).parent / "fixtures" / "vaults"

ROLES = ("perso", "pro", "foyer")

# Valeurs de domaine recopiées de la fixture des conventions (pas de chemin).
DOMAINES = {
    "perso": {"python", "homelab", "ia", "linux", "reseau", "maison", "methode"},
    "pro": {"mainframe", "banque", "assurance", "carriere", "methode"},
    "foyer": {"finances", "maison", "moto", "auto", "sante", "methode"},
}


def _installe_fixtures(env: VaultsEnv) -> Path:
    """Copie les fixtures sous le HOME de test et crée les dossiers de rôle.

    Args:
        env: Environnement isolé.

    Returns:
        Le fichier des emplacements copié.
    """
    env.write_settings()
    sources = env.home / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    emplacements = sources / "emplacements.md"
    shutil.copy(FIXTURES / "emplacements.md", emplacements)
    shutil.copy(FIXTURES / "conventions.md", sources / "conventions.md")
    texte = emplacements.read_text(encoding="utf-8")
    labels = DEFAULT_SETTINGS["emplacements"]["roles"]
    assert isinstance(labels, dict)
    for label in labels.values():
        trouve = re.search(
            rf"^\| `([^`]+)` \| {re.escape(label)} \|$", texte, re.MULTILINE
        )
        assert trouve is not None
        cible = Path(trouve.group(1).replace("~", str(env.home), 1))
        cible.mkdir(parents=True, exist_ok=True)
    return emplacements


def test_contrat_fixture_trouve_les_trois_roles_et_leurs_domaines(
    vaults_env: VaultsEnv,
) -> None:
    _installe_fixtures(vaults_env)

    catalog = VaultCatalog.load()

    assert catalog.roles == ROLES
    for role in ROLES:
        assert catalog.root(role).is_dir()
        assert catalog.domaines(role) == DOMAINES[role]


def test_contrat_fixture_a_les_dix_lignes_du_tableau_et_un_chemin_par_ligne() -> None:
    texte = (FIXTURES / "emplacements.md").read_text(encoding="utf-8")
    lignes = _tables.find_section(texte, "## Emplacements")
    assert lignes is not None
    table = _tables.first_table(lignes)

    assert table is not None
    assert len(table.rows) == 10
    assert all(len(_tables.code_spans(row[0])) == 1 for row in table.rows)
    # Les deux libellés les plus chargés (backticks, parenthèses) sont présents.
    assert any("(`" in row[1] and ")" in row[1] for row in table.rows)


def test_contrat_fixture_echoue_si_un_libelle_change(vaults_env: VaultsEnv) -> None:
    emplacements = _installe_fixtures(vaults_env)
    texte = emplacements.read_text(encoding="utf-8")
    emplacements.write_text(texte.replace("vault pro", "vault travail"), "utf-8")

    catalog = VaultCatalog.load()

    with pytest.raises(VaultCatalogError):
        catalog.root("pro")


def test_contrat_fixture_echoue_si_l_entete_change(vaults_env: VaultsEnv) -> None:
    _installe_fixtures(vaults_env)
    conventions = vaults_env.home / "sources" / "conventions.md"
    texte = conventions.read_text(encoding="utf-8")
    conventions.write_text(texte.replace("| Vault |", "| Coffre |"), "utf-8")
    catalog = VaultCatalog.load()

    with pytest.raises(VaultCatalogError):
        catalog.domaines("perso")


def test_contrat_reel_trouve_les_trois_roles() -> None:
    if not (XdgAppConfig("vault-tools").config_dir / "vaults.toml").is_file():
        pytest.skip("configuration réelle absente")

    catalog = VaultCatalog.load()

    for role in catalog.roles:
        assert catalog.root(role).is_dir()
        assert catalog.domaines(role)
