"""Tests du chargement et de la validation du TOML des vaults (T2)."""

import os
from pathlib import Path

import pytest

from linuxtools.errors.exceptions import ConfigurationError
from linuxtools.vaults.catalog import (
    VaultCatalog,
    VaultCatalogError,
    _config_file,
    _load_settings,
)
from tests.unit.vaults_helpers import (
    DEFAULT_SETTINGS,
    VaultsEnv,
    render_vaults_toml,
    with_value,
    without_key,
)

CLES = [
    "sources.emplacements",
    "sources.conventions",
    "emplacements.section",
    "emplacements.roles",
    "conventions.table_header",
]


def test_load_leve_si_toml_absent_et_nomme_chemin_xdg_et_exemple(
    vaults_env: VaultsEnv,
) -> None:
    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert str(vaults_env.config_file) in str(info.value)
    assert "vaults.example.toml" in str(info.value)
    assert info.value.source == vaults_env.config_file
    assert info.value.key is None


def test_load_lit_le_toml_sous_xdg_config_home(vaults_env: VaultsEnv) -> None:
    vaults_env.write_settings()
    vaults_env.write_emplacements({})

    catalog = VaultCatalog.load()

    assert catalog.roles == ("perso", "pro", "foyer")
    # Chemin attendu écrit en dur : le test porte sur le code, pas sur la fixture.
    assert _config_file() == vaults_env.home.parent / "config/vault-tools/vaults.toml"


def test_load_ne_cascade_pas_vers_xdg_config_dirs(
    vaults_env: VaultsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    systeme = vaults_env.home.parent / "etc-xdg"
    (systeme / "vault-tools").mkdir(parents=True)
    (systeme / "vault-tools" / "vaults.toml").write_text(
        render_vaults_toml(DEFAULT_SETTINGS), encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(systeme))

    with pytest.raises(VaultCatalogError) as info:
        VaultCatalog.load()

    assert info.value.source == vaults_env.config_file


def test_load_lit_les_chemins_sources_du_toml(vaults_env: VaultsEnv) -> None:
    vaults_env.write_settings()

    settings = _load_settings(vaults_env.config_file)

    assert settings.emplacements_file == vaults_env.home / "sources/emplacements.md"
    assert settings.conventions_file == vaults_env.home / "sources/conventions.md"
    assert settings.section == "## Emplacements"
    assert settings.table_header == "| Vault | Valeurs |"
    assert list(settings.roles.items()) == [
        ("perso", "vault perso"),
        ("pro", "vault pro"),
        ("foyer", "vault foyer"),
    ]


@pytest.mark.parametrize("cle", CLES)
def test_load_leve_si_cle_absente(vaults_env: VaultsEnv, cle: str) -> None:
    vaults_env.write_settings(without_key(DEFAULT_SETTINGS, cle))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == cle
    assert info.value.source == vaults_env.config_file
    assert cle in str(info.value)
    assert str(vaults_env.config_file) in str(info.value)


@pytest.mark.parametrize("table", ["sources", "emplacements", "conventions"])
def test_load_leve_si_table_absente(vaults_env: VaultsEnv, table: str) -> None:
    vaults_env.write_settings(without_key(DEFAULT_SETTINGS, table))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key is not None
    assert info.value.key.startswith(table + ".")


@pytest.mark.parametrize(
    ("cle", "valeur"),
    [
        ("sources.emplacements", ""),
        ("sources.conventions", "  "),
        ("emplacements.section", ""),
        ("conventions.table_header", "  "),
        ("emplacements.roles", {}),
    ],
)
def test_load_leve_si_cle_vide(vaults_env: VaultsEnv, cle: str, valeur: object) -> None:
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, cle, valeur))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == cle


@pytest.mark.parametrize("cle", CLES)
@pytest.mark.parametrize("valeur", [3, ["a"]])
def test_load_leve_si_cle_de_mauvais_type(
    vaults_env: VaultsEnv, cle: str, valeur: object
) -> None:
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, cle, valeur))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == cle


def test_load_leve_si_table_a_la_place_d_une_cle_chaine(
    vaults_env: VaultsEnv,
) -> None:
    vaults_env.write_settings(
        with_value(DEFAULT_SETTINGS, "emplacements.section", {"a": "b"})
    )

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "emplacements.section"


