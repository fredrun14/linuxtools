"""Tests unitaires pour XdgAppConfig."""

# stdlib
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch, PropertyMock

# third-party
import pytest

# local
from linuxtools.config.xdg import XdgAppConfig

_APP = "test-app"
_TEMPLATE = "[log]\nlevel = 'INFO'\n"


@pytest.fixture
def xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[XdgAppConfig]:
    """XdgAppConfig hermétique : config_dir et XDG_CONFIG_DIRS isolés."""
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "shared"))
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

    def test_find_config_file_retourne_none_si_aucun_niveau(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """find_config_file retourne None si aucun niveau n'a le fichier."""
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

    def test_xdg_config_dirs_suit_xdg_config_dirs(
        self,
        xdg: XdgAppConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """xdg_config_dirs liste un dossier par entrée de la variable."""
        a, b = tmp_path / "a", tmp_path / "b"
        monkeypatch.setenv("XDG_CONFIG_DIRS", f"{a}{os.pathsep}{b}")

        assert xdg.xdg_config_dirs == [a / _APP, b / _APP]

    def test_xdg_config_dirs_defaut_etc_xdg(
        self, xdg: XdgAppConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sans XDG_CONFIG_DIRS, le défaut XDG /etc/xdg s'applique."""
        monkeypatch.delenv("XDG_CONFIG_DIRS", raising=False)

        assert xdg.xdg_config_dirs == [Path("/etc/xdg") / _APP]

    def test_find_config_file_retourne_xdg_config_dirs_si_user_et_etc_absents(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """find_config_file trouve le fichier au 3e niveau."""
        shared = tmp_path / "shared" / _APP
        shared.mkdir(parents=True)
        shared_file = shared / "global.toml"
        shared_file.write_text(_TEMPLATE, encoding="utf-8")

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=tmp_path / "nowhere"
        ):
            result = xdg.find_config_file()

        assert result == shared_file

    def test_find_config_file_etc_prioritaire_sur_xdg_config_dirs(
        self, xdg: XdgAppConfig, tmp_path: Path
    ) -> None:
        """/etc/<app> est lu avant XDG_CONFIG_DIRS."""
        shared = tmp_path / "shared" / _APP
        shared.mkdir(parents=True)
        (shared / "global.toml").write_text("shared", encoding="utf-8")
        system_dir = tmp_path / "sys"
        system_dir.mkdir()
        system_file = system_dir / "global.toml"
        system_file.write_text("sys", encoding="utf-8")

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=system_dir
        ):
            result = xdg.find_config_file()

        assert result == system_file

    def test_find_config_file_premier_dossier_xdg_config_dirs_prioritaire(
        self,
        xdg: XdgAppConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """L'ordre de XDG_CONFIG_DIRS est respecté."""
        first, second = tmp_path / "a", tmp_path / "b"
        for base in (first, second):
            (base / _APP).mkdir(parents=True)
            (base / _APP / "global.toml").write_text(
                base.name, encoding="utf-8"
            )
        monkeypatch.setenv(
            "XDG_CONFIG_DIRS", f"{first}{os.pathsep}{second}"
        )

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=tmp_path / "nowhere"
        ):
            result = xdg.find_config_file()

        assert result == first / _APP / "global.toml"

    def test_xdg_config_dirs_ignore_entrees_relatives_ancienne_version(
        self, xdg: XdgAppConfig
    ) -> None:
        """Une entrée relative (ancienne platformdirs) est écartée."""
        with patch(
            "linuxtools.config.xdg.site_config_dir",
            return_value="app:rel/app:/opt/c/app",
        ):
            assert xdg.xdg_config_dirs == [Path("/opt/c/app")]

    def test_xdg_config_dirs_ignore_entrees_vides_ancienne_version(
        self, xdg: XdgAppConfig
    ) -> None:
        """Une entrée vide (ancienne platformdirs) est écartée."""
        with patch(
            "linuxtools.config.xdg.site_config_dir",
            return_value=f"/opt/a/app{os.pathsep}{os.pathsep}/opt/b/app",
        ):
            assert xdg.xdg_config_dirs == [
                Path("/opt/a/app"),
                Path("/opt/b/app"),
            ]

    def test_xdg_config_dirs_variable_vide_defaut_etc_xdg(
        self, xdg: XdgAppConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Une variable vide retombe sur le défaut /etc/xdg."""
        monkeypatch.setenv("XDG_CONFIG_DIRS", "")

        assert xdg.xdg_config_dirs == [Path("/etc/xdg") / _APP]

    def test_xdg_config_dirs_variable_relative_defaut_etc_xdg(
        self, xdg: XdgAppConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Une variable entièrement relative retombe sur /etc/xdg."""
        monkeypatch.setenv(
            "XDG_CONFIG_DIRS", f"rel/a{os.pathsep}rel/b"
        )

        assert xdg.xdg_config_dirs == [Path("/etc/xdg") / _APP]

    def test_find_config_file_second_dossier_xdg_config_dirs_si_premier_absent(
        self,
        xdg: XdgAppConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un premier dossier sans fichier n'empêche pas le second."""
        first, second = tmp_path / "a", tmp_path / "b"
        (first / _APP).mkdir(parents=True)
        (second / _APP).mkdir(parents=True)
        (second / _APP / "global.toml").write_text(
            "second", encoding="utf-8"
        )
        monkeypatch.setenv(
            "XDG_CONFIG_DIRS", f"{first}{os.pathsep}{second}"
        )

        with patch.object(
            type(xdg), "system_config_dir", new_callable=PropertyMock,
            return_value=tmp_path / "nowhere"
        ):
            result = xdg.find_config_file()

        assert result == second / _APP / "global.toml"
