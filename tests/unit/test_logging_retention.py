"""Tests pour la purge des anciens fichiers de logs."""

import os
import time
from pathlib import Path
from typing import Any

import pytest

from linuxtools.logging.retention import purge_old_logs

_JOUR = 86_400


def _creer(chemin: Path, age_jours: float) -> Path:
    """Crée un fichier dont la date de modification est simulée."""
    chemin.write_text("log", encoding="utf-8")
    t = time.time() - age_jours * _JOUR
    os.utime(chemin, (t, t))
    return chemin


def test_purge_old_logs_supprime_anciens_et_garde_recents(
    tmp_path: Path,
) -> None:
    """A-01 : l'ancien fichier du motif est supprimé, le récent gardé."""
    ancien = _creer(tmp_path / "run_vieux.log", 120)
    recent = _creer(tmp_path / "run_recent.log", 5)

    supprimes = purge_old_logs(tmp_path, "run_*.log")

    assert supprimes == [ancien]
    assert not ancien.exists()
    assert recent.exists()


def test_purge_old_logs_defaut_90_jours(tmp_path: Path) -> None:
    """F-02 : 89 jours conservé, 91 jours supprimé."""
    limite_basse = _creer(tmp_path / "run_89.log", 89)
    limite_haute = _creer(tmp_path / "run_91.log", 91)

    supprimes = purge_old_logs(tmp_path, "run_*.log")

    assert supprimes == [limite_haute]
    assert limite_basse.exists()


def test_purge_old_logs_ignore_hors_motif(tmp_path: Path) -> None:
    """A-02 : un ancien fichier d'un autre nom est conservé."""
    autre = _creer(tmp_path / "notes.txt", 400)

    assert purge_old_logs(tmp_path, "run_*.log") == []
    assert autre.exists()


def test_purge_old_logs_ignore_liens_symboliques(tmp_path: Path) -> None:
    """SEC : un lien ancien vers un fichier extérieur est conservé."""
    dossier = tmp_path / "logs"
    dossier.mkdir()
    cible = _creer(tmp_path / "externe.log", 400)
    lien = dossier / "run_lien.log"
    lien.symlink_to(cible)
    ancien = time.time() - 400 * _JOUR
    os.utime(lien, (ancien, ancien), follow_symlinks=False)

    assert purge_old_logs(dossier, "run_*.log") == []
    assert lien.is_symlink()
    assert cible.exists()


def test_purge_old_logs_ignore_sous_dossiers(tmp_path: Path) -> None:
    """SEC : un sous-dossier ancien au nom du motif est conservé."""
    sous_dossier = tmp_path / "run_archives.log"
    sous_dossier.mkdir()
    (sous_dossier / "x.log").write_text("x", encoding="utf-8")
    ancien = time.time() - 400 * _JOUR
    os.utime(sous_dossier, (ancien, ancien))

    assert purge_old_logs(tmp_path, "run_*.log") == []
    assert sous_dossier.is_dir()
    assert (sous_dossier / "x.log").exists()


def test_purge_old_logs_garde_fichier_courant(tmp_path: Path) -> None:
    """A-03 : le fichier `keep` est conservé même ancien."""
    courant = _creer(tmp_path / "run_courant.log", 400)
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    supprimes = purge_old_logs(tmp_path, "run_*.log", keep=courant)

    assert supprimes == [ancien]
    assert courant.exists()


def test_purge_old_logs_dry_run_liste_sans_supprimer(tmp_path: Path) -> None:
    """F-08 : en dry-run, le fichier est listé mais reste en place."""
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    supprimes = purge_old_logs(tmp_path, "run_*.log", dry_run=True)

    assert supprimes == [ancien]
    assert ancien.exists()


@pytest.mark.parametrize("motif", ["**", "*"])
def test_purge_old_logs_motif_double_etoile_ne_descend_pas_dans_les_sous_dossiers(
    tmp_path: Path, motif: str
) -> None:
    """F01 : `**` et `*` ne touchent jamais un fichier de sous-dossier."""
    sous_dossier = tmp_path / "sub"
    sous_dossier.mkdir()
    profond = _creer(sous_dossier / "run_vieux.log", 400)
    direct = _creer(tmp_path / "run_direct.log", 400)

    supprimes = purge_old_logs(tmp_path, motif)

    assert supprimes == [direct]
    assert profond.exists()


def test_purge_old_logs_dossier_absent_retourne_vide(tmp_path: Path) -> None:
    """F-10 : un dossier absent donne une liste vide, sans exception."""
    assert purge_old_logs(tmp_path / "absent", "run_*.log") == []


