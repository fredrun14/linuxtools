"""Acceptation (A-04 à A-07) : un job fictif décrit par ses seules données.

La chaîne est complète : `NotifiedJobInstaller.sync()` écrit réellement sous
`tmp_path` ; les commandes `Exec…=` sont relues dans les unités écrites ; le
`runtime` INSTALLÉ (copie sur disque, descripteur voisin) est lancé via `main`
avec un `Ctx` de test. Le descripteur n'est jamais injecté : `main` le charge
depuis le fichier écrit par l'installeur, donc un champ mal sérialisé ou mal relu
fait échouer ces tests. Le job ne porte aucune logique, uniquement des données.
"""

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.jobnotify.installer import NotifiedJobInstaller
from linuxtools.jobnotify.runtime import BUSCTL, SYSTEMCTL, Ctx, main
from linuxtools.jobnotify.spec import NoProbe, NotifiedJob, Outcome
from linuxtools.logging.base import Logger
from linuxtools.systemd.executor import SystemdExecutor, UserSystemdExecutor
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BOOT_A,
    FakeRunner,
    Recorder,
    Reply,
    ctx_for,
    system_handler,
    write_boot_id,
)

OWNER_UID = os.geteuid()  # les fichiers de test appartiennent à l'utilisateur réel
GUARD = "demo-app-demo-guard.service"
START = ("Sauvegarde démarrée", "Ne coupez pas le poste.")
END_SUCCESS = ("Sauvegarde terminée", "Tout est enregistré.")
END_FAILURE = ("Sauvegarde en échec", "Consultez le journal.")
END_INTERRUPTED = ("Sauvegarde interrompue", "Elle n'a pas abouti.")
# Ligne d'exécution d'unité ou d'autostart :
# `Exec…=[-]/usr/bin/python3 -I <chemin> <verbe> <job>`.
EXEC_RE = re.compile(r"^Exec\w*=-?/usr/bin/python3 -I (\S+) (\w+) (\S+)$", re.MULTILINE)
ENV_RE = re.compile(r"^Environment=(.+)$", re.MULTILINE)


def demo_job(*, scope: str = "system", lock: bool = True) -> NotifiedJob:
    """Job fictif : uniquement des données, aucune logique propre."""
    return NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="user" if scope == "user" else "system",
        start_texts=START,
        end_texts={
            Outcome.SUCCESS: END_SUCCESS,
            Outcome.FAILURE: END_FAILURE,
            Outcome.INTERRUPTED: END_INTERRUPTED,
        },
        lock=lock,
        probe=NoProbe(),
    )


def install_system(tmp_path: Path, *, lock: bool) -> NotifiedJobInstaller:
    """Installe le job fictif (scope système) sous `tmp_path`."""
    systemd = MagicMock(spec=SystemdExecutor)
    systemd.get_status.return_value = "inactive"
    systemd.reload_systemd.return_value = True
    installer = NotifiedJobInstaller(
        demo_job(lock=lock), systemd, MagicMock(spec=Logger), root_dir=tmp_path
    )
    installer.sync(enabled=True, dry_run=False)
    return installer


def install_user(
    home: Path, env: Mapping[str, str] | None = None
) -> NotifiedJobInstaller:
    """Installe le job fictif (scope user) sous le `home` de test.

    `env` est l'environnement de la session de l'utilisateur (XDG personnalisés).
    """
    systemd = MagicMock(spec=UserSystemdExecutor)
    systemd.get_status.return_value = "inactive"
    systemd.reload_systemd.return_value = True
    installer = NotifiedJobInstaller(
        demo_job(scope="user", lock=False),
        systemd,
        MagicMock(spec=Logger),
        home=home,
        env={} if env is None else env,
    )
    installer.sync(enabled=True, dry_run=False)
    return installer


def exec_lines(*unit_files: Path) -> list[tuple[str, str]]:
    """(chemin du runtime, verbe) de chaque ligne d'exécution des fichiers écrits.

    Le nom du job (dernier argument, F07) doit être celui du job fictif : il est
    vérifié ici, car le runtime refuse tout appel dont le job diffère du sien.
    """
    found = [
        (script, verb, job)
        for unit in unit_files
        for script, verb, job in EXEC_RE.findall(unit.read_text())
    ]
    assert {job for _, _, job in found} <= {"demo"}
    return [(script, verb) for script, verb, _ in found]


def demo_runner(
    *,
    sessions: Mapping[str, Mapping[str, str]] | None = None,
    notify: Reply | None = None,
) -> FakeRunner:
    """Poste simulé : loginctl, busctl, `systemctl` (système ou `--user`)."""
    base = system_handler(sessions=sessions, notify=notify)

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        args = [a for a in argv if a != "--user"] if argv[0] == SYSTEMCTL else argv
        return base(list(args)) if args[0] == SYSTEMCTL else base(argv)

    return FakeRunner(handler)


