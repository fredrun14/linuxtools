"""Tests de comportement complémentaires pour le module filesystem."""

import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.filesystem.acl import ensure_shared_group_directory
from linuxtools.filesystem.backup import LinuxFileBackup, copytree_secure
from linuxtools.filesystem.linux import LinuxFileManager
from tests.unit.couverture_helpers import cmd_result


def _faux_groupe() -> MagicMock:
    """Faux résultat de grp.getgrnam portant le GID courant."""
    groupe = MagicMock()
    groupe.gr_gid = os.getgid()
    return groupe


def test_acl_nfsv4_sans_logger_est_appliquee_apres_echec_posix(
    tmp_path: Path, executeur: MagicMock
) -> None:
    """Sans logger, le repli sur nfs4_setfacl réussit sans rien journaliser."""
    repertoire = tmp_path / "partage"
    repertoire.mkdir()
    executeur.run.side_effect = [cmd_result(success=False), cmd_result()]

    with patch("linuxtools.filesystem.acl.grp.getgrnam", return_value=_faux_groupe()):
        ensure_shared_group_directory(repertoire, "partage-lan", executor=executeur)

    outils = [c.args[0][0] for c in executeur.run.call_args_list]
    assert outils == ["setfacl", "nfs4_setfacl"]


def test_copytree_ignore_les_entrees_ni_fichier_ni_dossier(tmp_path: Path) -> None:
    """Une socket dans la source n'est pas copiée, le reste l'est."""
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.txt").write_text("a", encoding="utf-8")
    with socket.socket(socket.AF_UNIX) as sock:
        sock.bind(str(source / "sock"))

        copytree_secure(source, tmp_path / "dst")

    assert (tmp_path / "dst" / "a.txt").read_text(encoding="utf-8") == "a"
    assert not (tmp_path / "dst" / "sock").exists()


def test_sauvegarde_d_une_source_absente_sans_logger_renvoie_false(
    tmp_path: Path,
) -> None:
    """Sans logger, une source absente donne False sans créer la sauvegarde."""
    sauvegarde = tmp_path / "bak"

    assert LinuxFileBackup().backup(tmp_path / "absent", sauvegarde) is False
    assert not sauvegarde.exists()


def test_sauvegarde_vers_un_lien_symbolique_sans_logger_leve_oserror(
    tmp_path: Path,
) -> None:
    """Sans logger, une cible de sauvegarde symlink est refusée (OSError)."""
    source = tmp_path / "f"
    source.write_text("x", encoding="utf-8")
    cible = tmp_path / "lien"
    cible.symlink_to(tmp_path / "ailleurs")

    with pytest.raises(OSError):  # noqa: PT011 — l'erreur exacte dépend de l'OS
        LinuxFileBackup().backup(source, cible)


def test_restauration_sans_sauvegarde_sans_logger_leve_file_not_found(
    tmp_path: Path,
) -> None:
    """Sans logger, restaurer une sauvegarde absente lève FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Aucune sauvegarde"):
        LinuxFileBackup().restore(tmp_path / "f", tmp_path / "absente")


def test_restauration_vers_un_lien_symbolique_sans_logger_leve_oserror(
    tmp_path: Path,
) -> None:
    """Sans logger, restaurer sur un symlink est refusé (OSError)."""
    sauvegarde = tmp_path / "bak"
    sauvegarde.write_text("x", encoding="utf-8")
    cible = tmp_path / "lien"
    cible.symlink_to(tmp_path / "ailleurs")

    with pytest.raises(OSError):  # noqa: PT011 — l'erreur exacte dépend de l'OS
        LinuxFileBackup().restore(cible, sauvegarde)


def test_gestionnaire_de_fichiers_sans_logger_cree_lit_supprime(
    tmp_path: Path,
) -> None:
    """Sans logger, création, lecture et suppression fonctionnent."""
    gestionnaire = LinuxFileManager()
    fichier = tmp_path / "f.txt"

    assert gestionnaire.create_file(fichier, "bonjour") is True
    assert gestionnaire.read_file(fichier) == "bonjour"
    assert gestionnaire.delete_file(fichier) is True
    assert not fichier.exists()


def test_gestionnaire_de_fichiers_sans_logger_signale_les_echecs(
    tmp_path: Path,
) -> None:
    """Sans logger, les échecs de création/suppression donnent False, lecture lève."""
    gestionnaire = LinuxFileManager()
    lien = tmp_path / "lien"
    lien.symlink_to(tmp_path / "ailleurs")

    assert gestionnaire.create_file(lien, "x") is False
    assert gestionnaire.delete_file(tmp_path / "absent") is False
    with pytest.raises(FileNotFoundError):
        gestionnaire.read_file(tmp_path / "absent")
