"""Tests pour le module integrity."""

from unittest.mock import MagicMock, patch

import pytest

from linuxtools.errors import IntegrityError
from linuxtools.integrity import (
    SHA256IntegrityChecker,
    calculate_checksum,
)
from linuxtools.logging import FileLogger


class TestCalculateChecksum:
    """Tests pour la fonction calculate_checksum."""

    def test_sha256(self, tmp_path):
        """Test du calcul SHA256."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum = calculate_checksum(test_file)

        # SHA256 de "Hello, World!"
        assert len(checksum) == 64  # SHA256 = 64 caractères hex

    def test_different_content_different_checksum(self, tmp_path):
        """Test que des contenus différents donnent des checksums différents."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        checksum1 = calculate_checksum(file1)
        checksum2 = calculate_checksum(file2)

        assert checksum1 != checksum2

    def test_same_content_same_checksum(self, tmp_path):
        """Test que des contenus identiques donnent le même checksum."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        content = "Same content"
        file1.write_text(content)
        file2.write_text(content)

        checksum1 = calculate_checksum(file1)
        checksum2 = calculate_checksum(file2)

        assert checksum1 == checksum2

    def test_sha512_algorithm(self, tmp_path):
        """Test avec algorithme SHA512 (autorisé)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")

        checksum = calculate_checksum(test_file, algorithm='sha512')

        assert len(checksum) == 128  # SHA512 = 128 caractères hex

    def test_invalid_algorithm(self, tmp_path):
        """Test avec algorithme invalide (non dans la whitelist)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")

        with pytest.raises(ValueError, match="non autorisé"):
            calculate_checksum(test_file, algorithm='invalid')

    def test_checksum_algorithme_non_autorise_leve_valueerror(self, tmp_path):
        """MD5 est refusé par la whitelist (algorithme faible)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")

        with pytest.raises(ValueError, match="non autorisé"):
            calculate_checksum(test_file, algorithm='md5')

    def test_file_not_found(self):
        """Test avec fichier inexistant."""
        with pytest.raises(FileNotFoundError):
            calculate_checksum("/nonexistent/file.txt")