def test_load_leve_si_table_intermediaire_n_est_pas_une_table(
    vaults_env: VaultsEnv,
) -> None:
    contenu = render_vaults_toml(without_key(DEFAULT_SETTINGS, "sources"))
    vaults_env.config_file.parent.mkdir(parents=True)
    vaults_env.config_file.write_text('sources = "x"\n' + contenu, encoding="utf-8")

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "sources.emplacements"


def test_load_leve_si_libelle_de_role_vide(vaults_env: VaultsEnv) -> None:
    roles = {"perso": "vault perso", "pro": " "}
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, "emplacements.roles", roles))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "emplacements.roles.pro"


def test_load_leve_si_libelle_de_role_n_est_pas_une_chaine(
    vaults_env: VaultsEnv,
) -> None:
    roles = {"perso": 3}
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, "emplacements.roles", roles))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "emplacements.roles.perso"


def test_load_leve_si_nom_de_role_vide(vaults_env: VaultsEnv) -> None:
    roles = {" ": "vault perso"}
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, "emplacements.roles", roles))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "emplacements.roles"


def test_load_leve_si_libelle_de_role_en_double(vaults_env: VaultsEnv) -> None:
    roles = {"perso": "meme libelle", "pro": "meme libelle"}
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, "emplacements.roles", roles))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "emplacements.roles"
    assert "double" in str(info.value)


@pytest.mark.parametrize("cle", ["sources.emplacements", "sources.conventions"])
def test_load_refuse_un_chemin_source_relatif(vaults_env: VaultsEnv, cle: str) -> None:
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, cle, "dossier/relatif.md"))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == cle
    assert "relatif" in str(info.value)


def test_load_leve_si_toml_invalide(vaults_env: VaultsEnv) -> None:
    vaults_env.config_file.parent.mkdir(parents=True)
    vaults_env.config_file.write_text("[sources\nx = =\n", encoding="utf-8")

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert "TOML invalide" in str(info.value)
    assert info.value.__cause__ is not None


@pytest.mark.skipif(os.geteuid() == 0, reason="root lit tout fichier")
def test_load_leve_si_toml_illisible(vaults_env: VaultsEnv) -> None:
    vaults_env.write_settings()
    vaults_env.config_file.chmod(0o000)

    try:
        with pytest.raises(VaultCatalogError) as info:
            _load_settings(vaults_env.config_file)
    finally:
        vaults_env.config_file.chmod(0o600)

    assert "illisible" in str(info.value)
    assert isinstance(info.value.__cause__, OSError)


def test_vault_catalog_error_est_une_configuration_error() -> None:
    erreur = VaultCatalogError("détail", source=Path("/x/y.toml"), key="a.b")

    assert isinstance(erreur, ConfigurationError)
    assert str(erreur) == "/x/y.toml — clé « a.b » : détail"
    assert str(VaultCatalogError("d", source=Path("/x"))) == "/x : d"


def test_load_leve_si_toml_non_utf8(vaults_env: VaultsEnv) -> None:
    vaults_env.config_file.parent.mkdir(parents=True)
    vaults_env.config_file.write_bytes(b'[sources]\nx = "\xff\xfe"\n')

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert "illisible" in str(info.value)
    assert info.value.source == vaults_env.config_file
    assert isinstance(info.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize("cle", ["sources.emplacements", "sources.conventions"])
def test_load_leve_si_chemin_source_a_utilisateur_inconnu(
    vaults_env: VaultsEnv, cle: str
) -> None:
    valeur = "~utilisateur-inexistant-xyz/x.md"
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, cle, valeur))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == cle
    assert info.value.source == vaults_env.config_file


@pytest.mark.parametrize("libelle", [" vault perso", "vault perso ", "\tvault perso"])
def test_load_leve_si_libelle_de_role_a_des_espaces_de_bord(
    vaults_env: VaultsEnv, libelle: str
) -> None:
    roles = {"perso": libelle}
    vaults_env.write_settings(with_value(DEFAULT_SETTINGS, "emplacements.roles", roles))

    with pytest.raises(VaultCatalogError) as info:
        _load_settings(vaults_env.config_file)

    assert info.value.key == "emplacements.roles.perso"
    assert "espaces" in str(info.value)
