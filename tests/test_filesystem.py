"""Tests pour les modules filesystem.linux et filesystem.backup."""

import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.filesystem.backup import (
    LinuxFileBackup,
    copytree_secure,
)
from linuxtools.filesystem.linux import LinuxFileManager


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
        with pytest.raises(OSError):
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
        """Fichier créé avec permissions 0o644, indépendant de l'umask."""
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
        with pytest.raises(OSError):
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
        """Teste la branche except OSError dans restore()."""
        backup_path = str(tmp_path / "backup.txt")
        Path(backup_path).write_text("content")
        file_path = str(tmp_path / "restored.txt")
        logger = MagicMock()
        backup = LinuxFileBackup(logger)
        with patch(
            "linuxtools.filesystem.backup._copy_secure",
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

    def test_backup_refuse_symlink_source(self, tmp_path):
        """Lève OSError si la source est un symlink (O_NOFOLLOW sur src)."""
        real = tmp_path / "real.txt"
        real.write_text("données originales")
        link_src = tmp_path / "link_src.txt"
        link_src.symlink_to(real)
        backup_path = tmp_path / "bak.txt"
        backup, logger = self._make_backup()
        with pytest.raises(OSError):
            backup.backup(str(link_src), str(backup_path))
        assert not backup_path.exists()

    def test_backup_sans_logger(self, tmp_path):
        """backup() fonctionne sans logger injecté."""
        source = tmp_path / "source.txt"
        source.write_text("contenu")
        bak = tmp_path / "bak.txt"
        backup = LinuxFileBackup()
        result = backup.backup(str(source), str(bak))
        assert result is True
        assert bak.read_text() == "contenu"

    def test_restore_sans_logger(self, tmp_path):
        """restore() fonctionne sans logger injecté."""
        bak = tmp_path / "bak.txt"
        bak.write_text("sauvegardé")
        dest = tmp_path / "dest.txt"
        backup = LinuxFileBackup()
        backup.restore(str(dest), str(bak))
        assert dest.read_text() == "sauvegardé"


class TestCopytreeSecure:
    """Tests pour copytree_secure."""

    def _make_tree(self, root: Path) -> Path:
        """Crée un arbre source : a.txt, sub/b.txt."""
        root.mkdir()
        (root / "a.txt").write_text("contenu a")
        sub = root / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("contenu b")
        return root

    def test_copie_arbre_complet(self, tmp_path):
        """Copie un arbre et vérifie contenu + structure."""
        src = self._make_tree(tmp_path / "src")
        dst = tmp_path / "dst"
        result = copytree_secure(src, dst)
        assert (dst / "a.txt").read_text() == "contenu a"
        assert (dst / "sub" / "b.txt").read_text() == "contenu b"
        assert result == dst

    def test_fichiers_ont_permissions_0644(self, tmp_path):
        """Fichiers copiés avec permissions 0o644."""
        src = self._make_tree(tmp_path / "src")
        dst = tmp_path / "dst"
        copytree_secure(src, dst)
        assert os.stat(dst / "a.txt").st_mode & 0o777 == 0o644
        assert os.stat(dst / "sub" / "b.txt").st_mode & 0o777 == 0o644

    def test_repertoires_ont_permissions_0755(self, tmp_path):
        """Répertoires créés avec permissions 0o755."""
        src = self._make_tree(tmp_path / "src")
        dst = tmp_path / "dst"
        copytree_secure(src, dst)
        assert os.stat(dst).st_mode & 0o777 == 0o755
        assert os.stat(dst / "sub").st_mode & 0o777 == 0o755

    def test_dirs_exist_ok_false_leve_FileExistsError(self, tmp_path):
        """Lève FileExistsError si dst existe et dirs_exist_ok=False."""
        src = self._make_tree(tmp_path / "src")
        dst = tmp_path / "dst"
        dst.mkdir()
        with pytest.raises(FileExistsError):
            copytree_secure(src, dst, dirs_exist_ok=False)

    def test_dirs_exist_ok_true_fusionne(self, tmp_path):
        """Fusionne dans un répertoire existant."""
        src = self._make_tree(tmp_path / "src")
        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / "existant.txt").write_text("garde-moi")
        copytree_secure(src, dst, dirs_exist_ok=True)
        assert (dst / "existant.txt").read_text() == "garde-moi"
        assert (dst / "a.txt").read_text() == "contenu a"

    def test_ignore_filtre_fichiers(self, tmp_path):
        """ignore exclut les fichiers correspondants."""
        src = self._make_tree(tmp_path / "src")
        (src / "cache.pyc").write_text("bytecode")
        dst = tmp_path / "dst"
        copytree_secure(
            src, dst,
            ignore=shutil.ignore_patterns("*.pyc"),
        )
        assert not (dst / "cache.pyc").exists()
        assert (dst / "a.txt").exists()

    def test_ignore_filtre_repertoires(self, tmp_path):
        """ignore exclut les répertoires correspondants."""
        src = self._make_tree(tmp_path / "src")
        pycache = src / "__pycache__"
        pycache.mkdir()
        (pycache / "mod.pyc").write_text("bytecode")
        dst = tmp_path / "dst"
        copytree_secure(
            src, dst,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        assert not (dst / "__pycache__").exists()

    def test_symlinks_ignores_silencieusement(self, tmp_path):
        """Symlinks dans l'arbre source sont ignorés."""
        src = self._make_tree(tmp_path / "src")
        (src / "lien.txt").symlink_to(src / "a.txt")
        dst = tmp_path / "dst"
        copytree_secure(src, dst)
        assert not (dst / "lien.txt").exists()
        assert (dst / "a.txt").exists()

    def test_source_absente_leve_FileNotFoundError(self, tmp_path):
        """Lève FileNotFoundError si src n'existe pas."""
        with pytest.raises(FileNotFoundError):
            copytree_secure(
                tmp_path / "inexistant", tmp_path / "dst"
            )

    def test_source_pas_repertoire_leve_NotADirectoryError(
        self, tmp_path
    ):
        """Lève NotADirectoryError si src est un fichier."""
        src = tmp_path / "fichier.txt"
        src.write_text("pas un répertoire")
        with pytest.raises(NotADirectoryError):
            copytree_secure(src, tmp_path / "dst")

    def test_source_symlink_leve_OSError(self, tmp_path):
        """Lève OSError si src est un symlink vers un répertoire."""
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(OSError):
            copytree_secure(link, tmp_path / "dst")

    def test_repertoire_vide(self, tmp_path):
        """Copie un répertoire vide."""
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"
        copytree_secure(src, dst)
        assert dst.is_dir()
        assert list(dst.iterdir()) == []

    def test_retourne_path_destination(self, tmp_path):
        """Retourne Path(dst)."""
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"
        result = copytree_secure(src, dst)
        assert result == Path(dst)
        assert isinstance(result, Path)

    def test_follow_symlinks_copie_fichier_cible(self, tmp_path):
        """follow_symlinks=True copie le contenu du fichier cible."""
        src = tmp_path / "src"
        src.mkdir()
        real = src / "real.txt"
        real.write_text("contenu réel")
        (src / "lien.txt").symlink_to(real)
        dst = tmp_path / "dst"
        copytree_secure(src, dst, follow_symlinks=True)
        assert (dst / "lien.txt").read_text() == "contenu réel"
        assert not (dst / "lien.txt").is_symlink()

    def test_follow_symlinks_copie_repertoire_cible(self, tmp_path):
        """follow_symlinks=True recurse dans le répertoire cible."""
        src = tmp_path / "src"
        src.mkdir()
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        (real_dir / "inner.txt").write_text("inner")
        (src / "lien_dir").symlink_to(real_dir)
        dst = tmp_path / "dst"
        copytree_secure(src, dst, follow_symlinks=True)
        assert (dst / "lien_dir" / "inner.txt").read_text() == "inner"
        assert not (dst / "lien_dir").is_symlink()

    def test_follow_symlinks_false_ignore_symlinks(self, tmp_path):
        """follow_symlinks=False (défaut) ignore les symlinks."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "real.txt").write_text("réel")
        (src / "lien.txt").symlink_to(src / "real.txt")
        dst = tmp_path / "dst"
        copytree_secure(src, dst, follow_symlinks=False)
        assert (dst / "real.txt").exists()
        assert not (dst / "lien.txt").exists()

    def test_follow_symlinks_symlink_mort_ignore(self, tmp_path):
        """follow_symlinks=True ignore les symlinks morts."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "dead_link").symlink_to(tmp_path / "nexiste_pas")
        dst = tmp_path / "dst"
        copytree_secure(src, dst, follow_symlinks=True)
        assert not (dst / "dead_link").exists()
