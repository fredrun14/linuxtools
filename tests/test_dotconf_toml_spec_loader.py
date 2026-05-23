"""Tests unitaires pour dotconf.toml_spec_loader (TomlSpecLoader)."""

import os
from pathlib import Path

import pytest

from linux_python_utils.dotconf.toml_spec_loader import TomlSpecLoader


@pytest.fixture
def loader() -> TomlSpecLoader:
    """Fixture fournissant une instance de TomlSpecLoader."""
    return TomlSpecLoader()


@pytest.fixture
def flat_toml(tmp_path: Path) -> Path:
    """TOML de spec pour un fichier plat (sans section INI)."""
    f = tmp_path / "flat.toml"
    f.write_text(
        '[target]\n'
        'file_path = "/tmp/test-flat.conf"\n'
        '\n'
        '[[target.content]]\n'
        'comment = "# Quality"\n'
        'content = \'-f best\'\n'
        '\n'
        '[[target.content]]\n'
        'content = "--no-playlist"\n',
        encoding="utf-8",
    )
    return f


@pytest.fixture
def ini_toml(tmp_path: Path) -> Path:
    """TOML de spec pour un fichier INI avec section."""
    f = tmp_path / "ini.toml"
    f.write_text(
        '[target]\n'
        'file_path = "/tmp/test-ini.conf"\n'
        '\n'
        '[[target.content]]\n'
        'section = "main"\n'
        'comment = "# Fast"\n'
        'content = "fastestmirror = True"\n',
        encoding="utf-8",
    )
    return f


class TestTomlSpecLoaderLoad:
    """Tests pour TomlSpecLoader.load."""

    def test_load_flat_file_spec_returns_config_spec(
        self, loader: TomlSpecLoader, flat_toml: Path
    ) -> None:
        spec = loader.load(flat_toml)

        assert spec.file_path == Path("/tmp/test-flat.conf")
        assert len(spec.blocks) == 2
        assert spec.blocks[0].content == "-f best"
        assert spec.blocks[0].comment == "# Quality"
        assert spec.blocks[0].section is None
        assert spec.blocks[1].content == "--no-playlist"

    def test_load_ini_file_spec_returns_blocks_with_section(
        self, loader: TomlSpecLoader, ini_toml: Path
    ) -> None:
        spec = loader.load(ini_toml)

        assert len(spec.blocks) == 1
        assert spec.blocks[0].section == "main"
        assert spec.blocks[0].content == "fastestmirror = True"
        assert spec.blocks[0].comment == "# Fast"

    def test_load_resolves_tilde_in_file_path(
        self, loader: TomlSpecLoader, tmp_path: Path
    ) -> None:
        toml = tmp_path / "tilde.toml"
        toml.write_text(
            '[target]\nfile_path = "~/.config/app/config"\n'
            '[[target.content]]\ncontent = "opt = 1"\n',
            encoding="utf-8",
        )

        spec = loader.load(toml)

        home = Path.home()
        assert spec.file_path == home / ".config" / "app" / "config"

    def test_load_resolves_env_var_in_file_path(
        self, loader: TomlSpecLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MYAPP_HOME", str(tmp_path))
        toml = tmp_path / "env.toml"
        toml.write_text(
            '[target]\nfile_path = "$MYAPP_HOME/config"\n'
            '[[target.content]]\ncontent = "opt = 1"\n',
            encoding="utf-8",
        )

        spec = loader.load(toml)

        assert spec.file_path == (tmp_path / "config").resolve()

    def test_load_raises_file_not_found_if_toml_missing(
        self, loader: TomlSpecLoader, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.toml"

        with pytest.raises(FileNotFoundError):
            loader.load(missing)

    def test_load_raises_key_error_if_target_missing(
        self, loader: TomlSpecLoader, tmp_path: Path
    ) -> None:
        toml = tmp_path / "no_target.toml"
        toml.write_text('[other]\nkey = "value"\n', encoding="utf-8")

        with pytest.raises(KeyError):
            loader.load(toml)

    def test_load_raises_key_error_if_file_path_missing(
        self, loader: TomlSpecLoader, tmp_path: Path
    ) -> None:
        toml = tmp_path / "no_filepath.toml"
        toml.write_text(
            '[target]\n[[target.content]]\ncontent = "x"\n',
            encoding="utf-8",
        )

        with pytest.raises(KeyError):
            loader.load(toml)

    def test_load_raises_value_error_if_content_missing(
        self, loader: TomlSpecLoader, tmp_path: Path
    ) -> None:
        toml = tmp_path / "no_content.toml"
        toml.write_text(
            '[target]\nfile_path = "/tmp/x"\n'
            '[[target.content]]\ncomment = "# oops"\n',
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Bloc #1 sans clé 'content'"):
            loader.load(toml)

    def test_load_returns_empty_blocks_when_no_content(
        self, loader: TomlSpecLoader, tmp_path: Path
    ) -> None:
        toml = tmp_path / "empty.toml"
        toml.write_text('[target]\nfile_path = "/tmp/x"\n', encoding="utf-8")

        spec = loader.load(toml)

        assert spec.blocks == []
