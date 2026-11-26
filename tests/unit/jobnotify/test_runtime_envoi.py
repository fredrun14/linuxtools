"""Tests du runtime : sessions graphiques, envoi, fichier d'ID utilisateur."""

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from linuxtools.jobnotify.runtime import (
    BUSCTL,
    CALL_TIMEOUT_S,
    ENV_BIN,
    LOGINCTL,
    RUNUSER,
    Session,
    list_graphical_sessions,
    read_user_notification_id,
    send_notification,
)
from tests.unit.jobnotify.runtime_support import (
    ALICE,
    START_BODY,
    START_SUMMARY,
    FakeRunner,
    Recorder,
    id_path,
    loginctl_handler,
    make_ctx,
    props,
    write_id,
)


@pytest.mark.parametrize(
    "uid",
    ["0", "-1", "abc", "", "999", "1000.5", "²", "99999999999999999999"],
    ids=[
        "root",
        "negatif",
        "non_numerique",
        "vide",
        "uid_systeme",
        "decimal",
        "chiffre_non_ascii",
        "trop_grand",
    ],
)
def test_session_de_root_ou_uid_invalide_ignoree(tmp_path: Path, uid: str) -> None:
    recorder = Recorder()
    runner = FakeRunner(loginctl_handler({"1": props(uid=uid, name="root")}))

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, recorder))

    assert sessions == []


def test_session_au_nom_vide_ignoree(tmp_path: Path) -> None:
    runner = FakeRunner(loginctl_handler({"1": props(name="")}))

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert sessions == []


def test_session_a_l_identifiant_suspect_ignoree(tmp_path: Path) -> None:
    runner = FakeRunner(loginctl_handler({"--help": props()}))

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert sessions == []
    assert all(argv[1] != "show-session" for argv, _ in runner.calls)


def test_sessions_graphiques_filtre_type_class_remote(tmp_path: Path) -> None:
    runner = FakeRunner(
        loginctl_handler(
            {
                "1": props(uid="1000", name="alice", type_="wayland"),
                "2": props(uid="1001", name="bob", type_="x11"),
                "3": props(uid="1002", name="tty", type_="tty"),
                "4": props(uid="1003", name="greeter", class_="greeter"),
                "5": props(uid="1004", name="ssh", remote="yes"),
                "6": props(uid="1005", name="mir", type_="mir"),
            },
        ),
    )

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert sessions == [Session(1000, "alice"), Session(1001, "bob")]


def test_sessions_graphiques_ecarte_closing_garde_active_et_online(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        loginctl_handler(
            {
                "1": props(uid="1000", name="alice", state="active"),
                "2": props(uid="1001", name="bob", state="online"),
                "3": props(uid="1002", name="carol", state="closing"),
            },
        ),
    )

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert sessions == [Session(1000, "alice"), Session(1001, "bob")]


def test_sessions_graphiques_dedupliquees_par_uid(tmp_path: Path) -> None:
    runner = FakeRunner(
        loginctl_handler(
            {
                "1": props(uid="1000", name="alice", type_="wayland"),
                "2": props(uid="1000", name="alice", type_="x11"),
            },
        ),
    )

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert sessions == [Session(1000, "alice")]


def test_sessions_graphiques_ligne_vide_ignoree(tmp_path: Path) -> None:
    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if argv[1] == "list-sessions":
            return 0, "\n   \n"
        return 1, ""

    sessions = list_graphical_sessions(
        make_ctx(FakeRunner(handler), tmp_path, Recorder()),
    )

    assert sessions == []


