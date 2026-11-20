"""Tests de comportement de PathChecker (existence du répertoire parent)."""

from pathlib import Path

import pytest

from linuxtools.validation import PathChecker


def test_parent_qui_est_un_fichier_est_refuse(tmp_path: Path) -> None:
    """Un parent existant mais non répertoire est rejeté."""
    fichier = tmp_path / "fichier"
    fichier.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="n'est pas un répertoire"):
        PathChecker([str(fichier / "enfant.txt")]).validate()