class TestSHA256IntegrityChecker:
    """Tests pour SHA256IntegrityChecker."""

    @pytest.fixture
    def logger(self, tmp_path):
        """Crée un logger pour les tests."""
        log_file = tmp_path / "test.log"
        return FileLogger(str(log_file))

    def test_verify_file_success(self, tmp_path, logger):
        """Test de vérification réussie d'un fichier."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        content = "Test content"
        source.write_text(content)
        dest.write_text(content)

        checker = SHA256IntegrityChecker(logger)

        assert checker.verify_file(str(source), str(dest)) is True

    def test_verify_file_failure(self, tmp_path, logger):
        """Test de vérification échouée d'un fichier."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        source.write_text("Content 1")
        dest.write_text("Content 2")

        checker = SHA256IntegrityChecker(logger)

        assert checker.verify_file(str(source), str(dest)) is False

    def test_verify_directory(self, tmp_path, logger):
        """Test de vérification d'un répertoire."""
        # Créer structure source
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("Content 1")
        (source_dir / "file2.txt").write_text("Content 2")

        # Créer structure destination identique
        dest_dir = tmp_path / "dest" / "source"
        dest_dir.mkdir(parents=True)
        (dest_dir / "file1.txt").write_text("Content 1")
        (dest_dir / "file2.txt").write_text("Content 2")

        checker = SHA256IntegrityChecker(logger)

        assert checker.verify(str(source_dir), str(tmp_path / "dest")) is True

    def test_verify_missing_file(self, tmp_path, logger):
        """Test avec fichier manquant dans destination."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("Content")

        dest_dir = tmp_path / "dest" / "source"
        dest_dir.mkdir(parents=True)
        # Pas de fichier dans dest

        checker = SHA256IntegrityChecker(logger)

        assert checker.verify(str(source_dir), str(tmp_path / "dest")) is False

    def test_get_checksum(self, tmp_path, logger):
        """Test de la méthode get_checksum."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")

        checker = SHA256IntegrityChecker(logger)
        checksum = checker.get_checksum(str(test_file))

        assert len(checksum) == 64

    def test_verify_file_oserror_returns_false(self, tmp_path, logger):
        """Test que verify_file retourne False en cas d'OSError."""
        # Arrange — fichier source inexistant déclenche FileNotFoundError
        checker = SHA256IntegrityChecker(logger)

        # Act
        result = checker.verify_file(
            str(tmp_path / "inexistant.txt"),
            str(tmp_path / "dest.txt"),
        )

        # Assert
        assert result is False

    def test_verify_with_dest_subdir(self, tmp_path, logger):
        """Test de verify avec un dest_subdir explicite."""
        # Arrange
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("Contenu")

        custom_dest = tmp_path / "dest" / "custom"
        custom_dest.mkdir(parents=True)
        (custom_dest / "file.txt").write_text("Contenu")

        checker = SHA256IntegrityChecker(logger)

        # Act
        result = checker.verify(
            str(source_dir),
            str(tmp_path / "dest"),
            dest_subdir="custom",
        )

        # Assert
        assert result is True

    def test_verify_directory_flat_destination(self, tmp_path, logger):
        """Test que verify utilise la destination si le sous-dossier n'existe pas.

        Quand destination/basename(source) n'existe pas,
        actual_dest est remplacé par destination directement.
        """
        # Arrange
        source_dir = tmp_path / "mysource"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("Contenu")

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        (dest_dir / "file.txt").write_text("Contenu")
        # tmp_path/dest/mysource n'existe pas → fallback sur dest_dir

        checker = SHA256IntegrityChecker(logger)

        # Act
        result = checker.verify(str(source_dir), str(dest_dir))

        # Assert
        assert result is True

    def test_verify_directory_with_subdirectories(self, tmp_path, logger):
        """Test que verify ignore les sous-répertoires et traite les fichiers."""
        # Arrange
        source_dir = tmp_path / "source"
        subdir = source_dir / "subdir"
        subdir.mkdir(parents=True)
        (source_dir / "file1.txt").write_text("Contenu 1")
        (subdir / "file2.txt").write_text("Contenu 2")

        dest_dir = tmp_path / "dest" / "source"
        dest_subdir = dest_dir / "subdir"
        dest_subdir.mkdir(parents=True)
        (dest_dir / "file1.txt").write_text("Contenu 1")
        (dest_subdir / "file2.txt").write_text("Contenu 2")

        checker = SHA256IntegrityChecker(logger)

        # Act
        result = checker.verify(
            str(source_dir), str(tmp_path / "dest")
        )

        # Assert
        assert result is True

    def test_verify_directory_checksum_mismatch(self, tmp_path, logger):
        """Test que verify retourne False si un checksum diffère."""
        # Arrange
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("Contenu original")

        dest_dir = tmp_path / "dest" / "source"
        dest_dir.mkdir(parents=True)
        (dest_dir / "file.txt").write_text("Contenu modifié")

        checker = SHA256IntegrityChecker(logger)

        # Act
        result = checker.verify(
            str(source_dir), str(tmp_path / "dest")
        )

        # Assert
        assert result is False

    def test_verify_exception_returns_false(self, tmp_path, logger):
        """Test que verify retourne False en cas d'OSError."""
        # Arrange
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        checker = SHA256IntegrityChecker(logger)

        # Act
        with patch(
            "pathlib.Path.rglob",
            side_effect=OSError("Erreur de lecture"),
        ):
            result = checker.verify(
                str(source_dir), str(tmp_path / "dest")
            )

        # Assert
        assert result is False

    def test_verify_source_vide_logue_warning(self, tmp_path):
        """verify() retourne True et logue un warning si la source est vide."""
        # Arrange
        mock_logger = MagicMock()
        source_dir = tmp_path / "empty_source"
        source_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        checker = SHA256IntegrityChecker(mock_logger)

        # Act
        result = checker.verify(str(source_dir), str(dest_dir))

        # Assert
        assert result is True
        mock_logger.log_warning.assert_called_once()
        warning_msg = mock_logger.log_warning.call_args[0][0]
        assert "vide" in warning_msg.lower() or "0" in warning_msg