def installed_ctx(
    runner: FakeRunner,
    root: Path,
    script: Path,
    recorder: Recorder,
    *,
    euid: int,
    env: Mapping[str, str],
) -> Ctx:
    """Contexte du runtime installé : aucun descripteur injecté (lu sur disque)."""
    ctx = ctx_for(runner, root, recorder, euid=euid, env=env)
    ctx.descriptor = None
    ctx.script = script
    return ctx


def notifications(runner: FakeRunner) -> list[tuple[str, str, str]]:
    """(remplace, résumé, corps) de chaque notification `busctl` envoyée."""
    sent: list[tuple[str, str, str]] = []
    for argv, _ in runner.calls:
        if BUSCTL in argv:
            i = argv.index("demo-app")
            sent.append((argv[i + 1], argv[i + 3], argv[i + 4]))
    return sent


def system_script(root: Path, real: str) -> Path:
    """Runtime installé : le chemin réel des unités, vu sous la racine de test."""
    return root / real.lstrip("/")


def test_job_fictif_recoit_debut_fin_login(tmp_path: Path) -> None:
    # Arrange : installation réelle avec verrou, boot courant connu
    install_system(tmp_path, lock=True)
    write_boot_id(tmp_path, BOOT_A)
    etc = tmp_path / "etc"
    guard = etc / "systemd/system" / GUARD
    dropin = etc / "systemd/system/demo.service.d/demo-app-notify.conf"
    desktop = etc / "xdg/autostart/demo-app-demo-notify.desktop"
    assert exec_lines(guard) == [("/usr/local/libexec/demo-app/demo-notify", "start")]
    assert exec_lines(dropin) == [("/usr/local/libexec/demo-app/demo-notify", "end")]
    assert exec_lines(desktop) == [("/usr/local/libexec/demo-app/demo-notify", "login")]
    real = "/usr/local/libexec/demo-app/demo-notify"
    script = system_script(tmp_path, real)
    runner = demo_runner(sessions={"1": ALICE_PROPS})
    recorder = Recorder()

    # Act : début (compagnon), fin (service), puis login de bob (autre session)
    codes = [
        main(
            ["start"],
            installed_ctx(runner, tmp_path, script, recorder, euid=0, env={}),
        ),
        main(
            ["end"],
            installed_ctx(
                runner,
                tmp_path,
                script,
                recorder,
                euid=0,
                env={"SERVICE_RESULT": "success"},
            ),
        ),
    ]
    login_runner = demo_runner()
    codes.append(
        main(
            ["login"],
            installed_ctx(
                login_runner,
                tmp_path,
                script,
                recorder,
                euid=1001,
                env={"XDG_STATE_HOME": str(tmp_path / "state")},
            ),
        )
    )

    # Assert : textes du descripteur écrit, dans l'ordre début, fin (remplace), login
    assert codes == [0, 0, 0]
    assert notifications(runner) == [
        ("0", *START),
        ("42", *END_SUCCESS),
    ]
    first_systemctl = next(a for a, _ in runner.calls if a[0] == SYSTEMCTL)
    assert first_systemctl[:3] == [SYSTEMCTL, "stop", GUARD]
    assert notifications(login_runner) == [("0", *END_SUCCESS)]
    assert recorder.messages == []


def test_job_fictif_sans_verrou_ne_pose_aucun_inhibiteur(tmp_path: Path) -> None:
    # Arrange
    install_system(tmp_path, lock=False)
    write_boot_id(tmp_path, BOOT_A)
    written = {
        str(p.relative_to(tmp_path)): p.read_text()
        for p in tmp_path.rglob("*")
        if p.is_file() and "proc" not in p.parts
    }
    dropin = tmp_path / "etc/systemd/system/demo.service.d/demo-app-notify.conf"
    real = "/usr/local/libexec/demo-app/demo-notify"
    script = system_script(tmp_path, real)
    runner = demo_runner(sessions={"1": ALICE_PROPS})
    recorder = Recorder()

    # Assert (artefacts) : aucun compagnon ni inhibiteur, début par le drop-in
    assert not list((tmp_path / "etc/systemd/system").glob("*.service"))
    assert all("systemd-inhibit" not in text for text in written.values())
    assert "Wants=" not in dropin.read_text()
    assert exec_lines(dropin) == [(real, "start"), (real, "end")]

    # Act : le drop-in lance start puis end
    codes = [
        main(
            [verb, "demo"],
            installed_ctx(
                runner,
                tmp_path,
                script,
                recorder,
                euid=0,
                env={"SERVICE_RESULT": "success"},
            ),
        )
        for _, verb in exec_lines(dropin)
    ]

    # Assert : mêmes notifications, rien arrêté, aucun inhibiteur appelé
    assert codes == [0, 0]
    assert notifications(runner) == [("0", *START), ("42", *END_SUCCESS)]
    assert all("stop" not in argv for argv, _ in runner.calls)
    assert all("systemd-inhibit" not in " ".join(a) for a, _ in runner.calls)
    assert recorder.messages == []


