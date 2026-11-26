"""Tests du scope ``user`` du runtime (destinataire unique, chemins XDG)."""

import json
import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from linuxtools.jobnotify.runtime import (
    BUSCTL,
    LOGINCTL,
    RUNUSER,
    SYSTEMCTL,
    login,
    main,
    start,
)
from linuxtools.jobnotify.spec import NotifiedJob
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BASE_OUTCOMES,
    BOB_PROPS,
    BOOT_A,
    FakeRunner,
    Recorder,
    Reply,
    ctx_for,
    descriptor_of,
    files_under,
    mode_of,
    notify_calls,
    system_handler,
    write_boot_id,
)

OWNER_UID = os.geteuid()  # les fichiers de test appartiennent à l'utilisateur réel
GUARD = "demo-app-demo-guard.service"
USER_JOB = NotifiedJob(
    name="demo",
    owner="demo-app",
    watched_unit="demo.service",
    scope="user",
    lock=True,
    start_texts=("Sauvegarde en cours", "Ne coupez pas la session."),
    end_texts={
        outcome: (f"fin {outcome.value}", "corps de fin") for outcome in BASE_OUTCOMES
    },
)
USER_DESC = descriptor_of(USER_JOB)


def xdg_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Environnement d'un service utilisateur : dossiers XDG sous ``tmp_path``."""
    return {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
        **extra,
    }


def state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "demo-app" / "demo" / "state.json"


def id_file(tmp_path: Path) -> Path:
    return tmp_path / "run" / "demo-app" / "demo" / "id"


def seen_file(tmp_path: Path) -> Path:
    return tmp_path / "state" / "demo-app" / "demo" / "seen"


def write_user_state(tmp_path: Path, **overrides: object) -> None:
    state: dict[str, object] = {
        "boot_id": BOOT_A,
        "started_at": 1000.0,
        "status": "running",
        "outcome": None,
        "delivered": [],
    }
    state.update(overrides)
    state_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    state_path(tmp_path).write_text(json.dumps(state))


def user_runner(
    *,
    notify: Reply | None = None,
    active: dict[str, str] | None = None,
    stop: tuple[int, str] = (0, ""),
) -> FakeRunner:
    """Poste simulé : busctl, ``systemctl --user`` ; aucune session loginctl."""
    states = active or {}
    base = system_handler(sessions={"1": ALICE_PROPS, "2": BOB_PROPS}, notify=notify)

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if argv[:3] == [SYSTEMCTL, "--user", "stop"]:
            return stop
        if argv[:3] == [SYSTEMCTL, "--user", "is-active"]:
            return 0, states.get(argv[3], "inactive") + "\n"
        return base(argv)

    return FakeRunner(handler)


def run_verb(
    tmp_path: Path,
    verb: str,
    runner: FakeRunner,
    env: dict[str, str] | None = None,
    *,
    euid: int = OWNER_UID,
    result: str = "success",
) -> Recorder:
    write_boot_id(tmp_path, BOOT_A)
    recorder = Recorder()
    base_env = xdg_env(tmp_path, SERVICE_RESULT=result) if env is None else env
    ctx = ctx_for(runner, tmp_path, recorder, euid=euid, job=USER_DESC, env=base_env)
    assert main([verb], ctx) == 0
    return recorder


def test_start_scope_user_notifie_le_seul_proprietaire(tmp_path: Path) -> None:
    runner = user_runner()

    run_verb(tmp_path, "start", runner)

    binaries = [argv[0] for argv, _ in runner.calls]
    # Un seul envoi, direct : ni loginctl, ni runuser, aucun autre destinataire.
    assert binaries == [BUSCTL]
    assert LOGINCTL not in binaries
    assert RUNUSER not in binaries
    argv = runner.calls[0][0]
    assert argv[:3] == [BUSCTL, "--user", "call"]
    assert "Sauvegarde en cours" in argv
    assert json.loads(state_path(tmp_path).read_text())["status"] == "running"
    assert id_file(tmp_path).read_text() == "42\n"


def test_chemins_scope_user_suivent_xdg(tmp_path: Path) -> None:
    run_verb(tmp_path, "start", user_runner())

    assert sorted(files_under(tmp_path)) == [
        "proc/sys/kernel/random/boot_id",
        "run/demo-app/demo/id",
        "run/demo-app/demo/lock",
        "state/demo-app/demo/state.json",
    ]
    assert mode_of(state_path(tmp_path)) == 0o600
    assert mode_of(state_path(tmp_path).parent) == 0o700
    assert mode_of(id_file(tmp_path)) == 0o600
    assert mode_of(id_file(tmp_path).parent) == 0o700


def test_chemins_scope_user_replient_sur_home_local_state(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path / "home"), "XDG_RUNTIME_DIR": str(tmp_path / "run")}

    run_verb(tmp_path, "start", user_runner(), env)

    expected = tmp_path / "home/.local/state/demo-app/demo/state.json"
    assert json.loads(expected.read_text())["status"] == "running"


