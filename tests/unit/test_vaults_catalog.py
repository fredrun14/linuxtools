"""Tests de ``VaultCatalog`` : emplacements, ``roles``, ``root``, ``role_of``."""

import os
import stat
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeVar
from unittest.mock import MagicMock

import pytest

from linuxtools.logging.base import Logger
from linuxtools.vaults.catalog import VaultCatalog, VaultCatalogError
from tests.unit.vaults_helpers import DEFAULT_SETTINGS, VaultsEnv, with_value


def _setup(env: VaultsEnv) -> dict[str, Path]:
    """Crée trois dossiers de vault et les écrit dans les sources."""
    dirs = {name: env.home / f"coffre-{name}" for name in ("perso", "pro", "foyer")}
    for path in dirs.values():
        path.mkdir()
    env.write_settings()
    env.write_emplacements(
        {
            str(dirs["perso"]): "vault perso",
            str(dirs["pro"]): "vault pro",
            str(dirs["foyer"]): "vault foyer",
        }
    )
    return dirs


def test_load_lit_les_racines_des_trois_roles(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)

    catalog = VaultCatalog.load()

    assert {r: catalog.root(r) for r in catalog.roles} == {
        r: d.resolve() for r, d in dirs.items()
    }


def test_roles_suit_l_ordre_du_toml(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)

    assert VaultCatalog.load().roles == ("perso", "pro", "foyer")


