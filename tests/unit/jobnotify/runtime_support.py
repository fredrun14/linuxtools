"""Aides partagées des tests du runtime `jobnotify` (jobs et poste simulés)."""

import fcntl
import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest  # noqa: F401

from linuxtools.jobnotify.runtime import (
    BUSCTL,
    DNF5,
    LOGINCTL,
    SYSTEMCTL,
    Ctx,
    Descriptor,
    Session,
    end,
    main,
    parse_descriptor,
)
from linuxtools.jobnotify.runtime import (
    Outcome as RuntimeOutcome,
)
from linuxtools.jobnotify.spec import (
    Dnf5Probe,
    FingerprintProbe,
    NotifiedJob,
    Outcome,
)

# Textes constants des deux jobs de fedora-post-install, écrits à la main : ce sont
# les données qu'un consommateur fournit, ici sources indépendantes du runtime.
SHUTDOWN_OK = "Vous pouvez de nouveau éteindre le poste."
DNF5_START_BODY = (
    "N'éteignez pas le poste et ne le mettez pas en veille "
    "jusqu'à la fin de la mise à jour."
)
DNF5_END_TEXTS: Mapping[Outcome, tuple[str, str]] = {
    Outcome.SUCCESS: (
        "Mise à jour automatique terminée",
        f"Les mises à jour ont été installées. {SHUTDOWN_OK}",
    ),
    Outcome.SUCCESS_RESTART: (
        "Mise à jour automatique terminée : redémarrage requis",
        (
            "Les mises à jour ont été installées. Redémarrez le poste dès que "
            "possible ; vous pouvez de nouveau l'éteindre ou le mettre en veille."
        ),
    ),
    Outcome.NOTHING: (
        "Mise à jour automatique terminée",
        f"Aucune mise à jour à installer. {SHUTDOWN_OK}",
    ),
    Outcome.DONE_NO_DETAIL: (
        "Mise à jour automatique terminée",
        f"La mise à jour est terminée, mais son détail est illisible. {SHUTDOWN_OK}",
    ),
    Outcome.FAILURE: (
        "Mise à jour automatique en échec",
        (
            "La mise à jour a échoué : consultez « journalctl -u dnf5-automatic » "
            f"pour le détail. {SHUTDOWN_OK}"
        ),
    ),
    Outcome.INTERRUPTED: (
        "Mise à jour automatique interrompue",
        f"La mise à jour a été interrompue avant la fin. {SHUTDOWN_OK}",
    ),
}
FLATPAK_DONE = "Mise à jour Flatpak automatique terminée"
FLATPAK_START_SUMMARY = "Mise à jour Flatpak automatique en cours"
FLATPAK_END_TEXTS: Mapping[Outcome, tuple[str, str]] = {
    Outcome.SUCCESS: (
        FLATPAK_DONE,
        f"Les applications Flatpak ont été mises à jour. {SHUTDOWN_OK}",
    ),
    Outcome.NOTHING: (
        FLATPAK_DONE,
        f"Aucune application Flatpak à mettre à jour. {SHUTDOWN_OK}",
    ),
    Outcome.DONE_NO_DETAIL: (
        FLATPAK_DONE,
        f"La mise à jour est terminée, mais son détail est illisible. {SHUTDOWN_OK}",
    ),
    Outcome.FAILURE: (
        "Mise à jour Flatpak automatique en échec",
        (
            "La mise à jour a échoué : consultez « journalctl -u "
            f"flatpak-automatic » pour le détail. {SHUTDOWN_OK}"
        ),
    ),
    Outcome.INTERRUPTED: (
        "Mise à jour Flatpak automatique interrompue",
        f"La mise à jour a été interrompue avant la fin. {SHUTDOWN_OK}",
    ),
}

