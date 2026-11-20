"""Tests de comportement de SHA256IntegrityChecker sans logger."""

from pathlib import Path

import pytest

from linuxtools.errors.exceptions import IntegrityError
from linuxtools.integrity.base import ChecksumCalculator
from linuxtools.integrity.sha256 import SHA256IntegrityChecker


def _arbre(racine: Path, fichiers: dict[str, str]) -> Path:
    """Crée une arborescence de fichiers texte sous ``racine``."""
    racine.mkdir(parents=True, exist_ok=True)
    for nom, contenu in fichiers.items():
        (racine / nom).write_text(contenu, encoding="utf-8")
    return racine


class _CalculateurQuiEchoue(ChecksumCalculator):
    """Calculateur de checksum levant une ValueError."""

    def calculate(self, file_path: str | Path, algorithm: str = "sha256") -> str:
        """Échoue systématiquement."""
        raise ValueError(f"algorithme refusé : {algorithm} pour {file_path}")


def test_verify_file_sur_fichier_absent_renvoie_false(tmp_path: Path) -> None:
    """Sans logger, un fichier illisible donne False."""
    (tmp_path / "a").write_text("x", encoding="utf-8")

    assert SHA256IntegrityChecker().verify_file(tmp_path / "a", tmp_path / "b") is False


def test_verify_detecte_un_fichier_manquant_sans_logger(tmp_path: Path) -> None:
    """Sans logger, un fichier absent de la destination fait échouer verify."""
    source = _arbre(tmp_path / "src", {"a": "1"})
    destination = _arbre(tmp_path / "dst", {})

    assert SHA256IntegrityChecker().verify(str(source), str(destination)) is False


def test_verify_detecte_un_contenu_different_sans_logger(tmp_path: Path) -> None:
    """Sans logger, un checksum différent fait échouer verify."""
    source = _arbre(tmp_path / "src", {"a": "1"})
    destination = _arbre(tmp_path / "dst", {"a": "2"})

    assert SHA256IntegrityChecker().verify(str(source), str(destination)) is False


def test_verify_accepte_une_copie_conforme_sans_logger(tmp_path: Path) -> None:
    """Sans logger, une copie identique est validée."""
    source = _arbre(tmp_path / "src", {"a": "1"})
    destination = _arbre(tmp_path / "dst", {"a": "1"})

    assert SHA256IntegrityChecker().verify(str(source), str(destination)) is True


def test_verify_renvoie_false_si_le_calcul_leve_une_valueerror(
    tmp_path: Path,
) -> None:
    """Sans logger, une ValueError du calculateur donne False (pas d'exception)."""
    source = _arbre(tmp_path / "src", {"a": "1"})
    destination = _arbre(tmp_path / "dst", {"a": "1"})
    checker = SHA256IntegrityChecker(checksum_calculator=_CalculateurQuiEchoue())

    assert checker.verify(str(source), str(destination)) is False


def test_verify_or_raise_compte_les_fichiers_et_ignore_les_dossiers(
    tmp_path: Path,
) -> None:
    """Sans logger, seuls les fichiers sont comptés ; les dossiers sont ignorés."""
    source = _arbre(tmp_path / "src", {"a": "1"})
    (source / "sous").mkdir()
    destination = _arbre(tmp_path / "dst", {"a": "1"})

    assert SHA256IntegrityChecker().verify_or_raise(str(source), str(destination)) == 1


def test_verify_or_raise_leve_sur_contenu_different_sans_logger(
    tmp_path: Path,
) -> None:
    """Sans logger, un checksum différent lève IntegrityError."""
    source = _arbre(tmp_path / "src", {"a": "1"})
    destination = _arbre(tmp_path / "dst", {"a": "2"})

    with pytest.raises(IntegrityError):
        SHA256IntegrityChecker().verify_or_raise(str(source), str(destination))


def test_get_checksum_sans_logger_renvoie_le_sha256(tmp_path: Path) -> None:
    """Sans logger, le checksum d'un fichier connu est celui de SHA-256."""
    fichier = tmp_path / "a"
    fichier.write_bytes(b"abc")

    assert SHA256IntegrityChecker().get_checksum(fichier) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