@pytest.mark.parametrize(
    ("xdg", "data", "config", "state"),
    [
        ({}, ".local/share", ".config", ".local/state"),
        (
            {
                "XDG_DATA_HOME": "donnees",
                "XDG_CONFIG_HOME": "reglages",
                "XDG_STATE_HOME": "etat",
            },
            "donnees",
            "reglages",
            "etat",
        ),
    ],
    ids=["xdg_par_defaut", "xdg_personnalises"],
)
def test_job_fictif_scope_user_debut_fin_login(
    tmp_path: Path,
    xdg: Mapping[str, str],
    data: str,
    config: str,
    state: str,
) -> None:
    # Arrange : la session de l'utilisateur définit (ou non) des dossiers XDG ;
    # l'installeur et le login de l'autostart voient la MÊME session (A-06, F03).
    home = tmp_path / "home"
    home.mkdir()
    session = {"HOME": str(home), **{k: str(home / v) for k, v in xdg.items()}}
    install_user(home, session)
    write_boot_id(tmp_path, BOOT_A)
    script = home / data / "demo-app/demo-notify"
    dropin = home / config / "systemd/user/demo.service.d/demo-app-notify.conf"
    desktop = home / config / "autostart/demo-app-demo-notify.desktop"
    assert script.is_file()
    assert script.with_name("demo-notify.json").is_file()
    assert exec_lines(dropin) == [(str(script), "start"), (str(script), "end")]
    assert exec_lines(desktop) == [(str(script), "login")]
    # Environnement des unités relu du drop-in écrit, plus le bus ; le login de
    # l'autostart, lui, n'a que l'environnement de la session (jamais celui de l'unité).
    unit_env = dict(
        item.split("=", 1)
        for line in ENV_RE.findall(dropin.read_text())
        for item in line.split()
    )
    bus = {"XDG_RUNTIME_DIR": str(tmp_path / "run")}
    unit_ctx_env = {**unit_env, **bus}
    login_env = {**session, **bus}
    recorder = Recorder()

    # Act : début, fin sans bureau (busctl échoue), puis login qui rattrape
    start_runner = demo_runner()
    end_runner = demo_runner(notify=(1, ""))
    login_runner = demo_runner()
    codes = [
        main(
            ["start"],
            installed_ctx(
                start_runner,
                tmp_path,
                script,
                recorder,
                euid=OWNER_UID,
                env=unit_ctx_env,
            ),
        ),
        main(
            ["end"],
            installed_ctx(
                end_runner,
                tmp_path,
                script,
                recorder,
                euid=OWNER_UID,
                env={**unit_ctx_env, "SERVICE_RESULT": "success"},
            ),
        ),
        main(
            ["login"],
            installed_ctx(
                login_runner,
                tmp_path,
                script,
                recorder,
                euid=OWNER_UID,
                env=login_env,
            ),
        ),
    ]

    # Assert : le login relit l'état écrit par start/end, donc rattrape la fin
    assert codes == [0, 0, 0]
    assert notifications(start_runner) == [("0", *START)]
    assert notifications(login_runner) == [("0", *END_SUCCESS)]
    assert [a[0] for a, _ in start_runner.calls] == [BUSCTL]  # ni loginctl ni runuser
    assert (home / state / "demo-app/demo/state.json").is_file()
    assert (home / state / "demo-app/demo/seen").is_file()


@pytest.mark.parametrize(
    "failure",
    [(1, ""), OSError("busctl introuvable")],
    ids=["busctl_en_echec", "busctl_absent"],
)
def test_job_fictif_echec_bureau_ne_fait_pas_echouer_le_job(
    tmp_path: Path, failure: Reply
) -> None:
    # Arrange
    install_system(tmp_path, lock=True)
    write_boot_id(tmp_path, BOOT_A)
    script = system_script(tmp_path, "/usr/local/libexec/demo-app/demo-notify")
    runner = demo_runner(sessions={"1": ALICE_PROPS}, notify=failure)
    recorder = Recorder()

    # Act : chaque verbe lancé par les unités écrites, avec un bureau en échec
    codes = [
        main(
            [verb, "demo"],
            installed_ctx(
                runner,
                tmp_path,
                script,
                recorder,
                euid=0 if verb != "login" else 1001,
                env={
                    "SERVICE_RESULT": "success",
                    "XDG_STATE_HOME": str(tmp_path / "s"),
                },
            ),
        )
        for verb in ("start", "end", "login")
    ]

    # Assert : le job n'échoue pas, rien ne remonte, la fin reste tentée
    assert codes == [0, 0, 0]
    assert any(argv[:2] == [SYSTEMCTL, "stop"] for argv, _ in runner.calls)