DNF5_JOB = NotifiedJob(
    name="dnf5-auto",
    owner="fedora-post-install",
    watched_unit="dnf5-automatic.service",
    scope="system",
    start_texts=("Mise à jour automatique en cours", DNF5_START_BODY),
    end_texts=DNF5_END_TEXTS,
    lock=True,
    probe=Dnf5Probe(),
)
FLATPAK_JOB = NotifiedJob(
    name="flatpak-auto",
    owner="fedora-post-install",
    watched_unit="flatpak-automatic.service",
    scope="system",
    start_texts=(FLATPAK_START_SUMMARY, DNF5_START_BODY),
    end_texts=FLATPAK_END_TEXTS,
    lock=True,
    probe=FingerprintProbe(
        argv=("/usr/bin/flatpak", "list", "--system", "--columns=ref,active:f")
    ),
)


def descriptor_of(job: NotifiedJob) -> Descriptor:
    """Descripteur du runtime relu depuis le JSON produit par `spec.py`."""
    descriptor = parse_descriptor(json.loads(job.to_descriptor()))
    assert descriptor is not None
    return descriptor


BASE_OUTCOMES = (Outcome.SUCCESS, Outcome.FAILURE, Outcome.INTERRUPTED)
DNF5_DESC = descriptor_of(DNF5_JOB)
FLATPAK_DESC = descriptor_of(FLATPAK_JOB)

# Littéraux écrits à la main (sources indépendantes du module de production).
GUARD_UNIT = "fedora-post-install-dnf5-auto-guard.service"
STATE_RELATIVE = Path("var/lib/fedora-post-install/dnf5-auto/state.json")
IDS_RELATIVE = Path("run/fedora-post-install/dnf5-auto/ids")
START_SUMMARY = DNF5_JOB.start_texts[0]
START_BODY = DNF5_JOB.start_texts[1]
# Mêmes issues, clés du ``Outcome`` du runtime (énumération distincte : stdlib seule).
END_TEXTS: Mapping[RuntimeOutcome, tuple[str, str]] = {
    RuntimeOutcome(issue.value): texts for issue, texts in DNF5_END_TEXTS.items()
}


STARTED_AT = 1000.0


RUN_OK = {"start_time": 1010, "command_line": "dnf5 automatic"}


RUN_ANTERIEUR = {"start_time": 990, "command_line": "dnf5 automatic"}


RUN_MANUEL = {"start_time": 1010, "command_line": "dnf5 install vim"}


Handler = Callable[[Sequence[str]], tuple[int, str]]


class FakeRunner:
    """Runner de test : enregistre les appels et répond via un gestionnaire."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.calls: list[tuple[list[str], float]] = []

    def __call__(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        self.calls.append((list(argv), timeout))
        return self.handler(argv)


class Recorder:
    """Collecte les messages écrits sur le stderr injecté."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> int:
        self.messages.append(message)
        return len(message)


def make_ctx(runner: FakeRunner, tmp_path: Path, recorder: Recorder) -> Ctx:
    return Ctx(runner=runner, root_dir=tmp_path, stderr=recorder, descriptor=DNF5_DESC)


def loginctl_handler(
    sessions: Mapping[str, Mapping[str, str]],
) -> Handler:
    """Simule loginctl : ``sessions`` associe un id à ses propriétés."""

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if argv[:3] == [LOGINCTL, "list-sessions", "--no-legend"]:
            return 0, "".join(f"{sid} 1000 x seat0\n" for sid in sessions)
        if argv[:2] == [LOGINCTL, "show-session"]:
            props = sessions[argv[2]]
            return 0, "".join(f"{k}={v}\n" for k, v in props.items())
        return 1, ""

    return handler


def props(
    *,
    uid: str = "1000",
    name: str = "alice",
    type_: str = "wayland",
    class_: str = "user",
    remote: str = "no",
    state: str = "active",
) -> dict[str, str]:
    return {
        "State": state,
        "Type": type_,
        "Class": class_,
        "Remote": remote,
        "Name": name,
        "User": uid,
    }


ALICE = Session(uid=1000, user="alice")


BOOT_A = "aaaa-1111"


BOOT_B = "bbbb-2222"


ALICE_PROPS = props(uid="1000", name="alice")


BOB_PROPS = props(uid="1001", name="bob")


