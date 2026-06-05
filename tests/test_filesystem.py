"""Tests pour les modules filesystem.linux et filesystem.backup."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.filesystem.linux import LinuxFileManager
from linux_python_utils.filesystem.backup import LinuxFileBackup, _copy_secure


class TestLinuxFileManager:
    """Tests pour LinuxFileManager."""

    def _make_manager(self):
        """Crée un manager avec un logger mock."""
        logger = MagicMock()
        return LinuxFileManager(logger), logger

    def test_create_file_succes(self, tmp_path):
        """Crée un fichier avec succès."""
        manager, logger = self._make_manager()
        file_path = str(tmp_path / "test.txt")
        result = manager.create_file(file_path, "contenu test")
        assert result is True
        assert os.path.exists(file_path)
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "contenu test"
        logger.log_info.assert_called_once()

    def test_create_file_echec(self):
        """Retourne False si le répertoire parent n'existe pas."""
        manager, logger = self._make_manager()
        result = manager.create_file(
            "/repertoire_inexistant_xyz/fichier.txt", "contenu"
        )
        assert result is False
        logger.log_error.assert_called_once()

    def test_file_exists_retourne_true(self, tmp_path):
        """Retourne True si le fichier existe."""
        f = tmp_path / "existe.txt"
        f.write_text("x")
        manager, _ = self._make_manager()
        assert manager.file_exists(str(f)) is True

    def test_file_exists_retourne_false(self, tmp_path):
        """Retourne False si le fichier n'existe pas."""
        manager, _ = self._make_manager()
        assert manager.file_exists(
            str(tmp_path / "inexistant.txt")
        ) is False

    def test_read_file_succes(self, tmp_path):
        """Lit le contenu d'un fichier avec succès."""
        f = tmp_path / "lisible.txt"
        f.write_text("contenu test", encoding="utf-8")
        manager, logger = self._make_manager()
        content = manager.read_file(str(f))
        assert content == "contenu test"
        logger.log_info.assert_called_once()

    def test_read_file_echec_fichier_inexistant(self):
        """Lève une exception si le fichier n'existe pas."""
        manager, logger = self._make_manager()
        with pytest.raises(Exception):
            manager.read_file("/repertoire_inexistant_xyz/fichier.txt")
        logger.log_error.assert_called_once()

    def test_delete_file_succes(self, tmp_path):
        """Supprime un fichier avec succès."""
        f = tmp_path / "supprimer.txt"
        f.write_text("x")
        manager, logger = self._make_manager()
        result = manager.delete_file(str(f))
        assert result is True
        assert not os.path.exists(str(f))
        logger.log_info.assert_called_once()

    def test_delete_file_echec_inexistant(self):
        """Retourne False si le fichier n'existe pas."""
        manager, logger = self._make_manager()
        result = manager.delete_file(
            "/repertoire_inexistant_xyz/fichier.txt"
        )
        assert result is False
        logger.log_error.assert_called_once()

    def test_create_file_refuse_symlink(self, tmp_path):
        """Retourne False et ne modifie pas la cible si c'est un symlink."""
        real = tmp_path / "real.txt"
        real.write_text("original")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        manager, logger = self._make_manager()
        result = manager.create_file(str(link), "nouveau contenu")
        assert result is False
        logger.log_error.assert_called_once()
        assert real.read_text() == "original"

    def test_create_file_fixe_permissions_0644(self, tmp_path):
        """Le fichier créé a les permissions 0o644 indépendamment de l'umask."""
        file_path = str(tmp_path / "secure.txt")
        manager, _ = self._make_manager()
        manager.create_file(file_path, "contenu")
        assert os.stat(file_path).st_mode & 0o777 == 0o644


