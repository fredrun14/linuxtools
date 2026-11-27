"""Tests du runtime : isolation de deux jobs, courses de création."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from linuxtools.jobnotify.runtime import (
    SYSTEMCTL,
    main,
)
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BOOT_A,
    DNF5_DESC,
    FLATPAK_DESC,
    FLATPAK_GUARD,
    GUARD_UNIT,
    HASH_AB,
    LISTING_AB,
    FakeRunner,
    ForeignLock,
    Recorder,
    TickingClock,
    before_path,
    ctx_for,
    end_env,
    flatpak_handler,
    locked_ctx,
    notify_calls,
    parse_notify,
    run_flatpak,
    write_boot_id,
    write_flatpak_state,
)

DNF_STATE = "var/lib/fedora-post-install/dnf5-auto/state.json"


FLATPAK_STATE = "var/lib/fedora-post-install/flatpak-auto/state.json"


DNF_ROOT_ID = "run/fedora-post-install/dnf5-auto/ids/1000"


FLATPAK_ROOT_ID = "run/fedora-post-install/flatpak-auto/ids/1000"


def run_jobs(
    tmp_path: Path, steps: Sequence[tuple[str, str | None]]
) -> tuple[FakeRunner, list[int]]:
    """Rejoue ``(verbe, job)`` sur une même racine, avec un même runner.

    Chaque appel reçoit son propre ``Ctx`` (comme deux processus distincts) ;
    un job ``None`` vaut l'appel sans job des unités dnf déjà installées.
    """
    write_boot_id(tmp_path, BOOT_A)
    runner = FakeRunner(
        flatpak_handler(sessions={"1": ALICE_PROPS}, listings=[(0, LISTING_AB)])
    )
    codes = []
    for verb, job in steps:
        argv = [verb] if job is None else [verb, job]
        job_desc = FLATPAK_DESC if job == "flatpak-auto" else DNF5_DESC
        ctx = ctx_for(runner, tmp_path, Recorder(), euid=0, job=job_desc, env=end_env())
        codes.append(main(argv, ctx))
    return runner, codes


def stops_of(runner: FakeRunner) -> list[list[str]]:
    return [argv for argv, _ in runner.calls if argv[:2] == [SYSTEMCTL, "stop"]]


def test_deux_jobs_simultanes_la_fin_de_flatpak_ne_touche_pas_au_run_dnf(
    tmp_path: Path,
) -> None:
    runner, codes = run_jobs(
        tmp_path,
        [
            ("start", None),  # dnf : ID de notification 42
            ("snapshot", "flatpak-auto"),
            ("start", "flatpak-auto"),  # Flatpak : ID 43
            ("end", "flatpak-auto"),
        ],
    )

    assert codes == [0, 0, 0, 0]
    # Le run dnf est intact : état toujours « running », ID présent, compagnon vivant.
    assert json.loads((tmp_path / DNF_STATE).read_text())["status"] == "running"
    assert (tmp_path / DNF_ROOT_ID).read_text() == "42\n"
    assert stops_of(runner) == [[SYSTEMCTL, "stop", FLATPAK_GUARD]]
    # La fin de Flatpak remplace SA notification de lancement, pas celle de dnf.
    *_, fin = notify_calls(runner)
    assert parse_notify(fin)["replaces"] == "43"
    assert json.loads((tmp_path / FLATPAK_STATE).read_text())["status"] == "done"


def test_deux_jobs_simultanes_la_fin_de_dnf_ne_touche_pas_au_run_flatpak(
    tmp_path: Path,
) -> None:
    runner, codes = run_jobs(
        tmp_path,
        [
            ("snapshot", "flatpak-auto"),
            ("start", "flatpak-auto"),  # Flatpak : ID 42
            ("start", None),  # dnf : ID 43
            ("end", None),
        ],
    )

    assert codes == [0, 0, 0, 0]
    # Le run Flatpak est intact : état « running », ID, empreinte, compagnon vivant.
    assert json.loads((tmp_path / FLATPAK_STATE).read_text())["status"] == "running"
    assert (tmp_path / FLATPAK_ROOT_ID).read_text() == "42\n"
    assert before_path(tmp_path).read_text() == HASH_AB + "\n"
    assert stops_of(runner) == [[SYSTEMCTL, "stop", GUARD_UNIT]]
    # La fin de dnf remplace SA notification de lancement, pas celle de Flatpak.
    *_, fin = notify_calls(runner)
    assert parse_notify(fin)["replaces"] == "43"
    assert json.loads((tmp_path / DNF_STATE).read_text())["status"] == "done"


def test_les_deux_jobs_ont_des_verrous_flock_distincts(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_flatpak_state(tmp_path)
    foreign = ForeignLock(tmp_path)  # verrou DNF tenu (``start`` dnf en plein travail)
    recorder = Recorder()
    clock = TickingClock()
    ctx, _ = locked_ctx(
        tmp_path,
        flatpak_handler(sessions={"1": ALICE_PROPS}, listings=[(0, LISTING_AB)]),
        clock,
        recorder,
        job=FLATPAK_DESC,
    )

    code = main(["end", "flatpak-auto"], ctx)
    foreign.release()

    assert code == 0
    assert clock.sleeps == 0  # aucune attente : le verrou Flatpak est un autre fichier
    assert not any("verrou occupé" in m for m in recorder.messages)
    assert json.loads((tmp_path / FLATPAK_STATE).read_text())["status"] == "done"


def _mentir_exists_une_fois(monkeypatch: pytest.MonkeyPatch, cible: Path) -> None:
    """Simule la course : ``exists()`` répond False une fois, la cible existe déjà."""
    original = Path.exists
    deja_menti = False

    def _exists(self: Path, *args: Any, **kwargs: Any) -> bool:
        nonlocal deja_menti
        if self == cible and not deja_menti:
            deja_menti = True
            return False
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", _exists)


def test_snapshot_dossier_cree_entre_exists_et_mkdir_ecrit_l_empreinte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange : le compagnon a créé le dossier juste après le exists() du hook
    run_dir = before_path(tmp_path).parent
    run_dir.mkdir(parents=True, mode=0o700)
    _mentir_exists_une_fois(monkeypatch, run_dir)

    # Act
    _, _, codes = run_flatpak(
        tmp_path, ["snapshot"], flatpak_handler(listings=[(0, LISTING_AB)])
    )

    # Assert : pas d'erreur avalée, l'empreinte before est écrite
    assert codes == [0]
    assert before_path(tmp_path).read_text() == HASH_AB + "\n"


def test_snapshot_fichier_a_la_place_du_dossier_reste_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange : un fichier occupe l'emplacement du dossier (exists() masqué)
    run_dir = before_path(tmp_path).parent
    run_dir.parent.mkdir(parents=True)
    run_dir.write_text("intrus")
    _mentir_exists_une_fois(monkeypatch, run_dir)

    # Act
    run_flatpak(tmp_path, ["snapshot"], flatpak_handler(listings=[(0, LISTING_AB)]))

    # Assert : rien n'est écrit, le fichier est intact
    assert run_dir.read_text() == "intrus"


def test_snapshot_lien_a_la_place_du_dossier_reste_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange : un lien vers un dossier témoin occupe l'emplacement
    temoin = tmp_path / "temoin"
    temoin.mkdir()
    run_dir = before_path(tmp_path).parent
    run_dir.parent.mkdir(parents=True)
    run_dir.symlink_to(temoin)
    _mentir_exists_une_fois(monkeypatch, run_dir)
    # Le lien apparaît après le premier contrôle : is_symlink() ment aussi une fois
    # (ce contrôle initial) et c'est le contrôle après mkdir qui doit refuser.
    original_is_symlink = Path.is_symlink
    deja_menti = False

    def _is_symlink(self: Path) -> bool:
        nonlocal deja_menti
        if self == run_dir and not deja_menti:
            deja_menti = True
            return False
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)

    # Act
    run_flatpak(tmp_path, ["snapshot"], flatpak_handler(listings=[(0, LISTING_AB)]))

    # Assert : rien n'est écrit à travers le lien
    assert list(temoin.iterdir()) == []