def test_sessions_graphiques_appels_en_chemin_absolu_avec_timeout(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(loginctl_handler({"1": props()}))

    list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert runner.calls == [
        ([LOGINCTL, "list-sessions", "--no-legend"], CALL_TIMEOUT_S),
        (
            [
                LOGINCTL,
                "show-session",
                "1",
                "-p",
                "State",
                "-p",
                "Type",
                "-p",
                "Class",
                "-p",
                "Remote",
                "-p",
                "Name",
                "-p",
                "User",
            ],
            CALL_TIMEOUT_S,
        ),
    ]
    assert LOGINCTL == "/usr/bin/loginctl"
    assert CALL_TIMEOUT_S <= 5


def test_sessions_graphiques_list_sessions_en_echec_ecrit_sur_stderr(
    tmp_path: Path,
) -> None:
    recorder = Recorder()
    runner = FakeRunner(lambda argv: (1, ""))

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, recorder))

    assert sessions == []
    assert len(recorder.messages) == 1
    assert recorder.messages[0].endswith("\n")


def test_sessions_graphiques_show_session_en_echec_ignore_la_session(
    tmp_path: Path,
) -> None:
    recorder = Recorder()

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if argv[1] == "list-sessions":
            return 0, "1 1000 alice seat0\n2 1001 bob seat0\n"
        if argv[2] == "1":
            return 1, ""
        return 0, "".join(
            f"{k}={v}\n" for k, v in props(uid="1001", name="bob").items()
        )

    sessions = list_graphical_sessions(
        make_ctx(FakeRunner(handler), tmp_path, recorder),
    )

    assert sessions == [Session(1001, "bob")]
    assert len(recorder.messages) == 1


@pytest.mark.parametrize(
    "erreur",
    [subprocess.TimeoutExpired(cmd="loginctl", timeout=5), OSError("absent")],
    ids=["timeout", "oserror"],
)
def test_sessions_graphiques_runner_qui_leve_ecrit_sur_stderr(
    tmp_path: Path,
    erreur: Exception,
) -> None:
    recorder = Recorder()

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        raise erreur

    sessions = list_graphical_sessions(
        make_ctx(FakeRunner(handler), tmp_path, recorder),
    )

    assert sessions == []
    assert len(recorder.messages) == 1


def test_aucune_session_graphique_aucun_envoi(tmp_path: Path) -> None:
    runner = FakeRunner(loginctl_handler({}))

    sessions = list_graphical_sessions(make_ctx(runner, tmp_path, Recorder()))

    assert sessions == []
    assert len(runner.calls) == 1


def notify_argv(
    user: str,
    uid: int,
    *,
    replaces_id: str,
    summary: str,
    body: str,
    hints: Sequence[str],
) -> list[str]:
    """Argv attendu, écrit à la main (jamais recalculé comme le code)."""
    return [
        "/usr/bin/runuser",
        "-u",
        user,
        "--",
        "/usr/bin/env",
        "-i",
        f"XDG_RUNTIME_DIR=/run/user/{uid}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
        "/usr/bin/busctl",
        "--user",
        "call",
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
        "Notify",
        "susssasa{sv}i",
        "fedora-post-install",
        replaces_id,
        "system-software-update",
        summary,
        body,
        "0",
        *hints,
        "0",
    ]


def test_send_notification_argv_exact_sans_shell(tmp_path: Path) -> None:
    runner = FakeRunner(lambda argv: (0, "u 42\n"))

    notif_id = send_notification(
        make_ctx(runner, tmp_path, Recorder()),
        ALICE,
        summary=START_SUMMARY,
        body=START_BODY,
        persistent=True,
    )

    assert notif_id == 42
    assert runner.calls == [
        (
            notify_argv(
                "alice",
                1000,
                replaces_id="0",
                summary="Mise à jour automatique en cours",
                body=(
                    "N'éteignez pas le poste et ne le mettez pas en veille "
                    "jusqu'à la fin de la mise à jour."
                ),
                hints=["1", "urgency", "y", "2"],
            ),
            CALL_TIMEOUT_S,
        ),
    ]
    assert (RUNUSER, ENV_BIN, BUSCTL) == (
        "/usr/bin/runuser",
        "/usr/bin/env",
        "/usr/bin/busctl",
    )


