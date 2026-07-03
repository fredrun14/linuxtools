"""Tests unitaires pour SectionAwareEditor."""

from pathlib import Path

from linuxtools.dotconf import SectionAwareEditor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_editor(tmp_path: Path, filename: str = "config") -> SectionAwareEditor:
    """Retourne un éditeur pointant vers tmp_path/filename."""
    return SectionAwareEditor(tmp_path / filename)


def write_file(path: Path, content: str) -> None:
    """Écrit le contenu dans le fichier (crée les parents si nécessaire)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# TestIsBlockPresent
# ---------------------------------------------------------------------------


class TestIsBlockPresent:
    """Vérifie la détection de blocs actifs."""

    def test_retourne_false_si_fichier_absent(self, tmp_path: Path) -> None:
        # Arrange
        editor = make_editor(tmp_path, "absent.conf")
        # Act & Assert
        assert editor.is_block_present("key = value") is False

    def test_retourne_true_si_bloc_actif_sans_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n--write-subs\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_present("--rm-cache-dir") is True

    def test_retourne_true_si_bloc_actif_dans_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        write_file(path, "[main]\nfastestmirror = true\nmax_parallel_downloads = 10\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_present("fastestmirror = true", section="main") is True

    def test_retourne_false_si_bloc_absent(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_present("--write-subs") is False

    def test_retourne_false_si_bloc_commente(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "# --write-subs\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_present("--write-subs") is False

    def test_retourne_false_si_section_absente(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        write_file(path, "[other]\nkey = val\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_present("key = val", section="main") is False


# ---------------------------------------------------------------------------
# TestIsBlockCommented
# ---------------------------------------------------------------------------


class TestIsBlockCommented:
    """Vérifie la détection de blocs commentés."""

    def test_retourne_true_si_bloc_commente_sans_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "# --write-subs\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_commented("--write-subs") is True

    def test_retourne_true_si_bloc_commente_dans_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        write_file(path, "[main]\n# fastestmirror = true\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_commented("fastestmirror = true", section="main") is True

    def test_retourne_false_si_bloc_actif(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--write-subs\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_commented("--write-subs") is False

    def test_retourne_false_si_fichier_absent(self, tmp_path: Path) -> None:
        # Arrange
        editor = make_editor(tmp_path, "absent.conf")
        # Act & Assert
        assert editor.is_block_commented("--write-subs") is False

    def test_prefixe_point_virgule_reconnu(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "; fastestmirror = true\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.is_block_commented("fastestmirror = true") is True


# ---------------------------------------------------------------------------
# TestEnsureBlock
# ---------------------------------------------------------------------------


class TestEnsureBlock:
    """Vérifie les 5 comportements de ensure_block()."""

    def test_retourne_false_si_bloc_deja_present(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("--rm-cache-dir")
        # Assert
        assert result is False
        assert path.read_text() == "--rm-cache-dir\n"

    def test_cree_fichier_si_absent_sans_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "subdir" / "config"
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("--write-subs")
        # Assert
        assert result is True
        assert path.exists()
        assert "--write-subs" in path.read_text()

    def test_cree_fichier_si_absent_avec_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("fastestmirror = true", section="main")
        # Assert
        assert result is True
        content = path.read_text()
        assert "[main]" in content
        assert "fastestmirror = true" in content

    def test_decommente_bloc_commente(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n# --write-subs\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("--write-subs")
        # Assert
        assert result is True
        content = path.read_text()
        assert "--write-subs" in content
        assert "# --write-subs" not in content

    def test_insere_dans_section_existante(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        write_file(path, "[main]\nkeepcache = false\n\n[updates]\nfoo = bar\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("fastestmirror = true", section="main")
        # Assert
        assert result is True
        content = path.read_text()
        assert "fastestmirror = true" in content
        assert "keepcache = false" in content
        assert "[updates]" in content

    def test_cree_section_si_absente(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        write_file(path, "[commands]\nupgrade_type = default\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("fastestmirror = true", section="main")
        # Assert
        assert result is True
        content = path.read_text()
        assert "[main]" in content
        assert "fastestmirror = true" in content
        assert "[commands]" in content

    def test_appende_sans_section(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("--write-subs")
        # Assert
        assert result is True
        content = path.read_text()
        assert "--rm-cache-dir" in content
        assert "--write-subs" in content

    def test_inclut_commentaire_avant_bloc(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n")
        editor = SectionAwareEditor(path)
        # Act
        editor.ensure_block("--write-subs", comment="# Subtitles")
        # Assert
        content = path.read_text()
        lines = content.splitlines()
        idx = lines.index("--write-subs")
        assert lines[idx - 1] == "# Subtitles"

    def test_cree_dossier_parent_si_absent(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "deep" / "nested" / "config"
        editor = SectionAwareEditor(path)
        # Act
        editor.ensure_block("option = true")
        # Assert
        assert path.exists()

    def test_bloc_multiligne_detecte_present(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--write-subs\n--sub-langs fr\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("--write-subs\n--sub-langs fr")
        # Assert
        assert result is False

    def test_bloc_multiligne_insere_complet(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("--write-subs\n--sub-langs fr")
        # Assert
        assert result is True
        content = path.read_text()
        assert "--write-subs" in content
        assert "--sub-langs fr" in content

    def test_contenu_vide_retourne_false(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("")
        # Assert
        assert result is False

    def test_preserves_contenu_existant(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        original = "[main]\nkeepcache = false\n# throttle = 0\n"
        write_file(path, original)
        editor = SectionAwareEditor(path)
        # Act
        editor.ensure_block("fastestmirror = true", section="main")
        # Assert
        content = path.read_text()
        assert "keepcache = false" in content
        assert "# throttle = 0" in content

    def test_cree_section_dans_fichier_sans_newline_final(
        self, tmp_path: Path
    ) -> None:
        # Arrange — fichier existant sans \n final
        path = tmp_path / "dnf.conf"
        path.write_text("[commands]\nupgrade_type = default", encoding="utf-8")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.ensure_block("fastestmirror = true", section="main")
        # Assert
        assert result is True
        content = path.read_text()
        assert "[main]" in content
        assert "fastestmirror = true" in content
        assert "[commands]" in content


# ---------------------------------------------------------------------------
# TestListSections
# ---------------------------------------------------------------------------


class TestListSections:
    """Vérifie la détection des sections INI."""

    def test_retourne_sections_dans_ordre(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "dnf.conf"
        write_file(path, "[main]\nkey = val\n\n[commands]\nother = val\n")
        editor = SectionAwareEditor(path)
        # Act
        result = editor.list_sections()
        # Assert
        assert result == ["main", "commands"]

    def test_retourne_liste_vide_si_fichier_absent(self, tmp_path: Path) -> None:
        # Arrange
        editor = make_editor(tmp_path, "absent.conf")
        # Act & Assert
        assert editor.list_sections() == []

    def test_retourne_liste_vide_si_pas_de_sections(self, tmp_path: Path) -> None:
        # Arrange
        path = tmp_path / "config"
        write_file(path, "--rm-cache-dir\n--write-subs\n")
        editor = SectionAwareEditor(path)
        # Act & Assert
        assert editor.list_sections() == []