def test_root_expanse_le_tilde_du_tableau(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements({"~/coffre-perso": "vault perso"})

    assert VaultCatalog.load().root("perso") == dirs["perso"].resolve()


def test_load_ignore_les_lignes_sans_libelle_de_role(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements(
        {"/n/importe/quoi": "autre emplacement", str(dirs["pro"]): "vault pro"}
    )

    catalog = VaultCatalog.load()

    assert catalog.root("pro") == dirs["pro"].resolve()


def test_load_ignore_un_tableau_dans_un_bloc_de_code_de_la_section(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_settings()
    reel = f"| `{dirs['pro']}` | vault pro |"
    contenu = (
        "## Emplacements\n\n```\n| A | B |\n|---|---|\n| `/faux` | vault pro |\n```\n\n"
        f"| Chemin | Contenu |\n|---|---|\n{reel}\n"
    )
    (vaults_env.home / "sources" / "emplacements.md").write_text(
        contenu, encoding="utf-8"
    )

    assert VaultCatalog.load().root("pro") == dirs["pro"].resolve()


def _ecrire_emplacements(env: VaultsEnv, contenu: str) -> None:
    """Écrit un fichier d'emplacements brut (cas mal formés)."""
    env.write_settings()
    cible = env.home / "sources" / "emplacements.md"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")


def test_load_leve_si_fichier_emplacements_absent(vaults_env: VaultsEnv) -> None:
    vaults_env.write_settings()

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert info.value.key == "sources.emplacements"
    assert info.value.source == vaults_env.config_file
    assert "emplacements.md" in str(info.value)


def test_load_leve_si_fichier_emplacements_illisible(vaults_env: VaultsEnv) -> None:
    _ecrire_emplacements(vaults_env, "")
    cible = vaults_env.home / "sources" / "emplacements.md"
    cible.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert info.value.source == cible
    assert isinstance(info.value.__cause__, UnicodeDecodeError)


def test_load_leve_si_emplacements_est_un_dossier(vaults_env: VaultsEnv) -> None:
    vaults_env.write_settings()
    (vaults_env.home / "sources" / "emplacements.md").mkdir(parents=True)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert isinstance(info.value.__cause__, OSError)


def test_load_leve_si_section_absente(vaults_env: VaultsEnv) -> None:
    _ecrire_emplacements(vaults_env, "## Autre\n")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert info.value.key == "emplacements.section"


def test_load_leve_si_section_sans_tableau(vaults_env: VaultsEnv) -> None:
    _ecrire_emplacements(vaults_env, "## Emplacements\n\ntexte seul\n")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert "aucun tableau" in str(info.value)


def test_load_leve_si_tableau_mal_forme(vaults_env: VaultsEnv) -> None:
    _ecrire_emplacements(vaults_env, "## Emplacements\n\n| A | B |\n| pas | sep |\n")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert isinstance(info.value.__cause__, ValueError)


def test_load_leve_si_tableau_a_une_seule_colonne(vaults_env: VaultsEnv) -> None:
    _ecrire_emplacements(vaults_env, "## Emplacements\n\n| A |\n|---|\n| x |\n")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert "structure inattendue" in str(info.value)


def test_load_leve_si_libelle_en_double(vaults_env: VaultsEnv) -> None:
    _ecrire_emplacements(
        vaults_env,
        "## Emplacements\n\n| C | L |\n|---|---|\n| `/a` | vault pro |\n"
        "| `/b` | vault pro |\n",
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert info.value.key == "emplacements.roles"


@pytest.mark.parametrize("cellule", ["/a sans backticks", "`/a` `/b`", "`/a` texte"])
def test_load_leve_si_cellule_chemin_invalide(
    vaults_env: VaultsEnv, cellule: str
) -> None:
    _ecrire_emplacements(
        vaults_env,
        f"## Emplacements\n\n| C | L |\n|---|---|\n| {cellule} | vault pro |\n",
    )

    with pytest.raises(VaultCatalogError):
        VaultCatalog.load()


def test_root_leve_si_role_inconnu(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("inconnu")

    assert "perso, pro, foyer" in str(info.value)
    assert info.value.key == "emplacements.roles"


def test_root_leve_si_libelle_absent_du_tableau(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({"/x": "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("perso")

    assert info.value.key == "emplacements.roles.perso"


def test_root_leve_si_dossier_absent(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({str(vaults_env.home / "absent"): "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert "introuvable" in str(info.value)


def test_root_refuse_un_chemin_relatif_du_tableau(
    vaults_env: VaultsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({"coffre-pro": "vault pro"})
    # « coffre-pro » existe sous le cwd (vaults_env.home) : seul le relatif compte.
    monkeypatch.chdir(vaults_env.home)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert "relatif refusé" in str(info.value)


def test_root_n_utilise_pas_le_role_comme_chemin(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    (vaults_env.home / "x").mkdir()

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("../x")

    assert "inconnu" in str(info.value)


def test_role_of_rend_le_role_si_chemin_egal_a_la_racine(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)

    assert VaultCatalog.load().role_of(dirs["pro"]) == "pro"


def test_role_of_suit_un_lien_symbolique_vers_la_racine(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    lien = vaults_env.home / "lien"
    lien.symlink_to(dirs["foyer"])

    assert VaultCatalog.load().role_of(lien) == "foyer"


def test_role_of_rend_none_pour_un_sous_dossier(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)
    (dirs["pro"] / "sous").mkdir()

    assert VaultCatalog.load().role_of(dirs["pro"] / "sous") is None


def test_role_of_rend_none_pour_un_chemin_inconnu(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)

    assert VaultCatalog.load().role_of(vaults_env.home) is None


def test_role_of_ignore_un_role_dont_le_dossier_manque(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements(
        {
            "relatif": "vault perso",
            str(vaults_env.home / "absent"): "vault pro",
            str(dirs["foyer"]): "vault foyer",
        }
    )

    catalog = VaultCatalog.load()

    assert catalog.role_of(dirs["foyer"]) == "foyer"
    assert catalog.role_of(dirs["perso"]) is None


def test_role_of_ignore_un_role_absent_du_tableau(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements({str(dirs["foyer"]): "vault foyer"})

    catalog = VaultCatalog.load()

    assert catalog.role_of(dirs["foyer"]) == "foyer"
    assert catalog.role_of(dirs["pro"]) is None


def test_load_journalise_le_chargement_si_logger_fourni(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    logger = MagicMock(spec=Logger)

    VaultCatalog.load(logger=logger)

    logger.log_info.assert_called_once()
    assert "3 rôles" in logger.log_info.call_args.args[0]


def test_domaines_rend_les_valeurs_du_role(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": ["alpha", "beta"], "perso": ["gamma"]})

    assert VaultCatalog.load().domaines("pro") == frozenset({"alpha", "beta"})


def test_domaines_differe_selon_le_role(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": ["alpha"], "perso": ["gamma"]})

    catalog = VaultCatalog.load()

    assert "alpha" in catalog.domaines("pro")
    assert "alpha" not in catalog.domaines("perso")


def test_domaines_accepte_une_valeur_ajoutee_au_fichier(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": ["alpha"]})
    assert VaultCatalog.load().domaines("pro") == frozenset({"alpha"})

    vaults_env.write_conventions({"pro": ["alpha", "nouvelle"]})

    assert VaultCatalog.load().domaines("pro") == frozenset({"alpha", "nouvelle"})


def test_domaines_ne_relit_pas_le_fichier_apres_la_premiere_demande(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": ["alpha"]})
    catalog = VaultCatalog.load()
    catalog.domaines("pro")
    (vaults_env.home / "sources" / "conventions.md").unlink()

    assert catalog.domaines("pro") == frozenset({"alpha"})


def test_load_ne_lit_pas_le_fichier_de_conventions(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)

    catalog = VaultCatalog.load()

    assert catalog.root("pro") == dirs["pro"].resolve()


def test_domaines_tolere_alignement_et_separateurs(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    (vaults_env.home / "sources").mkdir(exist_ok=True)
    (vaults_env.home / "sources" / "conventions.md").write_text(
        "|  Vault   |   Valeurs |\n|:---|---:|\n| pro  | `a` , `b` · `c`   `d` |\n",
        encoding="utf-8",
    )

    assert VaultCatalog.load().domaines("pro") == frozenset({"a", "b", "c", "d"})


def test_domaines_ignore_un_tableau_dans_un_bloc_de_code(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": ["vrai"]})
    path = vaults_env.home / "sources" / "conventions.md"
    leurre = "```\n| Vault | Valeurs |\n|---|---|\n| pro | `faux` |\n```\n\n"
    path.write_text(leurre + path.read_text(encoding="utf-8"), encoding="utf-8")

    assert VaultCatalog.load().domaines("pro") == frozenset({"vrai"})


def test_domaines_leve_si_fichier_conventions_absent(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "introuvable" in str(info.value)
    assert "sources.conventions" in str(info.value)


def test_domaines_leve_si_tableau_introuvable(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    (vaults_env.home / "sources").mkdir(exist_ok=True)
    (vaults_env.home / "sources" / "conventions.md").write_text(
        "Rien ici.\n", encoding="utf-8"
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "tableau" in str(info.value)
    assert "conventions.table_header" in str(info.value)


def test_domaines_leve_si_tableau_en_double(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": ["a"]})
    path = vaults_env.home / "sources" / "conventions.md"
    texte = path.read_text(encoding="utf-8")
    path.write_text(texte + "\n" + texte, encoding="utf-8")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "double" in str(info.value)


def test_domaines_leve_si_role_sans_ligne(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"perso": ["a"]})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "aucune ligne pour le rôle « pro »" in str(info.value)


def test_domaines_leve_si_ligne_en_double(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    path_rows = "| Vault | Valeurs |\n|---|---|\n| pro | `a` |\n| pro | `b` |\n"
    (vaults_env.home / "sources").mkdir(exist_ok=True)
    (vaults_env.home / "sources" / "conventions.md").write_text(
        path_rows, encoding="utf-8"
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "« pro » en double" in str(info.value)


def test_domaines_leve_si_cellule_vide(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_conventions({"pro": []})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "vide" in str(info.value)


def test_domaines_leve_si_texte_hors_backticks(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    (vaults_env.home / "sources").mkdir(exist_ok=True)
    (vaults_env.home / "sources" / "conventions.md").write_text(
        "| Vault | Valeurs |\n|---|---|\n| pro | `a` et autre |\n",
        encoding="utf-8",
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "hors backticks" in str(info.value)


def test_domaines_leve_si_role_inconnu(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("inconnu")

    assert "inconnu" in str(info.value)


def test_root_leve_si_chemin_du_tableau_a_utilisateur_inconnu(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({"~utilisateur-inexistant-xyz/v": "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert "utilisateur-inexistant-xyz" in str(info.value)
    assert info.value.key == "emplacements.roles.pro"


def test_role_of_ignore_un_candidat_a_utilisateur_inconnu(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements(
        {
            "~utilisateur-inexistant-xyz/v": "vault perso",
            str(dirs["foyer"]): "vault foyer",
        }
    )

    catalog = VaultCatalog.load()

    assert catalog.role_of(dirs["foyer"]) == "foyer"


def test_role_of_leve_si_la_cible_a_un_utilisateur_inconnu(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    catalog = VaultCatalog.load()

    with pytest.raises(VaultCatalogError) as info:
        catalog.role_of(Path("~utilisateur-inexistant-xyz/v"))

    assert "utilisateur-inexistant-xyz" in str(info.value)


def _lien_en_boucle(env: VaultsEnv) -> Path:
    """Crée une vraie boucle de liens ``boucle`` → ``autre`` → ``boucle``."""
    boucle = env.home / "boucle"
    autre = env.home / "autre"
    boucle.symlink_to(autre)
    autre.symlink_to(boucle)
    return boucle


def test_root_leve_si_le_chemin_du_tableau_est_une_boucle_de_liens(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    boucle = _lien_en_boucle(vaults_env)
    vaults_env.write_emplacements({str(boucle): "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert "boucle" in str(info.value)
    assert info.value.key == "emplacements.roles.pro"


def test_role_of_rend_none_si_la_cible_est_une_boucle_de_liens(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    boucle = _lien_en_boucle(vaults_env)

    assert VaultCatalog.load().role_of(boucle) is None


def test_role_of_ignore_un_candidat_en_boucle_de_liens(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    boucle = _lien_en_boucle(vaults_env)
    vaults_env.write_emplacements(
        {str(boucle): "vault perso", str(dirs["foyer"]): "vault foyer"}
    )

    catalog = VaultCatalog.load()

    assert catalog.role_of(dirs["foyer"]) == "foyer"


def test_role_of_reconnait_un_role_dont_le_dossier_n_existe_pas(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    absent = vaults_env.home / "absent"
    vaults_env.write_emplacements(
        {str(absent): "vault perso", str(dirs["foyer"]): "vault foyer"}
    )

    assert VaultCatalog.load().role_of(absent) == "perso"


def test_role_of_ignore_une_boucle_que_resolve_laisse_passer(
    vaults_env: VaultsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Python 3.13+ : ``resolve()`` rend la boucle telle quelle, ``stat`` la voit."""
    _setup(vaults_env)
    boucle = _lien_en_boucle(vaults_env)
    resolve_reel = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        if self == boucle:
            return self
        return resolve_reel(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)

    assert VaultCatalog.load().role_of(boucle) is None


def test_role_of_rend_le_premier_role_si_deux_roles_ont_le_meme_dossier(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    lien = vaults_env.home / "lien"
    lien.symlink_to(dirs["perso"])
    vaults_env.write_emplacements(
        {str(lien): "vault pro", str(dirs["perso"]): "vault perso"}
    )

    assert VaultCatalog.load().role_of(dirs["perso"]) == "perso"


@pytest.fixture
def parent_ferme() -> Iterator[Callable[[Path], None]]:
    """Retire tous les droits d'un dossier, restaurés en fin de test.

    Saute le test si les droits sont sans effet (root).
    """
    fermes: list[tuple[Path, int]] = []

    def fermer(dossier: Path) -> None:
        if os.geteuid() == 0:
            pytest.skip("root ignore les permissions POSIX")
        fermes.append((dossier, dossier.stat().st_mode))
        dossier.chmod(0)

    yield fermer
    for dossier, mode in fermes:
        dossier.chmod(stat.S_IMODE(mode))


def test_load_leve_si_le_dossier_de_la_configuration_est_inaccessible(
    vaults_env: VaultsEnv, parent_ferme: Callable[[Path], None]
) -> None:
    _setup(vaults_env)
    parent_ferme(vaults_env.config_file.parent)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert info.value.source == vaults_env.config_file
    assert isinstance(info.value.__cause__, PermissionError)


def test_root_leve_si_le_dossier_parent_du_vault_est_inaccessible(
    vaults_env: VaultsEnv, parent_ferme: Callable[[Path], None]
) -> None:
    parent = vaults_env.home / "parent"
    (parent / "vault").mkdir(parents=True)
    _setup(vaults_env)
    vaults_env.write_emplacements({str(parent / "vault"): "vault pro"})
    catalog = VaultCatalog.load()
    parent_ferme(parent)

    with pytest.raises(VaultCatalogError) as info:
        catalog.root("pro")

    assert info.value.key == "emplacements.roles.pro"
    assert info.value.source == vaults_env.home / "sources" / "emplacements.md"
    assert isinstance(info.value.__cause__, PermissionError)


def test_root_leve_si_le_chemin_du_tableau_contient_un_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({"/a\0b": "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert info.value.key == "emplacements.roles.pro"


def test_role_of_ignore_un_candidat_a_octet_nul(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements(
        {"/a\0b": "vault perso", str(dirs["foyer"]): "vault foyer"}
    )

    assert VaultCatalog.load().role_of(dirs["foyer"]) == "foyer"


def test_role_of_rend_none_si_la_cible_contient_un_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)

    assert VaultCatalog.load().role_of(Path("/a\0b")) is None


def test_role_of_nomme_l_argument_et_non_le_toml_comme_source(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    cible = Path("~utilisateur-inexistant-xyz/v")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().role_of(cible)

    assert info.value.source == cible
    assert info.value.key is None


def test_root_nomme_la_cle_du_role_si_chemin_relatif(vaults_env: VaultsEnv) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({"coffre-pro": "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert info.value.key == "emplacements.roles.pro"


def test_root_nomme_la_cle_du_role_si_dossier_introuvable(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({str(vaults_env.home / "absent"): "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert info.value.key == "emplacements.roles.pro"


def test_root_leve_si_le_chemin_du_tableau_est_tilde_puis_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_emplacements({"~\0x": "vault pro"})

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().root("pro")

    assert info.value.key == "emplacements.roles.pro"


def test_role_of_leve_si_la_cible_est_tilde_puis_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    cible = Path("~\0x")

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().role_of(cible)

    assert info.value.source == cible


def test_role_of_ignore_un_candidat_tilde_puis_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    vaults_env.write_emplacements(
        {"~\0x": "vault perso", str(dirs["foyer"]): "vault foyer"}
    )

    assert VaultCatalog.load().role_of(dirs["foyer"]) == "foyer"


def test_domaines_leve_si_le_tableau_des_conventions_a_une_seule_colonne(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_settings(
        with_value(DEFAULT_SETTINGS, "conventions.table_header", "| Vault |")
    )
    (vaults_env.home / "sources" / "conventions.md").write_text(
        "| Vault |\n|---|\n| pro |\n", encoding="utf-8"
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load().domaines("pro")

    assert "structure inattendue" in str(info.value)


def test_load_leve_si_la_source_emplacements_contient_un_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    vaults_env.write_settings(
        with_value(DEFAULT_SETTINGS, "sources.emplacements", "~/sources/a\0b.md")
    )

    with pytest.raises(VaultCatalogError):
        VaultCatalog.load()


def test_domaines_leve_si_la_source_conventions_contient_un_octet_nul(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    vaults_env.write_settings(
        with_value(DEFAULT_SETTINGS, "sources.conventions", "~/sources/a\0b.md")
    )

    with pytest.raises(VaultCatalogError):
        VaultCatalog.load().domaines("pro")


_T = TypeVar("_T")
_LIMITE_S = 5.0


def _avec_limite(appel: Callable[[], _T]) -> _T:
    """Exécute ``appel`` dans un thread ; échoue s'il dépasse la limite.

    Un FIFO lu sans précaution fige le processus : le test doit échouer au
    lieu de bloquer la CI.
    """
    sortie: list[_T] = []
    erreurs: list[BaseException] = []

    def cible() -> None:
        try:
            sortie.append(appel())
        except BaseException as exc:  # noqa: BLE001 - relayée au thread de test
            erreurs.append(exc)

    thread = threading.Thread(target=cible, daemon=True)
    thread.start()
    thread.join(_LIMITE_S)
    if thread.is_alive():
        pytest.fail(f"appel bloqué au-delà de {_LIMITE_S} s")
    if erreurs:
        raise erreurs[0]
    return sortie[0]


def test_avec_limite_relance_une_exception_brute() -> None:
    def echoue() -> int:
        raise KeyError("brute")

    with pytest.raises(KeyError):
        _avec_limite(echoue)


def test_load_leve_sans_bloquer_si_la_source_emplacements_est_un_fifo(
    vaults_env: VaultsEnv,
) -> None:
    fifo = vaults_env.home / "sources" / "emplacements.md"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)
    vaults_env.write_settings()

    with pytest.raises(VaultCatalogError) as info:
        _avec_limite(VaultCatalog.load)

    assert "régulier" in str(info.value)


def test_domaines_leve_sans_bloquer_si_la_source_conventions_est_un_fifo(
    vaults_env: VaultsEnv,
) -> None:
    _setup(vaults_env)
    fifo = vaults_env.home / "sources" / "conventions.md"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)

    with pytest.raises(VaultCatalogError) as info:
        _avec_limite(lambda: VaultCatalog.load().domaines("pro"))

    assert "régulier" in str(info.value)


_NON_REGULIER = "fichier de configuration n'est pas un fichier régulier"


def test_load_refuse_sans_bloquer_une_configuration_fifo(
    vaults_env: VaultsEnv,
) -> None:
    vaults_env.config_file.parent.mkdir(parents=True)
    os.mkfifo(vaults_env.config_file)

    with pytest.raises(VaultCatalogError) as info:
        _avec_limite(VaultCatalog.load)

    assert _NON_REGULIER in str(info.value)
    assert "copier l'exemple" not in str(info.value)
    assert info.value.source == vaults_env.config_file


def test_load_refuse_une_configuration_qui_est_un_dossier(
    vaults_env: VaultsEnv,
) -> None:
    vaults_env.config_file.mkdir(parents=True)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert _NON_REGULIER in str(info.value)
    assert "copier l'exemple" not in str(info.value)


def test_load_refuse_une_configuration_liee_a_dev_zero(
    vaults_env: VaultsEnv,
) -> None:
    vaults_env.config_file.parent.mkdir(parents=True)
    vaults_env.config_file.symlink_to("/dev/zero")

    with pytest.raises(VaultCatalogError) as info:
        _avec_limite(VaultCatalog.load)

    assert _NON_REGULIER in str(info.value)


def test_load_annonce_introuvable_si_la_configuration_est_absente(
    vaults_env: VaultsEnv,
) -> None:
    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert "copier l'exemple" in str(info.value)
    assert _NON_REGULIER not in str(info.value)


def test_load_traduit_un_toml_trop_imbrique_en_erreur_de_catalogue(
    vaults_env: VaultsEnv,
) -> None:
    vaults_env.config_file.parent.mkdir(parents=True)
    profondeur = 1000
    vaults_env.config_file.write_text(
        "a = " + "[" * profondeur + "]" * profondeur + "\n", encoding="utf-8"
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert "TOML invalide" in str(info.value)
    assert isinstance(info.value.__cause__, RecursionError)


def test_load_refuse_sans_ouvrir_un_chemin_non_regulier_present(
    vaults_env: VaultsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # La présélection par stat refuse avant tout os.open (périphérique).
    vaults_env.write_settings(
        with_value(DEFAULT_SETTINGS, "sources.emplacements", "/dev/null")
    )
    ouvertures: list[str] = []
    reel = os.open

    def espion(path: str | Path, flags: int, mode: int = 0o777) -> int:
        ouvertures.append(str(path))
        return reel(path, flags, mode)

    monkeypatch.setattr(os, "open", espion)

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert "régulier" in str(info.value)
    assert "/dev/null" not in ouvertures


def test_load_refuse_si_fstat_decouvre_un_fichier_non_regulier(
    vaults_env: VaultsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Course : stat voit un fichier régulier, l'ouverture tombe sur un FIFO.
    vaults_env.write_settings()
    fifo = vaults_env.home / "sources" / "emplacements.md"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)
    regulier = vaults_env.config_file.stat()
    reel = os.stat

    def faux_stat(path: str | Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if Path(path) == fifo:
            return regulier
        return reel(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", faux_stat)

    with pytest.raises(VaultCatalogError) as info:
        _avec_limite(VaultCatalog.load)

    assert "régulier" in str(info.value)


def test_load_suit_un_lien_symbolique_vers_la_source(
    vaults_env: VaultsEnv,
) -> None:
    dirs = _setup(vaults_env)
    cible = vaults_env.home / "sources" / "emplacements.md"
    reelle = vaults_env.home / "reelle.md"
    cible.rename(reelle)
    cible.symlink_to(reelle)

    catalog = VaultCatalog.load()

    assert catalog.roles == ("perso", "pro", "foyer")
    assert catalog.root("pro") == dirs["pro"].resolve()


def test_load_refuse_dev_null_comme_source(vaults_env: VaultsEnv) -> None:
    vaults_env.write_settings(
        with_value(DEFAULT_SETTINGS, "sources.emplacements", "/dev/null")
    )

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert "régulier" in str(info.value)


def test_load_accepte_une_source_utf8_avec_bom(vaults_env: VaultsEnv) -> None:
    dirs = _setup(vaults_env)
    source = vaults_env.home / "sources" / "emplacements.md"
    source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes())

    assert VaultCatalog.load().root("pro") == dirs["pro"].resolve()