def test_send_notification_environnement_minimal_env_i(tmp_path: Path) -> None:
    runner = FakeRunner(lambda argv: (0, "u 9\n"))

    send_notification(
        make_ctx(runner, tmp_path, Recorder()),
        ALICE,
        summary="s",
        body="b",
        persistent=False,
    )

    argv, _ = runner.calls[0]
    # runuser -u alice -- /usr/bin/env -i <variables> /usr/bin/busctl ...
    assert argv[:7] == [
        "/usr/bin/runuser",
        "-u",
        "alice",
        "--",
        "/usr/bin/env",
        "-i",
        "XDG_RUNTIME_DIR=/run/user/1000",
    ]
    assert argv[7] == "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
    assert argv[8] == "/usr/bin/busctl"
    # Aucune variable du service root ne doit traverser vers l'utilisateur.
    assignments = [arg for arg in argv[6:8] if "=" in arg]
    assert len(assignments) == 2
    joined = "\n".join(argv)
    assert "SERVICE_RESULT" not in joined
    assert "INVOCATION_ID" not in joined
    assert not any(arg.startswith("PATH=") for arg in argv)


def test_send_notification_injection_dans_le_nom_utilisateur_reste_un_seul_argument(
    tmp_path: Path,
) -> None:
    hostile = Session(uid=1000, user="a; rm -rf /")
    runner = FakeRunner(lambda argv: (0, "u 7\n"))

    send_notification(
        make_ctx(runner, tmp_path, Recorder()),
        hostile,
        summary="s",
        body="b",
        persistent=False,
    )

    argv, _ = runner.calls[0]
    assert argv[:4] == ["/usr/bin/runuser", "-u", "a; rm -rf /", "--"]
    assert argv.count("a; rm -rf /") == 1
    assert all(isinstance(arg, str) for arg in argv)
    assert argv[0].startswith("/usr/")


def test_send_notification_remplace_l_id_fourni(tmp_path: Path) -> None:
    runner = FakeRunner(lambda argv: (0, "u 43\n"))

    notif_id = send_notification(
        make_ctx(runner, tmp_path, Recorder()),
        ALICE,
        summary="Fin",
        body="Corps",
        replaces_id=42,
        persistent=False,
    )

    assert notif_id == 43
    assert runner.calls[0][0] == notify_argv(
        "alice",
        1000,
        replaces_id="42",
        summary="Fin",
        body="Corps",
        hints=["1", "urgency", "y", "1"],
    )


@pytest.mark.parametrize(
    ("rc", "out"),
    [
        (1, "u 5\n"),
        (0, ""),
        (0, "s 5\n"),
        (0, "u\n"),
        (0, "u cinq\n"),
        (0, "u -3\n"),
        (0, "u 5 6\n"),
        (0, "u ²\n"),
    ],
    ids=[
        "rc_non_nul",
        "sortie_vide",
        "mauvais_type",
        "sans_valeur",
        "non_numerique",
        "negatif",
        "valeurs_en_trop",
        "chiffre_non_ascii",
    ],
)
def test_envoi_echoue_ecrit_sur_stderr(tmp_path: Path, rc: int, out: str) -> None:
    recorder = Recorder()
    runner = FakeRunner(lambda argv: (rc, out))

    notif_id = send_notification(
        make_ctx(runner, tmp_path, recorder),
        ALICE,
        summary="s",
        body="b",
        persistent=True,
    )

    assert notif_id is None
    assert len(recorder.messages) == 1
    assert "alice" in recorder.messages[0]
    assert recorder.messages[0].endswith("\n")


@pytest.mark.parametrize(
    "erreur",
    [subprocess.TimeoutExpired(cmd="busctl", timeout=5), OSError("absent")],
    ids=["timeout", "oserror"],
)
def test_envoi_runner_qui_leve_ecrit_sur_stderr(
    tmp_path: Path,
    erreur: Exception,
) -> None:
    recorder = Recorder()

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        raise erreur

    notif_id = send_notification(
        make_ctx(FakeRunner(handler), tmp_path, recorder),
        ALICE,
        summary="s",
        body="b",
        persistent=True,
    )

    assert notif_id is None
    assert len(recorder.messages) == 1


