"""Tests des chemins d'état du runtime, paramétrés par `owner` (Q-06)."""

from pathlib import Path

from linuxtools.jobnotify import runtime
from linuxtools.jobnotify.runtime import Descriptor
from linuxtools.jobnotify.spec import NotifiedJob, Outcome
from tests.unit.jobnotify.runtime_support import (
    DNF5_DESC,
    FLATPAK_DESC,
    FakeRunner,
    Recorder,
    descriptor_of,
    make_ctx,
)


def _ctx(tmp_path: Path, job: Descriptor = DNF5_DESC) -> runtime.Ctx:
    ctx = make_ctx(FakeRunner(lambda argv: (1, "")), tmp_path, Recorder())
    ctx.descriptor = job
    return ctx


def test_chemins_etat_identiques_pour_owner_fedora_post_install(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)

    # Littéraux du hook historique : le schéma des chemins est figé (Q-06).
    assert runtime._state_target(ctx).path == (
        tmp_path / "var/lib/fedora-post-install/dnf5-auto/state.json"
    )
    assert runtime._lock_target(ctx).path == (
        tmp_path / "run/fedora-post-install/dnf5-auto/lock"
    )
    assert runtime._ids_target(ctx, 1000).path == (
        tmp_path / "run/fedora-post-install/dnf5-auto/ids/1000"
    )
    assert runtime._user_id_target(ctx, 1000).path == (
        tmp_path / "run/user/1000/fedora-post-install/dnf5-auto.id"
    )
    assert runtime._before_target(_ctx(tmp_path, FLATPAK_DESC)).path == (
        tmp_path / "run/fedora-post-install/flatpak-auto/before"
    )


def test_chemins_suivent_owner_et_nom_du_descripteur(tmp_path: Path) -> None:
    job = NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="system",
        start_texts=("a", "b"),
        end_texts=dict.fromkeys((Outcome.SUCCESS, Outcome.FAILURE), ("a", "b"))
        | {Outcome.INTERRUPTED: ("a", "b")},
    )
    ctx = make_ctx(FakeRunner(lambda argv: (1, "")), tmp_path, Recorder())
    ctx.descriptor = descriptor_of(job)

    assert runtime._state_target(ctx).path == (
        tmp_path / "var/lib/demo-app/demo/state.json"
    )
    assert runtime._lock_target(ctx).path == tmp_path / "run/demo-app/demo/lock"
    assert runtime._user_id_target(ctx, 1000).path == (
        tmp_path / "run/user/1000/demo-app/demo.id"
    )
