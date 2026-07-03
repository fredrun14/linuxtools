"""Tests unitaires pour PathCheckerMountPoint."""

from pathlib import Path
from unittest.mock import patch

import pytest

from linuxtools.validation import PathCheckerMountPoint

_MODULE = "linuxtools.validation.path_checker_mount_point"


class TestPathCheckerMountPoint:
    """Tests pour PathCheckerMountPoint."""

    def test_validate_chemin_direct_mount(self, tmp_path):
        """Chemin lui-même point de montage → pas d'exception."""
        target = tmp_path / "mnt"
        target.mkdir()
        with patch(f"{_MODULE}.os.path.ismount", return_value=True):
            PathCheckerMountPoint(target).validate()

    def test_validate_parent_est_mount(self, tmp_path):
        """Sous-répertoire d'un montage → OK."""
        nas_mount = tmp_path / "syno" / "backup"
        destination = nas_mount / "home"
        destination.mkdir(parents=True)

        def ismount_side(path):
            return Path(path) == nas_mount

        with patch(f"{_MODULE}.os.path.ismount", side_effect=ismount_side):
            PathCheckerMountPoint(destination).validate()

    def test_validate_leve_si_aucun_mount(self, tmp_path):
        """Aucun montage trouvé → ValueError."""
        target = tmp_path / "local" / "data"
        target.mkdir(parents=True)
        with patch(f"{_MODULE}.os.path.ismount", return_value=False):
            with pytest.raises(ValueError):
                PathCheckerMountPoint(target).validate()

    def test_message_contient_chemin(self, tmp_path):
        """Le message d'erreur contient le chemin d'origine."""
        target = tmp_path / "nas" / "backup"
        target.mkdir(parents=True)
        with patch(f"{_MODULE}.os.path.ismount", return_value=False):
            with pytest.raises(ValueError, match=str(target)):
                PathCheckerMountPoint(target).validate()

    def test_nearest_mount_remonte_au_parent(self, tmp_path):
        """_nearest_mount_point retourne le bon ancêtre."""
        parent = tmp_path / "mnt"
        child = parent / "subdir"
        child.mkdir(parents=True)

        def ismount_side(path):
            return Path(path) == parent

        with patch(f"{_MODULE}.os.path.ismount", side_effect=ismount_side):
            checker = PathCheckerMountPoint(child)
            result = checker._nearest_mount_point(child)
            assert result == parent

    def test_accepte_str_en_entree(self, tmp_path):
        """Accepte un str en plus de Path."""
        target = tmp_path / "mnt"
        target.mkdir()
        with patch(f"{_MODULE}.os.path.ismount", return_value=True):
            PathCheckerMountPoint(str(target)).validate()
