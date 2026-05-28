"""Tests unitaires pour ConfTomlExporter."""

from pathlib import Path

import pytest

from linux_python_utils.dotconf import ConfTomlExporter
from linux_python_utils.dotconf.toml_spec_loader import TomlSpecLoader


@pytest.fixture
def exporter() -> ConfTomlExporter:
    """Fixture fournissant une instance de ConfTomlExporter."""
    return ConfTomlExporter()


class TestExport:
    """Tests pour ConfTomlExporter.export."""

    def test_export_flat_file_produces_content_blocks(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / ".zshrc"
        source.write_text(
            "export PATH=/usr/local/bin:$PATH\nalias ll='ls -la'\n",
            encoding="utf-8",
        )
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert
        content = dest.read_text(encoding="utf-8")
        assert "[[target.content]]" in content
        assert content.count("[[target.content]]") == 2

    def test_export_flat_file_no_section_field(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / ".vimrc"
        source.write_text("set number\nset tabstop=4\n", encoding="utf-8")
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert — fichier plat : pas de champ section
        content = dest.read_text(encoding="utf-8")
        assert "section =" not in content

    def test_export_comment_attached_to_next_block(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / ".zshrc"
        source.write_text("# aliases\nalias ll='ls -la'\n", encoding="utf-8")
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert
        content = dest.read_text(encoding="utf-8")
        assert 'comment = "# aliases"' in content
        assert "alias ll=" in content

    def test_export_empty_lines_ignored(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / ".zshrc"
        source.write_text(
            "export A=1\n\n\nexport B=2\n", encoding="utf-8"
        )
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert — uniquement 2 blocs de contenu
        content = dest.read_text(encoding="utf-8")
        assert content.count("[[target.content]]") == 2

    def test_export_orphan_comment_ignored(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange — commentaire en fin de fichier sans contenu suivant
        source = tmp_path / ".zshrc"
        source.write_text(
            "export A=1\n# commentaire orphelin\n", encoding="utf-8"
        )
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert — 1 seul bloc, le commentaire orphelin est ignoré
        content = dest.read_text(encoding="utf-8")
        assert content.count("[[target.content]]") == 1

    def test_export_ini_file_section_field_present(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / "dnf.conf"
        source.write_text(
            "[main]\nkeepcache=1\nmax_parallel_downloads=10\n",
            encoding="utf-8",
        )
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert
        content = dest.read_text(encoding="utf-8")
        assert 'section = "main"' in content
        assert content.count('section = "main"') == 2

    def test_export_ini_section_header_not_in_content(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / "dnf.conf"
        source.write_text("[main]\nkeepcache=1\n", encoding="utf-8")
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert — [main] ne doit pas apparaître comme valeur de content
        content = dest.read_text(encoding="utf-8")
        assert 'content = "[main]"' not in content

    def test_export_special_chars_escaped(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange — contenu avec backslash et guillemet double
        source = tmp_path / ".vimrc"
        source.write_text('set backspace=indent,eol,start\nlet g:x="val"\n',
                           encoding="utf-8")
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert — guillemets échappés dans le TOML
        content = dest.read_text(encoding="utf-8")
        assert '\\"val\\"' in content

    def test_export_file_path_is_absolute(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / "config.conf"
        source.write_text("key=value\n", encoding="utf-8")
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        # Assert — file_path dans le TOML commence par /
        content = dest.read_text(encoding="utf-8")
        assert f'file_path = "{source.resolve()}"' in content

    def test_export_source_not_found_raises(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / "inexistant.conf"
        dest = tmp_path / "out.toml"
        # Act / Assert
        with pytest.raises(FileNotFoundError):
            exporter.export(source, dest)

    def test_export_creates_dest_parent_dirs(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange — dest dans un sous-répertoire inexistant
        source = tmp_path / "config.conf"
        source.write_text("key=value\n", encoding="utf-8")
        dest = tmp_path / "subdir" / "nested" / "out.toml"
        # Act — ne doit pas lever d'exception
        exporter.export(source, dest)
        # Assert
        assert dest.exists()

    def test_round_trip_with_toml_spec_loader(
        self, exporter: ConfTomlExporter, tmp_path: Path
    ) -> None:
        # Arrange
        source = tmp_path / "dnf.conf"
        source.write_text(
            "[main]\n# keep downloaded packages\nkeepcache=1\n"
            "max_parallel_downloads=10\n",
            encoding="utf-8",
        )
        dest = tmp_path / "out.toml"
        # Act
        exporter.export(source, dest)
        spec = TomlSpecLoader().load(dest)
        # Assert
        assert spec.file_path == source.resolve()
        assert len(spec.blocks) == 2
        assert spec.blocks[0].section == "main"
        assert spec.blocks[0].comment == "# keep downloaded packages"
        assert spec.blocks[0].content == "keepcache=1"


class TestIsIni:
    """Tests pour ConfTomlExporter._is_ini."""

    def test_returns_true_for_ini_content(
        self, exporter: ConfTomlExporter
    ) -> None:
        assert exporter._is_ini(["[main]", "key=value"]) is True

    def test_returns_false_for_flat_content(
        self, exporter: ConfTomlExporter
    ) -> None:
        assert exporter._is_ini(["export PATH=/usr/bin", "alias ll=ls"]) is False

    def test_returns_false_for_empty_lines(
        self, exporter: ConfTomlExporter
    ) -> None:
        assert exporter._is_ini(["", "  "]) is False


class TestTomlEscape:
    """Tests pour ConfTomlExporter._toml_escape."""

    def test_escapes_backslash(self) -> None:
        assert ConfTomlExporter._toml_escape("a\\b") == "a\\\\b"

    def test_escapes_double_quote(self) -> None:
        assert ConfTomlExporter._toml_escape('say "hi"') == 'say \\"hi\\"'

    def test_escapes_newline(self) -> None:
        assert ConfTomlExporter._toml_escape("a\nb") == "a\\nb"

    def test_backslash_escaped_before_quote(self) -> None:
        # \\" doit devenir \\\\" et non \\"
        assert ConfTomlExporter._toml_escape('\\"') == '\\\\\\"'

    def test_plain_string_unchanged(self) -> None:
        assert ConfTomlExporter._toml_escape("keepcache=1") == "keepcache=1"
