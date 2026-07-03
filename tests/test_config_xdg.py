"""Tests unitaires pour XdgAppConfig."""

# stdlib
from pathlib import Path
from unittest.mock import patch, PropertyMock

# third-party
import pytest

# local
from linuxtools.config.xdg import XdgAppConfig

_APP = "test-app"
_TEMPLATE = "[log]\nlevel = 'INFO'\n"


@pytest.fixture
def xdg(tmp_path: Path) -> XdgAppConfig:
    """XdgAppConfig avec config_dir redirigé vers tmp_path."""
    with patch(
        "linuxtools.config.xdg.user_config_path",
        return_value=tmp_path / _APP,
    ):
        yield XdgAppConfig(_APP)


class TestXdgAppConfig:
    def test_config_dir_contient_app_name(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """config_dir se termine par le nom de l'app."""
        assert xdg.config_dir == tmp_path / _APP

    def test_init_config_file_cree_fichier(
        self, xdg: XdgAppConfig
    ) -> None:
        """init_config_file crée le fichier avec le template."""
        result = xdg.init_config_file(_TEMPLATE)

        assert result.exists()

    def test_init_config_file_cree_repertoire_parent(
        self, xdg: XdgAppConfig
    ) -> None:
        """init_config_file crée ~/.config/<app>/ si absent."""
        assert not xdg.config_dir.exists()

        xdg.init_config_file(_TEMPLATE)

        assert xdg.config_dir.is_dir()

    def test_init_config_file_leve_file_exists_error(
        self, xdg: XdgAppConfig
    ) -> None:
        """Lève FileExistsError si fichier existe et force=False."""
        xdg.init_config_file(_TEMPLATE)

        with pytest.raises(FileExistsError):
            xdg.init_config_file(_TEMPLATE)

    def test_init_config_file_force_ecrase(
        self, xdg: XdgAppConfig
    ) -> None:
        """force=True écrase le fichier sans erreur."""
        xdg.init_config_file("[log]\nlevel = 'DEBUG'\n")

        result = xdg.init_config_file(_TEMPLATE, force=True)

        assert result.read_text(encoding="utf-8") == _TEMPLATE

    def test_init_config_file_nom_personnalise(
        self, xdg: XdgAppConfig
    ) -> None:
        """filename personnalisé crée le bon fichier."""
        result = xdg.init_config_file(_TEMPLATE, filename="custom.toml")

        assert result.name == "custom.toml"
        assert result.exists()

    def test_ensure_subdir_cree_repertoire(
        self, xdg: XdgAppConfig
    ) -> None:
        """ensure_subdir crée le sous-répertoire et retourne son chemin."""
        result = xdg.ensure_subdir("configs")

        assert result.is_dir()
        assert result == xdg.config_dir / "configs"

    def test_ensure_subdir_idempotent(
        self, xdg: XdgAppConfig
    ) -> None:
        """Appels répétés sur le même nom n'échouent pas."""
        xdg.ensure_subdir("configs")
        xdg.ensure_subdir("configs")

        assert (xdg.config_dir / "configs").is_dir()

    def test_contenu_fichier_egal_template(
        self, xdg: XdgAppConfig
    ) -> None:
        """Le contenu écrit correspond exactement au template."""
        result = xdg.init_config_file(_TEMPLATE)

        assert result.read_text(encoding="utf-8") == _TEMPLATE

    def test_system_config_dir_contient_etc_et_app_name(
        self, xdg: XdgAppConfig
    ) -> None:
        """system_config_dir vaut /etc/<app_name>/."""
        assert xdg.system_config_dir == Path("/etc") / _APP

    def test_find_config_file_retourne_user_path_si_present(
        self, xdg: XdgAppConfig
    ) -> None:
        """find_config_file retourne le chemin user si le fichier existe."""
        xdg.init_config_file(_TEMPLATE)

        result = xdg.find_config_file()

        assert result == xdg.config_dir / "global.toml"

    def test_find_config_file_retourne_system_path_si_user_absent(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """find_config_file retourne /etc/…/file si ~/.config/… est absent."""
        system_dir = tmp_path / "sys"
        system_dir.mkdir()
        system_file = system_dir / "global.toml"
        system_file.write_text(_TEMPLATE, encoding="utf-8")

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=system_dir
        ):
            result = xdg.find_config_file()

        assert result == system_file

    def test_find_config_file_retourne_none_si_les_deux_absents(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """find_config_file retourne None si aucun fichier n'existe."""
        absent = tmp_path / "nowhere"

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=absent
        ):
            result = xdg.find_config_file()

        assert result is None

    def test_find_config_file_user_prioritaire_sur_systeme(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """find_config_file retourne le chemin user même si /etc/… existe."""
        xdg.init_config_file(_TEMPLATE)
        system_dir = tmp_path / "sys"
        system_dir.mkdir()
        (system_dir / "global.toml").write_text("other", encoding="utf-8")

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=system_dir
        ):
            result = xdg.find_config_file()

        assert result == xdg.config_dir / "global.toml"

    def test_find_config_file_filename_personnalise(
        self, xdg: XdgAppConfig
    ) -> None:
        """find_config_file cherche le bon filename personnalisé."""
        xdg.init_config_file(_TEMPLATE, filename="custom.toml")

        result = xdg.find_config_file("custom.toml")

        assert result is not None
        assert result.name == "custom.toml"