class TestSHA256IntegrityCheckerOrRaise:
    """Tests pour verify_file_or_raise et verify_or_raise."""

    @pytest.fixture
    def logger(self, tmp_path):
        """Fixture fournissant un FileLogger pour les tests."""
        log_file = tmp_path / "test.log"
        return FileLogger(str(log_file))

    def test_verify_file_or_raise_succes_ne_leve_pas(
        self, tmp_path, logger
    ) -> None:
        """verify_file_or_raise ne lève rien si les fichiers sont identiques."""
        # Arrange
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        source.write_text("contenu")
        dest.write_text("contenu")
        checker = SHA256IntegrityChecker(logger)

        # Act / Assert — ne doit pas lever
        checker.verify_file_or_raise(source, dest)

    def test_verify_file_or_raise_leve_integrity_error(
        self, tmp_path, logger
    ) -> None:
        """verify_file_or_raise lève IntegrityError si les checksums diffèrent."""
        # Arrange
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        source.write_text("original")
        dest.write_text("modifié")
        checker = SHA256IntegrityChecker(logger)

        # Act / Assert
        with pytest.raises(IntegrityError):
            checker.verify_file_or_raise(source, dest)

    def test_verify_file_or_raise_attributs_integrity_error(
        self, tmp_path, logger
    ) -> None:
        """IntegrityError expose path, expected et actual non nuls."""
        # Arrange
        source = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        source.write_text("A")
        dest.write_text("B")
        checker = SHA256IntegrityChecker(logger)

        # Act
        with pytest.raises(IntegrityError) as exc_info:
            checker.verify_file_or_raise(source, dest)

        # Assert
        err = exc_info.value
        assert err.path == dest
        assert err.expected is not None
        assert err.actual is not None
        assert err.expected != err.actual

    def test_verify_file_or_raise_oserror_propage(
        self, tmp_path, logger
    ) -> None:
        """verify_file_or_raise ne capture pas OSError."""
        # Arrange
        checker = SHA256IntegrityChecker(logger)

        # Act / Assert
        with pytest.raises(OSError):
            checker.verify_file_or_raise(
                tmp_path / "inexistant.txt",
                tmp_path / "dest.txt",
            )

    def test_verify_or_raise_succes_retourne_count(
        self, tmp_path, logger
    ) -> None:
        """verify_or_raise retourne le nombre de fichiers vérifiés."""
        # Arrange
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "a.txt").write_text("A")
        (source_dir / "b.txt").write_text("B")
        dest_dir = tmp_path / "dest" / "source"
        dest_dir.mkdir(parents=True)
        (dest_dir / "a.txt").write_text("A")
        (dest_dir / "b.txt").write_text("B")
        checker = SHA256IntegrityChecker(logger)

        # Act
        count = checker.verify_or_raise(
            str(source_dir), str(tmp_path / "dest")
        )

        # Assert
        assert count == 2

    def test_verify_or_raise_fichier_manquant_leve_integrity_error(
        self, tmp_path, logger
    ) -> None:
        """verify_or_raise lève IntegrityError si un fichier est absent."""
        # Arrange
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("contenu")
        dest_dir = tmp_path / "dest" / "source"
        dest_dir.mkdir(parents=True)  # vide — fichier manquant
        checker = SHA256IntegrityChecker(logger)

        # Act / Assert
        with pytest.raises(IntegrityError):
            checker.verify_or_raise(
                str(source_dir), str(tmp_path / "dest")
            )

    def test_verify_or_raise_checksum_different_leve_integrity_error(
        self, tmp_path, logger
    ) -> None:
        """verify_or_raise lève IntegrityError si un checksum diffère."""
        # Arrange
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("original")
        dest_dir = tmp_path / "dest" / "source"
        dest_dir.mkdir(parents=True)
        (dest_dir / "file.txt").write_text("modifié")
        checker = SHA256IntegrityChecker(logger)

        # Act / Assert
        with pytest.raises(IntegrityError):
            checker.verify_or_raise(
                str(source_dir), str(tmp_path / "dest")
            )

    def test_verify_or_raise_source_vide_retourne_zero(
        self, tmp_path, logger
    ) -> None:
        """verify_or_raise retourne 0 si la source est vide."""
        # Arrange
        source_dir = tmp_path / "source_vide"
        source_dir.mkdir()
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        checker = SHA256IntegrityChecker(logger)

        # Act
        count = checker.verify_or_raise(str(source_dir), str(dest_dir))

        # Assert
        assert count == 0