def test_end_scope_user_remplace_la_notification_du_lancement(tmp_path: Path) -> None:
    run_verb(tmp_path, "start", user_runner())
    runner = user_runner()
    started = json.loads(state_path(tmp_path).read_text())["started_at"]
    # L'ID du lancement doit être plus récent que le début du run (mtime > started_at).
    os.utime(id_file(tmp_path), (started + 5, started + 5))

    run_verb(tmp_path, "end", runner)

    (argv,) = notify_calls(runner)
    assert argv[argv.index("demo-app") + 1] == "42"  # remplace l'ID mémorisé
    assert "fin success" in argv
    assert runner.calls[0][0][:4] == [SYSTEMCTL, "--user", "stop", GUARD]
    final = json.loads(state_path(tmp_path).read_text())
    assert final["status"] == "done"
    assert final["delivered"] == [OWNER_UID]


def test_end_scope_user_continue_si_l_arret_du_compagnon_echoue(
    tmp_path: Path,
) -> None:
    write_user_state(tmp_path)
    runner = user_runner(stop=(5, ""))

    run_verb(tmp_path, "end", runner)

    assert len(notify_calls(runner)) == 1
    assert json.loads(state_path(tmp_path).read_text())["delivered"] == [OWNER_UID]


def test_login_scope_user_rattrape(tmp_path: Path) -> None:
    # Run sans bureau (linger) : la notification de fin échoue, rien n'est livré.
    write_user_state(tmp_path)
    run_verb(tmp_path, "end", user_runner(notify=(1, "")))
    assert json.loads(state_path(tmp_path).read_text())["delivered"] == []
    runner = user_runner()

    run_verb(tmp_path, "login", runner)

    (argv,) = notify_calls(runner)
    assert "fin success" in argv
    assert seen_file(tmp_path).read_text().strip() == "1000.0"


def test_login_scope_user_run_en_cours_utilise_systemctl_user(tmp_path: Path) -> None:
    write_user_state(tmp_path)
    runner = user_runner(active={GUARD: "active"})

    run_verb(tmp_path, "login", runner)

    assert [SYSTEMCTL, "--user", "is-active", GUARD] in [a for a, _ in runner.calls]
    (argv,) = notify_calls(runner)
    assert "Sauvegarde en cours" in argv
    assert id_file(tmp_path).read_text() == "42\n"


def test_scope_user_sans_xdg_runtime_dir_ne_notifie_pas_mais_rend_zero(
    tmp_path: Path,
) -> None:
    runner = user_runner()
    env = {"XDG_STATE_HOME": str(tmp_path / "state")}

    recorder = run_verb(tmp_path, "start", runner, env)

    assert runner.calls == []
    assert not state_path(tmp_path).exists()
    assert recorder.messages == [
        "demo-notify : scope user : XDG_RUNTIME_DIR ou dossier d'état absent, "
        "aucune action\n"
    ]


def test_scope_user_sans_dossier_d_etat_ne_notifie_pas_mais_rend_zero(
    tmp_path: Path,
) -> None:
    runner = user_runner()
    env = {"XDG_RUNTIME_DIR": str(tmp_path / "run"), "HOME": "relatif"}

    run_verb(tmp_path, "start", runner, env)

    assert runner.calls == []
    assert not (tmp_path / "run").exists()


def test_scope_user_etat_d_un_autre_proprietaire_est_ignore(tmp_path: Path) -> None:
    write_user_state(tmp_path, status="done", outcome="success")
    runner = user_runner()

    recorder = run_verb(tmp_path, "login", runner, euid=OWNER_UID + 1)

    assert notify_calls(runner) == []
    assert "demo-notify : état illisible, ignoré\n" in recorder.messages


def test_scope_user_verbe_direct_sans_xdg_runtime_dir_leve_runtimeerror(
    tmp_path: Path,
) -> None:
    ctx = ctx_for(
        user_runner(),
        tmp_path,
        Recorder(),
        euid=OWNER_UID,
        job=USER_DESC,
        env={"XDG_STATE_HOME": str(tmp_path / "state")},
    )

    with pytest.raises(RuntimeError, match="XDG_RUNTIME_DIR"):
        start(ctx)


def test_scope_user_verbe_direct_sans_dossier_d_etat_leve_runtimeerror(
    tmp_path: Path,
) -> None:
    ctx = ctx_for(
        user_runner(),
        tmp_path,
        Recorder(),
        euid=OWNER_UID,
        job=USER_DESC,
        env={"XDG_RUNTIME_DIR": str(tmp_path / "run")},
    )

    with pytest.raises(RuntimeError, match="XDG_STATE_HOME"):
        login(ctx)
