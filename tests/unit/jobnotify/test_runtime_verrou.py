"""Tests du verrou flock du runtime."""

import fcntl
import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from linuxtools.jobnotify.runtime import (
    SYSTEMCTL,
    TOTAL_BUDGET_S,
    end,
    main,
    start,
)
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BOOT_A,
    GUARD_UNIT,
    ForeignLock,
    Recorder,
    TickingClock,
    is_locked_by_someone,
    lock_path,
    locked_ctx,
    mode_of,
    read_state_file,
    root_id_path,
    system_handler,
    write_boot_id,
    write_state_file,
)


def test_end_attend_la_fin_de_start_avant_d_arreter_le_compagnon(
    tmp_path: Path,
) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_state_file(tmp_path)
    foreign = ForeignLock(tmp_path)
    stop_calls_while_held: list[bool] = []
    base = system_handler(sessions={"1": ALICE_PROPS})

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if list(argv[:2]) == [SYSTEMCTL, "stop"]:
            stop_calls_while_held.append(not released)
        return base(argv)

    released = False

    def on_sleep(count: int) -> None:
        nonlocal released
        if count == 3:  # ``start`` finit : sa dernière écriture précède celle de end
            write_state_file(tmp_path, started_at=1500.0)
            foreign.release()
            released = True

    clock = TickingClock(on_sleep)
    ctx, runner = locked_ctx(tmp_path, handler, clock, Recorder())

    end(ctx)

    assert clock.sleeps == 3
    # Arrêt du compagnon seulement après la libération par start.
    assert stop_calls_while_held == [False]
    assert read_state_file(tmp_path)["status"] == "done"
    assert read_state_file(tmp_path)["started_at"] == 1500.0
    assert runner.calls[0][0][:2] == [SYSTEMCTL, "stop"]


def test_end_verrou_tenu_trop_longtemps_poursuit_sans_bloquer(
    tmp_path: Path,
) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_state_file(tmp_path)
    foreign = ForeignLock(tmp_path)
    recorder = Recorder()
    clock = TickingClock()
    ctx, runner = locked_ctx(
        tmp_path, system_handler(sessions={"1": ALICE_PROPS}), clock, recorder
    )

    rc = main(["end"], ctx)

    foreign.release()
    assert rc == 0
    assert 0 < clock.now - 500.0 <= TOTAL_BUDGET_S
    assert [SYSTEMCTL, "stop", GUARD_UNIT] in [a for a, _ in runner.calls]
    assert read_state_file(tmp_path)["status"] == "done"
    assert any("verrou" in m for m in recorder.messages)


def test_start_verrou_indisponible_travaille_quand_meme(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    foreign = ForeignLock(tmp_path)
    clock = TickingClock()
    ctx, _ = locked_ctx(
        tmp_path, system_handler(sessions={"1": ALICE_PROPS}), clock, Recorder()
    )

    start(ctx)

    foreign.release()
    assert read_state_file(tmp_path)["status"] == "running"
    assert root_id_path(tmp_path, 1000).read_text().strip() == "42"


def test_start_tient_le_verrou_pendant_tout_son_travail(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    held: list[bool] = []
    base = system_handler(sessions={"1": ALICE_PROPS})

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        held.append(is_locked_by_someone(tmp_path))
        return base(argv)

    ctx, _ = locked_ctx(tmp_path, handler, TickingClock(), Recorder())

    start(ctx)

    assert held
    assert all(held)
    assert not is_locked_by_someone(tmp_path)  # relâché à la fin


def test_end_tient_le_verrou_pendant_l_arret_du_compagnon_et_le_relache(
    tmp_path: Path,
) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_state_file(tmp_path)
    at_stop: list[bool] = []
    base = system_handler(sessions={"1": ALICE_PROPS})

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if list(argv[:2]) == [SYSTEMCTL, "stop"]:
            at_stop.append(is_locked_by_someone(tmp_path))
        return base(argv)

    ctx, _ = locked_ctx(tmp_path, handler, TickingClock(), Recorder())

    end(ctx)

    assert at_stop == [True]
    assert not is_locked_by_someone(tmp_path)


def test_verrou_relache_meme_si_le_travail_leve(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        raise RuntimeError("panne")

    ctx, _ = locked_ctx(tmp_path, handler, TickingClock(), Recorder())

    rc = main(["start"], ctx)

    assert rc == 0
    assert not is_locked_by_someone(tmp_path)


def test_verrou_est_un_fichier_root_0600_dans_un_dossier_0700(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    ctx, _ = locked_ctx(tmp_path, system_handler(), TickingClock(), Recorder())

    start(ctx)

    assert mode_of(lock_path(tmp_path)) == 0o600
    assert mode_of(lock_path(tmp_path).parent) == 0o700


def test_verrou_lien_symbolique_refuse_sans_etre_suivi(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_state_file(tmp_path)
    cible = tmp_path / "cible"
    cible.write_text("intact")
    lock_path(tmp_path).parent.mkdir(parents=True)
    lock_path(tmp_path).symlink_to(cible)
    recorder = Recorder()
    ctx, runner = locked_ctx(
        tmp_path, system_handler(sessions={"1": ALICE_PROPS}), TickingClock(), recorder
    )

    end(ctx)

    assert cible.read_text() == "intact"
    assert lock_path(tmp_path).is_symlink()
    assert any("verrou" in m for m in recorder.messages)
    assert [SYSTEMCTL, "stop", GUARD_UNIT] in [a for a, _ in runner.calls]
    assert read_state_file(tmp_path)["status"] == "done"


def test_verrou_dossier_lien_symbolique_refuse(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    parent = lock_path(tmp_path).parent
    parent.parent.mkdir(parents=True)
    parent.symlink_to(ailleurs)
    ctx, _ = locked_ctx(tmp_path, system_handler(), TickingClock(), Recorder())

    start(ctx)

    assert list(ailleurs.iterdir()) == []


def test_verrou_non_regulier_refuse(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    lock_path(tmp_path).parent.mkdir(parents=True)
    os.mkfifo(lock_path(tmp_path))
    recorder = Recorder()
    ctx, _ = locked_ctx(tmp_path, system_handler(), TickingClock(), recorder)

    start(ctx)

    assert any("verrou" in m for m in recorder.messages)
    assert read_state_file(tmp_path)["status"] == "running"


def test_verrou_flock_en_erreur_poursuit_sans_verrou(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_boot_id(tmp_path, BOOT_A)

    def failing_flock(fd: int, operation: int) -> None:
        raise OSError(37, "ENOLCK")

    monkeypatch.setattr(fcntl, "flock", failing_flock)
    recorder = Recorder()
    ctx, _ = locked_ctx(tmp_path, system_handler(), TickingClock(), recorder)

    start(ctx)

    assert any("verrou" in m for m in recorder.messages)
    assert read_state_file(tmp_path)["status"] == "running"


def test_verrou_sans_budget_pose_utilise_le_delai_court(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    foreign = ForeignLock(tmp_path)
    clock = TickingClock()
    ctx, _ = locked_ctx(tmp_path, system_handler(), clock, Recorder())
    ctx.started = None  # hors ``main`` : pas de budget global imposé

    start(ctx)

    foreign.release()
    assert 0 < clock.now - 500.0 < TOTAL_BUDGET_S
