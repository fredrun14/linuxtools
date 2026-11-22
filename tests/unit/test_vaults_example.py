"""Tests de l'exemple de configuration empaqueté de ``linuxtools.vaults``."""

import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import linuxtools
from linuxtools.vaults import catalog
from linuxtools.vaults.catalog import VaultCatalog, _load_settings
from tests.unit.vaults_helpers import VaultsEnv, conventions_md, emplacements_md


def _example_path() -> Path:
    """Rend le chemin de l'exemple empaqueté."""
    return Path(str(files("linuxtools.vaults").joinpath("vaults.example.toml")))


def _example_data() -> dict[str, Any]:
    """Rend le contenu parsé de l'exemple empaqueté."""
    return tomllib.loads(_example_path().read_text(encoding="utf-8"))


def test_exemple_present_dans_le_paquet_installe() -> None:
    assert files("linuxtools.vaults").joinpath("vaults.example.toml").is_file()


def test_exemple_empaquete_se_charge(vaults_env: VaultsEnv) -> None:
    data = _example_data()
    vaults_env.config_file.parent.mkdir(parents=True)
    vaults_env.config_file.write_text(
        _example_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    roles: dict[str, str] = data["emplacements"]["roles"]
    rows = {f"~/dossier-{role}/": label for role, label in roles.items()}
    contenus = {
        "emplacements": emplacements_md(rows).replace(
            "## Emplacements", data["emplacements"]["section"]
        ),
        "conventions": conventions_md({role: ["a"] for role in roles}),
    }
    for key, content in contenus.items():
        source = Path(data["sources"][key]).expanduser()
        target = vaults_env.home / source.relative_to(Path.home())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    result = VaultCatalog.load()

    assert result.roles == tuple(roles)


def test_exemple_contient_toutes_les_cles_lues(vaults_env: VaultsEnv) -> None:
    data = _example_data()

    settings = _load_settings(_example_path())

    assert settings.roles == data["emplacements"]["roles"]
    assert settings.section == data["emplacements"]["section"]
    assert settings.table_header == data["conventions"]["table_header"]


def test_linuxtools_exporte_vault_catalog_et_son_erreur() -> None:
    assert linuxtools.VaultCatalog is catalog.VaultCatalog
    assert linuxtools.VaultCatalogError is catalog.VaultCatalogError
    assert "VaultCatalog" in linuxtools.__all__
    assert "VaultCatalogError" in linuxtools.__all__