def current_session(tmp_path: Path) -> Session:
    return Session(uid=os.getuid(), user="u")


def noop_runner() -> FakeRunner:
    return FakeRunner(lambda argv: (1, ""))


@pytest.mark.parametrize(
    ("content", "attendu"),
    [
        (b"42", 42),
        (b"42\n", 42),
        (b"1", 1),
        (b"4294967295", 2**32 - 1),
    ],
    ids=["nu", "retour_ligne", "borne_basse", "borne_haute"],
)
def test_read_user_notification_id_valeurs_valides(
    tmp_path: Path,
    content: bytes,
    attendu: int,
) -> None:
    session = current_session(tmp_path)
    write_id(tmp_path, session.uid, content)

    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        session,
    )

    assert notif_id == attendu


@pytest.mark.parametrize(
    "content",
    [
        b"0",
        b"4294967296",
        b"-5",
        b"abc",
        b"",
        b"\n",
        b"4 2",
        b"\xff\xfe",
        b"1" * 17,
        b"0" * 4096,
        "²".encode(),
    ],
    ids=[
        "zero",
        "au_dessus_de_2_puissance_32",
        "negatif",
        "non_numerique",
        "vide",
        "retour_ligne_seul",
        "deux_valeurs",
        "octets_non_utf8",
        "dix_sept_octets",
        "gros_fichier",
        "chiffre_non_ascii",
    ],
)
def test_read_user_notification_id_refuse_lien_symbolique_gros_fichier_hors_bornes(
    tmp_path: Path,
    content: bytes,
) -> None:
    session = current_session(tmp_path)
    write_id(tmp_path, session.uid, content)

    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        session,
    )

    assert notif_id is None


def test_read_user_notification_id_refuse_lien_symbolique(tmp_path: Path) -> None:
    session = current_session(tmp_path)
    cible = tmp_path / "cible"
    cible.write_bytes(b"42")
    chemin = id_path(tmp_path, session.uid)
    chemin.parent.mkdir(parents=True)
    chemin.symlink_to(cible)

    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        session,
    )

    assert notif_id is None


def test_read_user_notification_id_refuse_mauvais_proprietaire(
    tmp_path: Path,
) -> None:
    session = current_session(tmp_path)
    write_id(tmp_path, session.uid, b"42")
    autre = Session(uid=session.uid + 1, user="autre")
    # Le fichier existe pour ``session`` ; on le range sous l'uid de ``autre``.
    destination = id_path(tmp_path, autre.uid)
    destination.parent.mkdir(parents=True)
    id_path(tmp_path, session.uid).rename(destination)

    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        autre,
    )

    assert notif_id is None


def test_read_user_notification_id_refuse_fichier_non_regulier(
    tmp_path: Path,
) -> None:
    session = current_session(tmp_path)
    chemin = id_path(tmp_path, session.uid)
    chemin.parent.mkdir(parents=True)
    os.mkfifo(chemin)

    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        session,
    )

    assert notif_id is None


def test_read_user_notification_id_fichier_absent(tmp_path: Path) -> None:
    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        current_session(tmp_path),
    )

    assert notif_id is None


def test_read_user_notification_id_erreur_de_lecture_donne_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = current_session(tmp_path)
    write_id(tmp_path, session.uid, b"42")

    def lecture_en_echec(fd: int, length: int) -> bytes:
        raise OSError("EIO")

    monkeypatch.setattr(os, "read", lecture_en_echec)

    notif_id = read_user_notification_id(
        make_ctx(noop_runner(), tmp_path, Recorder()),
        session,
    )

    assert notif_id is None


def test_sessions_graphiques_show_session_qui_leve_ignore_la_session(
    tmp_path: Path,
) -> None:
    recorder = Recorder()

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if argv[1] == "list-sessions":
            return 0, "1 1000 alice seat0\n"
        raise OSError("absent")

    sessions = list_graphical_sessions(
        make_ctx(FakeRunner(handler), tmp_path, recorder),
    )

    assert sessions == []
    assert len(recorder.messages) == 1
