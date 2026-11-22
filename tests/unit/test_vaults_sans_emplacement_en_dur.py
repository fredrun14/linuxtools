"""Garde A-13 : aucune chaîne d'emplacement ou de libellé dans ``src/**/*.py``."""

from pathlib import Path

import linuxtools

FORBIDDEN: tuple[str, ...] = (
    ".claude/CLAUDE.md",
    "conventions-vault.md",
    "## Emplacements",
    "vault perso",
    "vault pro",
    "vault foyer",
    "| Vault | Valeurs |",
    "/tank/obsidian",
    "Proxmox-NAS-DIY-1-Dashboard.md",
)


def find_forbidden(root: Path) -> list[str]:
    """Rend les occurrences ``fichier:ligne: chaîne`` des chaînes interdites."""
    trouvees: list[str] = []
    for chemin in sorted(root.rglob("*.py")):
        relatif = chemin.relative_to(root)
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        for numero, ligne in enumerate(lignes, start=1):
            trouvees.extend(
                f"{relatif}:{numero}: {chaine}"
                for chaine in FORBIDDEN
                if chaine in ligne
            )
    return trouvees


def test_find_forbidden_signale_une_chaine_dans_un_fichier_py(
    tmp_path: Path,
) -> None:
    """Une chaîne interdite dans un ``.py`` est rapportée avec fichier et ligne."""
    (tmp_path / "a.py").write_text("x = 1\ny = '/tank/obsidian'\n", encoding="utf-8")

    assert find_forbidden(tmp_path) == ["a.py:2: /tank/obsidian"]


def test_find_forbidden_ignore_un_fichier_non_py(tmp_path: Path) -> None:
    """Un fichier ``.toml`` portant une chaîne interdite est toléré."""
    (tmp_path / "a.toml").write_text("p = '/tank/obsidian'\n", encoding="utf-8")

    assert find_forbidden(tmp_path) == []


def test_src_ne_contient_aucune_chaine_interdite() -> None:
    """Le code de ``linuxtools`` ne porte aucun emplacement ni libellé en dur."""
    racine = Path(linuxtools.__file__).parent

    assert find_forbidden(racine) == []