def test_purge_old_logs_dossier_lien_symbolique_ignore(
    tmp_path: Path,
) -> None:
    """SEC : un dossier qui est un lien symbolique n'est pas parcouru."""
    reel = tmp_path / "reel"
    reel.mkdir()
    ancien = _creer(reel / "run_vieux.log", 400)
    lien = tmp_path / "lien"
    lien.symlink_to(reel, target_is_directory=True)

    assert purge_old_logs(lien, "run_*.log") == []
    assert ancien.exists()


def test_purge_old_logs_echec_suppression_ne_leve_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-10 : un unlink refusé est ignoré et le fichier n'est pas listé."""
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    def refuser(*args: object, **kwargs: object) -> None:
        raise PermissionError("refusé")

    monkeypatch.setattr(os, "unlink", refuser)

    assert purge_old_logs(tmp_path, "run_*.log") == []
    assert ancien.exists()


def test_purge_old_logs_dossier_non_traversable_retourne_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F02 : un dossier qu'on ne peut pas ouvrir donne une liste vide."""
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    def refuser(*args: object, **kwargs: object) -> int:
        raise PermissionError("non traversable")

    monkeypatch.setattr(os, "open", refuser)

    assert purge_old_logs(tmp_path, "run_*.log") == []
    assert ancien.exists()


def test_purge_old_logs_keep_relatif_ou_autre_ecriture_est_conserve(
    tmp_path: Path,
) -> None:
    """F05 : `keep` écrit autrement (via `..`) désigne le même fichier."""
    (tmp_path / "sub").mkdir()
    courant = _creer(tmp_path / "run_courant.log", 400)
    autre_ecriture = tmp_path / "sub" / ".." / "run_courant.log"

    assert purge_old_logs(tmp_path, "run_*.log", keep=autre_ecriture) == []
    assert courant.exists()


def test_purge_old_logs_motif_double_etoile_avec_suffixe_valide(
    tmp_path: Path,
) -> None:
    """F07 : `**.log` est un motif valide, comparé au nom du fichier."""
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    assert purge_old_logs(tmp_path, "**.log") == [ancien]
    assert not ancien.exists()


def test_purge_old_logs_stat_en_echec_ignore_le_fichier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F04 : un stat en échec sur un nom l'écarte, les autres sont traités."""
    illisible = _creer(tmp_path / "run_illisible.log", 400)
    ancien = _creer(tmp_path / "run_vieux.log", 400)
    vrai_stat = os.stat

    def stat_selectif(path: Any, *args: Any, **kwargs: Any) -> Any:
        if path == "run_illisible.log":
            raise OSError("stat impossible")
        return vrai_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat_selectif)

    assert purge_old_logs(tmp_path, "run_*.log") == [ancien]
    assert illisible.exists()


def test_purge_old_logs_listage_en_echec_retourne_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F04 : un listage impossible donne une liste vide, sans exception."""
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    def echouer(*args: object, **kwargs: object) -> None:
        raise OSError("listage impossible")

    monkeypatch.setattr(os, "scandir", echouer)

    assert purge_old_logs(tmp_path, "run_*.log") == []
    assert ancien.exists()


def test_purge_old_logs_keep_inexistant_ne_protege_rien(
    tmp_path: Path,
) -> None:
    """F04 : un `keep` introuvable n'empêche pas la purge des autres."""
    ancien = _creer(tmp_path / "run_vieux.log", 400)

    supprimes = purge_old_logs(
        tmp_path, "run_*.log", keep=tmp_path / "run_absent.log"
    )

    assert supprimes == [ancien]
    assert not ancien.exists()


@pytest.mark.parametrize("motif", ["", "../x", "a/b", "/etc/*", "**/x"])
def test_purge_old_logs_rejette_motif_invalide(
    tmp_path: Path, motif: str
) -> None:
    """SEC : motif vide ou contenant un séparateur -> ValueError."""
    with pytest.raises(ValueError):
        purge_old_logs(tmp_path, motif)


@pytest.mark.parametrize("duree", [0, -1])
def test_purge_old_logs_rejette_duree_invalide(
    tmp_path: Path, duree: int
) -> None:
    """Une durée inférieure à 1 jour -> ValueError."""
    with pytest.raises(ValueError):
        purge_old_logs(tmp_path, "run_*.log", max_age_days=duree)


def test_purge_old_logs_keep_lien_symbolique_protege_la_cible(
    tmp_path: Path,
) -> None:
    """F10 : `keep` lien symbolique protège le fichier qu'il désigne."""
    dossier = tmp_path / "logs"
    dossier.mkdir()
    cible = _creer(dossier / "run_courant.log", 400)
    lien = tmp_path / "lien_courant.log"
    lien.symlink_to(cible)

    supprimes = purge_old_logs(dossier, "run_*.log", keep=lien)

    assert supprimes == []
    assert cible.exists()