TRANSACTION_RUN = [{"start_time": 1010, "command_line": "dnf5 automatic"}]


STATE_KEYS = {"boot_id", "started_at", "status", "outcome", "delivered"}


Reply = tuple[int, str] | Exception


class Clock:
    """Horloge de test : rend les instants donnés, puis répète le dernier."""

    def __init__(self, *times: float) -> None:
        self.times = list(times)

    def __call__(self) -> float:
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


def answer(value: tuple[int, str] | Exception) -> tuple[int, str]:
    """Rend la réponse simulée, ou lève l'exception simulée."""
    if isinstance(value, Exception):
        raise value
    return value


def system_handler(
    *,
    sessions: Mapping[str, Mapping[str, str]] | None = None,
    history: tuple[int, str] | Exception = (0, "[]"),
    running: tuple[int, str] | Exception = (0, "running\n"),
    needs: tuple[int, str] | Exception = (0, ""),
    active: tuple[int, str] | Exception = (0, "inactive\n"),
    guard: tuple[int, str] | Exception = (3, "inactive\n"),
    notify: tuple[int, str] | Exception | None = None,
) -> Handler:
    """Simule le poste : loginctl, systemctl, dnf5 et busctl."""
    base = loginctl_handler(sessions or {})
    next_id = iter(range(42, 1000))

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if argv[0] == LOGINCTL:
            return base(argv)
        if BUSCTL in argv:
            return answer(notify) if notify is not None else (0, f"u {next(next_id)}\n")
        replies: dict[tuple[str, ...], Reply] = {
            (SYSTEMCTL, "stop"): (0, ""),
            (SYSTEMCTL, "is-system-running"): running,
            (SYSTEMCTL, "is-active", GUARD_UNIT): guard,
            (SYSTEMCTL, "is-active"): active,
            (DNF5, "history", "list"): history,
            (DNF5, "needs-restarting"): needs,
        }
        for prefix, reply in replies.items():
            if tuple(argv[: len(prefix)]) == prefix:
                return answer(reply)
        return 1, ""

    return handler


def root_binary_lstat(_path: str) -> os.stat_result:
    """`lstat` d'un binaire sûr : fichier régulier 0755 appartenant à root."""
    return os.stat_result((stat.S_IFREG | 0o755, 1, 1, 1, 0, 0, 0, 0, 0, 0))


def ctx_for(
    runner: FakeRunner,
    tmp_path: Path,
    recorder: Recorder,
    *,
    euid: int,
    job: Descriptor = DNF5_DESC,
    env: Mapping[str, str] | None = None,
    now: Callable[[], float] = lambda: 2000.0,
    monotonic: Callable[[], float] = lambda: 500.0,
) -> Ctx:
    """Contexte de test : racine factice, root ou utilisateur fixé explicitement."""
    return Ctx(
        runner=runner,
        root_dir=tmp_path,
        env=env or {},
        now=now,
        monotonic=monotonic,
        geteuid=lambda: euid,
        lstat=root_binary_lstat,
        stderr=recorder,
        descriptor=job,
    )


def notify_calls(runner: FakeRunner) -> list[list[str]]:
    return [argv for argv, _ in runner.calls if BUSCTL in argv]


def parse_notify(argv: Sequence[str]) -> dict[str, str]:
    i = list(argv).index("fedora-post-install")
    return {
        "replaces": argv[i + 1],
        "summary": argv[i + 3],
        "body": argv[i + 4],
        "urgency": argv[i + 9],
        "expire": argv[i + 10],
    }


def write_boot_id(root: Path, value: str) -> None:
    path = root / "proc" / "sys" / "kernel" / "random" / "boot_id"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n")


def write_state_file(root: Path, **overrides: object) -> Path:
    state: dict[str, object] = {
        "boot_id": BOOT_A,
        "started_at": 1000.0,
        "status": "running",
        "outcome": None,
        "delivered": [],
    }
    state.update(overrides)
    path = root / STATE_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    return path


def read_state_file(root: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads((root / STATE_RELATIVE).read_text()))