class TestLinuxFileBackup:
    """Tests pour LinuxFileBackup."""

    def _make_backup(self):
        """Crée un gestionnaire de sauvegarde avec un logger mock."""
        logger = MagicMock()
        return LinuxFileBackup(logger), logger

    def test_backup_succes(self, tmp_path):
        """Crée une sauvegarde avec succès."""
        source = tmp_path / "original.txt"
        source.write_text("contenu original")
        backup_path = str(tmp_path / "backup.txt")
        backup, logger = self._make_backup()
        backup.backup(str(source), backup_path)
        assert os.path.exists(backup_path)
        logger.log_info.assert_called_once()

    def test_backup_source_absente_retourne_false(self, tmp_path):
        """Retourne False et logge un warning si la source est absente."""
        backup_path = str(tmp_path / "backup.txt")
        backup, logger = self._make_backup()
        result = backup.backup(
            str(tmp_path / "inexistant_source.txt"), backup_path
        )
        assert result is False
        logger.log_warning.assert_called_once()
        assert not os.path.exists(backup_path)

    def test_backup_retourne_true_si_succes(self, tmp_path):
        """Retourne True quand la sauvegarde réussit."""
        source = tmp_path / "original.txt"
        source.write_text("données")
        backup, _ = self._make_backup()
        result = backup.backup(str(source), str(tmp_path / "bak.txt"))
        assert result is True

    def test_backup_refuse_symlink_destination(self, tmp_path):
        """Lève OSError si la destination est un symlink."""
        source = tmp_path / "source.txt"
        source.write_text("données")
        real_dest = tmp_path / "real_dest.txt"
        real_dest.write_text("ne pas écraser")
        link_dest = tmp_path / "link_dest.txt"
        link_dest.symlink_to(real_dest)
        backup, logger = self._make_backup()
        with pytest.raises(OSError):
            backup.backup(str(source), str(link_dest))
        assert real_dest.read_text() == "ne pas écraser"

    def test_backup_erreur_destination_invalide(self, tmp_path):
        """Lève une exception si la destination est invalide."""
        source = tmp_path / "source.txt"
        source.write_text("x")
        backup, logger = self._make_backup()
        with pytest.raises(Exception):
            backup.backup(
                str(source),
                "/repertoire_inexistant_xyz/backup.txt"
            )
        logger.log_error.assert_called_once()

    def test_restore_succes(self, tmp_path):
        """Restaure un fichier avec succès."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("contenu sauvegardé", encoding="utf-8")
        restore_path = str(tmp_path / "restaure.txt")
        backup, logger = self._make_backup()
        backup.restore(restore_path, str(backup_file))
        assert os.path.exists(restore_path)
        logger.log_info.assert_called_once()

    def test_restore_backup_inexistant(self, tmp_path):
        """Lève FileNotFoundError si la sauvegarde n'existe pas."""
        backup, logger = self._make_backup()
        with pytest.raises(FileNotFoundError):
            backup.restore(
                str(tmp_path / "dest.txt"),
                str(tmp_path / "inexistant_backup.txt")
            )
        logger.log_error.assert_called_once()

    def test_restore_exception_oserror(self, tmp_path):
        """Teste le chemin except OSError (non-FileNotFoundError) dans restore()."""
        backup_path = str(tmp_path / "backup.txt")
        Path(backup_path).write_text("content")
        file_path = str(tmp_path / "restored.txt")
        logger = MagicMock()
        backup = LinuxFileBackup(logger)
        with patch(
            "linux_python_utils.filesystem.backup._copy_secure",
            side_effect=OSError("disk error"),
        ):
            with pytest.raises(OSError):
                backup.restore(file_path, backup_path)
        logger.log_error.assert_called()

    def test_restore_refuse_symlink_destination(self, tmp_path):
        """Lève OSError si la destination de restauration est un symlink."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("sauvegarde")
        real_dest = tmp_path / "real.txt"
        real_dest.write_text("ne pas écraser")
        link_dest = tmp_path / "link.txt"
        link_dest.symlink_to(real_dest)
        backup, logger = self._make_backup()
        with pytest.raises(OSError):
            backup.restore(str(link_dest), str(backup_file))
        assert real_dest.read_text() == "ne pas écraser"