def root_id_path(root: Path, uid: int) -> Path:
    return root / IDS_RELATIVE / str(uid)


def user_id_path(root: Path, uid: int) -> Path:
    return root / "run" / "user" / str(uid) / "fedora-post-install" / "dnf5-auto.id"


def mode_of(path: Path) -> int:
    return path.stat().st_mode & 0o777


def end_env(result: str = "success") -> dict[str, str]:
    return {"SERVICE_RESULT": result}


def run_end(
    tmp_path: Path,
    *,
    env: Mapping[str, str] | None = None,
    history: Reply = (0, "[]"),
    running: Reply = (0, "running\n"),
    needs: Reply = (0, ""),
    notify: Reply | None = None,
) -> tuple[FakeRunner, Recorder]:
    """Rejoue ``end`` en root sur un poste simulé à une session (alice)."""
    if not (tmp_path / "proc/sys/kernel/random/boot_id").exists():
        write_boot_id(tmp_path, BOOT_A)  # le boot courant est celui de l'état
    runner = FakeRunner(
        system_handler(
            sessions={"1": ALICE_PROPS},
            history=history,
            running=running,
            needs=needs,
            notify=notify,
        ),
    )
    recorder = Recorder()
    end(ctx_for(runner, tmp_path, recorder, euid=0, env=env or end_env()))
    return runner, recorder


def raw_state(**overrides: str) -> bytes:
    """État JSON écrit à la main ; chaque surcharge est un fragment JSON brut."""
    fields = {
        "boot_id": '"a"',
        "started_at": "1.0",
        "status": '"done"',
        "outcome": "null",
        "delivered": "[]",
        **overrides,
    }
    return ("{" + ", ".join(f'"{k}": {v}' for k, v in fields.items()) + "}").encode()


def lock_path(root: Path) -> Path:
    return root / IDS_RELATIVE.parent / "lock"


class ForeignLock:
    """Verrou tenu par un AUTRE descripteur : simule ``start`` en plein travail."""

    def __init__(self, root: Path) -> None:
        path = lock_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)

    def release(self) -> None:
        os.close(self.fd)


def is_locked_by_someone(root: Path) -> bool:
    """Vrai si un autre descripteur détient le verrou (essai non bloquant)."""
    fd = os.open(lock_path(root), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)
    return False


class TickingClock:
    """Horloge monotone qui n'avance que lorsque le hook dort (poll du verrou)."""

    def __init__(self, on_sleep: Callable[[int], None] | None = None) -> None:
        self.now = 500.0
        self.sleeps = 0
        self.on_sleep = on_sleep

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(self.sleeps)


def locked_ctx(
    tmp_path: Path,
    handler: Handler,
    clock: TickingClock,
    recorder: Recorder,
    *,
    job: Descriptor = DNF5_DESC,
    env: Mapping[str, str] | None = None,
) -> tuple[Ctx, FakeRunner]:
    runner = FakeRunner(handler)
    ctx = ctx_for(
        runner,
        tmp_path,
        recorder,
        euid=0,
        job=job,
        env=env or end_env(),
        monotonic=clock,
    )
    ctx.sleep = clock.sleep
    return ctx, runner


FLATPAK_GUARD = "fedora-post-install-flatpak-auto-guard.service"


FLATPAK_WATCHED = "flatpak-automatic.service"


FLATPAK = "/usr/bin/flatpak"
FLATPAK_LIST_ARGV = [FLATPAK, "list", "--system", "--columns=ref,active:f"]


LISTING_BA = (
    "app/org.example.Beta/x86_64/stable\tdef456\n"
    "app/org.example.Alpha/x86_64/stable\tabc123\n"
)


LISTING_AB = (
    "app/org.example.Alpha/x86_64/stable\tabc123\n"
    "app/org.example.Beta/x86_64/stable\tdef456\n"
)


HASH_AB = "83a1c94a355dda13cbab3b1c251002c93d1030c3d14161fcafbdb44889d2a7d5"


HASH_OTHER = "0" * 63 + "1"


def flatpak_handler(
    *,
    sessions: Mapping[str, Mapping[str, str]] | None = None,
    listings: Sequence[Reply] = ((0, ""),),
    running: Reply = (0, "running\n"),
    active: Mapping[str, str] | None = None,
) -> Handler:
    """Simule le poste pour Flatpak : ``flatpak list`` rend ``listings`` en séquence.

    Le dernier élément de ``listings`` se répète ; ``active`` donne l'état
    ``is-active`` de chaque unité (``inactive`` par défaut).
    """
    base = system_handler(sessions=sessions, running=running)
    pending = list(listings)
    states = active or {}

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if argv == FLATPAK_LIST_ARGV:
            return answer(pending.pop(0) if len(pending) > 1 else pending[0])
        if argv[:2] == [SYSTEMCTL, "is-active"]:
            return 0, states.get(argv[2], "inactive") + "\n"
        return base(argv)

    return handler


def before_path(root: Path) -> Path:
    return root / "run/fedora-post-install/flatpak-auto/before"


def run_flatpak(
    tmp_path: Path,
    verbs: Sequence[str],
    handler: Handler,
    *,
    env: Mapping[str, str] | None = None,
    euid: int = 0,
) -> tuple[FakeRunner, Recorder, list[int]]:
    """Rejoue des verbes du hook pour ``flatpak-auto`` sur une même racine."""
    if not (tmp_path / "proc/sys/kernel/random/boot_id").exists():
        write_boot_id(tmp_path, BOOT_A)
    runner = FakeRunner(handler)
    recorder = Recorder()
    codes = [
        main(
            [verb, "flatpak-auto"],
            ctx_for(
                runner, tmp_path, recorder, euid=euid, job=FLATPAK_DESC, env=env or {}
            ),
        )
        for verb in verbs
    ]
    return runner, recorder, codes


def write_flatpak_state(root: Path, **overrides: object) -> None:
    state: dict[str, object] = {
        "boot_id": BOOT_A,
        "started_at": 1000.0,
        "status": "running",
        "outcome": None,
        "delivered": [],
    }
    state.update(overrides)
    path = root / "var/lib/fedora-post-install/flatpak-auto/state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def write_before(root: Path, digest: str) -> None:
    before_path(root).parent.mkdir(parents=True, exist_ok=True)
    before_path(root).write_text(digest + "\n")


def end_flatpak(
    tmp_path: Path,
    *,
    before: str | None = HASH_AB,
    listings: Sequence[Reply] = ((0, LISTING_AB),),
    result: str = "success",
    running: Reply = (0, "running\n"),
    with_state: bool = True,
    sessions: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[FakeRunner, Recorder]:
    """Rejoue ``end flatpak-auto`` après un lancement, avant / après fournis."""
    write_boot_id(tmp_path, BOOT_A)
    if with_state:
        write_flatpak_state(tmp_path)
    if before is not None:
        write_before(tmp_path, before)
    handler = flatpak_handler(
        sessions={"1": ALICE_PROPS} if sessions is None else sessions,
        listings=listings,
        running=running,
    )
    runner = FakeRunner(handler)
    recorder = Recorder()
    ctx = ctx_for(
        runner, tmp_path, recorder, euid=0, job=FLATPAK_DESC, env=end_env(result)
    )
    assert main(["end", "flatpak-auto"], ctx) == 0
    return runner, recorder


def sent_texts(runner: FakeRunner) -> list[tuple[str, str]]:
    return [
        (parse_notify(a)["summary"], parse_notify(a)["body"])
        for a in notify_calls(runner)
    ]


def id_path(root: Path, uid: int) -> Path:
    return root / "run" / "user" / str(uid) / "fedora-post-install" / "dnf5-auto.id"


def write_id(root: Path, uid: int, content: bytes, mode: int = 0o600) -> Path:
    path = id_path(root, uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def files_under(root: Path) -> dict[str, str]:
    """Contenu texte de chaque fichier sous ``root`` (clé : chemin relatif)."""
    return {
        str(path.relative_to(root)): path.read_text()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
