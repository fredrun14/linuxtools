"""Tests du cycle du runtime : main, default_runner, start, end."""

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from linuxtools.jobnotify.runtime import (
    BUSCTL,
    DNF5,
    SYSTEMCTL,
    TOTAL_BUDGET_S,
    Ctx,
    Outcome,
    Session,
    default_runner,
    end,
    main,
    start,
)
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BOB_PROPS,
    BOOT_A,
    BOOT_B,
    DNF5_DESC,
    DNF5_JOB,
    END_TEXTS,
    FLATPAK_DESC,
    GUARD_UNIT,
    START_BODY,
    STATE_KEYS,
    STATE_RELATIVE,
    TRANSACTION_RUN,
    Clock,
    FakeRunner,
    Recorder,
    Reply,
    answer,
    ctx_for,
    end_env,
    files_under,
    make_ctx,
    mode_of,
    notify_calls,
    parse_notify,
    read_state_file,
    root_id_path,
    run_end,
    system_handler,
    write_boot_id,
    write_id,
    write_state_file,
)


@pytest.mark.parametrize(
    "argv",
    [["bogus"], [], ["start", "extra"], ["start"], ["end"], ["login"]],
    ids=["verbe_inconnu", "sans_verbe", "trop_d_arguments", "start", "end", "login"],
)
def test_main_retourne_toujours_zero(tmp_path: Path, argv: list[str]) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)
    recorder = Recorder()
    runner = FakeRunner(lambda a: answer(ValueError("boom")))

    rc = main(argv, ctx_for(runner, tmp_path, recorder, euid=1000))

    assert rc == 0
    assert recorder.messages != []


@pytest.mark.parametrize(
    "exc", [RuntimeError("kaboom"), KeyError("k")], ids=["runtime", "key"]
)
@pytest.mark.parametrize("verb", ["start", "end", "login"])
def test_main_exception_inattendue_rc_zero_et_message(
    tmp_path: Path, verb: str, exc: Exception
) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)
    recorder = Recorder()
    runner = FakeRunner(lambda a: answer(exc))

    rc = main([verb], ctx_for(runner, tmp_path, recorder, euid=1000))

    assert rc == 0
    texte = "".join(recorder.messages)
    assert type(exc).__name__ in texte
    assert verb in texte


@pytest.mark.parametrize("explicit_argv", [True, False], ids=["argv", "sys_argv"])
def test_main_ctx_et_argv_par_defaut(
    explicit_argv: bool,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["dnf5-auto-notify", "bogus"])

    rc = main(["bogus"] if explicit_argv else None)

    assert rc == 0
    assert "invalide" in capfd.readouterr().err


def test_main_sans_job_vaut_dnf5_auto(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    ctx = ctx_for(runner, tmp_path, Recorder(), euid=0)

    rc = main(["start"], ctx)

    assert rc == 0
    assert ctx.descriptor is DNF5_DESC
    assert (tmp_path / "var/lib/fedora-post-install/dnf5-auto/state.json").is_file()


def test_main_job_explicite_dnf5_auto_identique_au_defaut(tmp_path: Path) -> None:
    results = []
    for name, argv in (("defaut", ["start"]), ("explicite", ["start", "dnf5-auto"])):
        root = tmp_path / name
        write_boot_id(root, BOOT_A)
        runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))

        main(argv, ctx_for(runner, root, Recorder(), euid=0))

        results.append((runner.calls, files_under(root)))

    assert results[0] == results[1]
    assert results[0][0] != []


@pytest.mark.parametrize(
    "argv",
    [["start", "evil"], ["end", "../x"], ["start", "dnf5-auto", "x"]],
    ids=["job_inconnu", "job_traversant", "trop_d_arguments"],
)
def test_main_job_inconnu_rc0_sans_action(tmp_path: Path, argv: list[str]) -> None:
    recorder = Recorder()
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))

    rc = main(argv, ctx_for(runner, tmp_path, recorder, euid=0))

    assert rc == 0
    assert len(recorder.messages) == 1
    assert recorder.messages[0].startswith("dnf5-auto-notify : verbe ou job invalide")
    assert runner.calls == []


def test_main_start_nominal_sous_budget(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))

    rc = main(["start"], ctx_for(runner, tmp_path, Recorder(), euid=0))

    assert rc == 0
    assert len(notify_calls(runner)) == 1


def test_budget_depasse_saute_les_etapes_suivantes(tmp_path: Path) -> None:
    write_state_file(tmp_path)
    recorder = Recorder()
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    clock = Clock(0.0, float(TOTAL_BUDGET_S))

    rc = main(["end"], ctx_for(runner, tmp_path, recorder, euid=0, monotonic=clock))

    assert rc == 0
    assert runner.calls == []
    assert any("budget" in m for m in recorder.messages)


def test_budget_ignore_un_saut_de_l_horloge_murale(tmp_path: Path) -> None:
    # L'horloge murale saute d'un jour (NTP, resynchronisation) : le budget,
    # mesuré en monotonic, n'est pas entamé.
    write_state_file(tmp_path)
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    wall = Clock(0.0, 86400.0)

    rc = main(["end"], ctx_for(runner, tmp_path, Recorder(), euid=0, now=wall))

    assert rc == 0
    assert runner.calls != []


def test_budget_ignore_un_recul_de_l_horloge_murale(tmp_path: Path) -> None:
    # L'horloge murale recule : le budget épuisé en monotonic coupe quand même.
    write_state_file(tmp_path)
    recorder = Recorder()
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    wall = Clock(5000.0, 0.0)
    mono = Clock(0.0, float(TOTAL_BUDGET_S))

    rc = main(
        ["end"], ctx_for(runner, tmp_path, recorder, euid=0, now=wall, monotonic=mono)
    )

    assert rc == 0
    assert runner.calls == []
    assert any("budget" in m for m in recorder.messages)


def test_default_runner_commande_reussie_rend_code_et_sortie() -> None:
    assert default_runner(["/usr/bin/echo", "bonjour"], 5) == (0, "bonjour\n")
    assert default_runner(["/usr/bin/true"], 5) == (0, "")


def test_default_runner_commande_en_echec_rend_le_code() -> None:
    assert default_runner(["/usr/bin/false"], 5) == (1, "")


def test_default_runner_commande_inexistante_leve_oserror() -> None:
    with pytest.raises(OSError, match="inexistant"):
        default_runner(["/usr/bin/dnf5-auto-notify-inexistant"], 5)


def test_default_runner_delai_depasse_leve_timeout_expired() -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        default_runner(["/usr/bin/sleep", "5"], 0.05)


def test_default_runner_sans_shell_avec_delai_et_sortie_texte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 3, stdout="sortie")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = default_runner(("/usr/bin/x", "a; b"), 4)

    assert result == (3, "sortie")
    assert seen["argv"] == ["/usr/bin/x", "a; b"]
    assert seen["timeout"] == 4
    assert seen["capture_output"] is True
    assert seen["check"] is False
    assert seen.get("shell", False) is False
    assert seen["stdin"] == subprocess.DEVNULL
    assert seen["encoding"] == "utf-8"
    assert seen["errors"] == "replace"


def test_start_ecrit_etat_running_et_notifie_chaque_session(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    runner = FakeRunner(
        system_handler(sessions={"1": ALICE_PROPS, "2": BOB_PROPS}),
    )

    start(ctx_for(runner, tmp_path, Recorder(), euid=0))

    assert read_state_file(tmp_path) == {
        "boot_id": BOOT_A,
        "started_at": 2000.0,
        "status": "running",
        "outcome": None,
        "delivered": [],
    }
    assert mode_of(tmp_path / STATE_RELATIVE) == 0o644
    users = [argv[2] for argv in notify_calls(runner)]
    assert users == ["alice", "bob"]
    assert root_id_path(tmp_path, 1000).read_text().strip() == "42"
    assert root_id_path(tmp_path, 1001).read_text().strip() == "43"
    assert mode_of(root_id_path(tmp_path, 1000).parent) == 0o700


def test_start_envoie_notification_critique_persistante(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))

    start(ctx_for(runner, tmp_path, Recorder(), euid=0))

    (argv,) = notify_calls(runner)
    assert parse_notify(argv) == {
        "replaces": "0",
        "summary": "Mise à jour automatique en cours",
        "body": START_BODY,
        "urgency": "2",
        "expire": "0",
    }


def test_start_ancien_id_oublie_avant_l_envoi(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    stale = root_id_path(tmp_path, 1000)
    stale.parent.mkdir(parents=True)
    stale.write_text("999\n")
    runner = FakeRunner(
        system_handler(sessions={"1": ALICE_PROPS}, notify=(1, "")),
    )

    start(ctx_for(runner, tmp_path, Recorder(), euid=0))

    assert not stale.exists()


@pytest.mark.parametrize(
    "content",
    [None, "pas un id!\n", "a" * 65, "\n"],
    ids=["absent", "caracteres_invalides", "trop_long", "vide"],
)
def test_start_boot_id_illisible_ecrit_sur_stderr(
    tmp_path: Path,
    content: str | None,
) -> None:
    if content is not None:
        write_boot_id(tmp_path, content.rstrip("\n") if content != "\n" else "")
    recorder = Recorder()
    runner = FakeRunner(system_handler())

    start(ctx_for(runner, tmp_path, recorder, euid=0))

    assert read_state_file(tmp_path)["boot_id"] == ""
    assert any("boot_id" in m for m in recorder.messages)


def test_aucune_session_graphique_aucun_envoi_rc_zero(tmp_path: Path) -> None:
    write_state_file(tmp_path)
    runner = FakeRunner(system_handler(sessions={}))
    recorder = Recorder()

    rc_start = main(["start"], ctx_for(runner, tmp_path, recorder, euid=0))
    rc_end = main(
        ["end"],
        ctx_for(runner, tmp_path, recorder, euid=0, env={"SERVICE_RESULT": "success"}),
    )

    assert (rc_start, rc_end) == (0, 0)
    assert notify_calls(runner) == []
    assert read_state_file(tmp_path)["status"] == "done"


HISTORY_RUN = (0, json.dumps(TRANSACTION_RUN))


def test_end_arrete_le_compagnon_avant_la_notification(tmp_path: Path) -> None:
    write_state_file(tmp_path)

    runner, _ = run_end(tmp_path, history=HISTORY_RUN)

    argvs = [argv for argv, _ in runner.calls]
    stop = [SYSTEMCTL, "stop", "fedora-post-install-dnf5-auto-guard.service"]
    assert GUARD_UNIT == "fedora-post-install-dnf5-auto-guard.service"
    assert argvs.index(stop) < min(i for i, a in enumerate(argvs) if BUSCTL in a)
    assert argvs[0] == stop


def test_end_ecrit_l_etat_terminal_avant_la_premiere_notification(
    tmp_path: Path,
) -> None:
    # F21, E9 : un ``login`` qui relit l'état pendant l'envoi de ``end`` doit
    # déjà voir l'état terminal (sinon sa notification « en cours » reste orpheline).
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)
    base = system_handler(sessions={"1": ALICE_PROPS})
    vus: list[dict[str, object]] = []

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if BUSCTL in argv:
            vus.append(read_state_file(tmp_path))
        return base(argv)

    end(ctx_for(FakeRunner(handler), tmp_path, Recorder(), euid=0, env=end_env()))

    assert vus[0]["status"] == "done"
    assert vus[0]["outcome"] == "nothing"  # historique vide
    assert vus[0]["started_at"] == 1000.0
    assert read_state_file(tmp_path)["delivered"] == [1000]


def test_end_remplace_la_notification_de_lancement(tmp_path: Path) -> None:
    write_state_file(tmp_path)
    root_id = root_id_path(tmp_path, 1000)
    root_id.parent.mkdir(parents=True)
    root_id.write_text("77\n")

    runner, _ = run_end(tmp_path, history=HISTORY_RUN)

    (argv,) = notify_calls(runner)
    summary, body = END_TEXTS[Outcome.SUCCESS]
    assert parse_notify(argv) == {
        "replaces": "77",
        "summary": summary,
        "body": body,
        "urgency": "1",
        "expire": "0",
    }
    assert read_state_file(tmp_path) == {
        "boot_id": BOOT_A,
        "started_at": 1000.0,
        "status": "done",
        "outcome": "success",
        "delivered": [1000],
    }
    assert not root_id.exists()


@pytest.mark.parametrize(
    ("root_id", "root_mtime", "user_id", "user_mtime", "attendu"),
    [
        (None, None, None, None, "0"),
        (None, None, "55", 500.0, "0"),
        (None, None, "55", 2000.0, "55"),
        ("77", 2000.0, None, None, "77"),
        ("77", 500.0, None, None, "0"),
        ("77", 2000.0, "55", 2000.0, "55"),
        ("77", 2000.0, "55", 500.0, "77"),
        ("77", 500.0, "55", 500.0, "0"),
    ],
    ids=[
        "aucun",
        "id_utilisateur_seul_plus_ancien_que_le_run",
        "id_utilisateur_seul_plus_recent_que_le_run",
        "id_root_recent",
        "id_root_d_un_run_precedent",
        "id_utilisateur_et_root_recents",
        "id_utilisateur_ancien_root_recent",
        "id_utilisateur_et_root_anciens",
    ],
)
def test_end_choix_de_l_id_a_remplacer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_id: str | None,
    root_mtime: float | None,
    user_id: str | None,
    user_mtime: float | None,
    attendu: str,
) -> None:
    write_state_file(tmp_path)  # started_at = 1000.0
    if root_id is not None and root_mtime is not None:
        path = root_id_path(tmp_path, os.getuid())
        path.parent.mkdir(parents=True)
        path.write_text(root_id)
        os.utime(path, (root_mtime, root_mtime))
    if user_id is not None and user_mtime is not None:
        written = write_id(tmp_path, os.getuid(), user_id.encode())
        os.utime(written, (user_mtime, user_mtime))
    # Le propriétaire du fichier d'ID doit être l'uid de la session : on utilise
    # l'uid réel du processus de test (la CI tourne en root, uid < 1000).
    monkeypatch.setattr(
        "linuxtools.jobnotify.runtime.list_graphical_sessions",
        lambda ctx: [Session(uid=os.getuid(), user="u")],
    )

    runner, _ = run_end(tmp_path, history=HISTORY_RUN)

    assert parse_notify(notify_calls(runner)[0])["replaces"] == attendu


def test_end_etat_invalide_ne_reutilise_aucun_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sans started_at fiable (état absent), aucun ID ne peut être daté : 0.
    path = root_id_path(tmp_path, os.getuid())
    path.parent.mkdir(parents=True)
    path.write_text("77")
    os.utime(path, (2000.0, 2000.0))
    written = write_id(tmp_path, os.getuid(), b"55")
    os.utime(written, (2000.0, 2000.0))
    monkeypatch.setattr(
        "linuxtools.jobnotify.runtime.list_graphical_sessions",
        lambda ctx: [Session(uid=os.getuid(), user="u")],
    )

    runner, _ = run_end(tmp_path, history=HISTORY_RUN)

    assert parse_notify(notify_calls(runner)[0])["replaces"] == "0"


@pytest.mark.parametrize(
    "history",
    [
        (1, ""),
        (0, "pas du json"),
        (0, '{"a": 1}'),
        (0, "[" * 3000),
        OSError("absent"),
    ],
    ids=[
        "rc_non_nul",
        "json_invalide",
        "pas_une_liste",
        "trop_imbrique",
        "commande_absente",
    ],
)
def test_end_historique_illisible_donne_done_no_detail_et_stderr(
    tmp_path: Path,
    history: Reply,
) -> None:
    write_state_file(tmp_path)

    runner, recorder = run_end(tmp_path, history=history)

    summary, _ = END_TEXTS[Outcome.DONE_NO_DETAIL]
    assert parse_notify(notify_calls(runner)[0])["summary"] == summary
    assert recorder.messages != []
    assert read_state_file(tmp_path)["outcome"] == "done_no_detail"


def test_end_systeme_en_arret_notifie_interruption(tmp_path: Path) -> None:
    write_state_file(tmp_path)

    runner, _ = run_end(tmp_path, running=(1, "stopping\n"))

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.INTERRUPTED][0])
    )
    state = read_state_file(tmp_path)
    assert (state["status"], state["outcome"]) == ("interrupted", "interrupted")
    assert not any(argv[0] == DNF5 for argv, _ in runner.calls)


def test_end_echec_notifie_sans_interroger_dnf(tmp_path: Path) -> None:
    write_state_file(tmp_path)

    runner, _ = run_end(tmp_path, env=end_env("exit-code"))

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.FAILURE][0])
    )
    assert not any(argv[0] == DNF5 for argv, _ in runner.calls)
    assert read_state_file(tmp_path)["status"] == "done"


REBOOT_JSON = (
    '[{"type": "reboot", "reboot_required": true, "packages": ["kernel"], '
    '"documentation": "https://access.redhat.com/solutions/27943"}]'
)


NO_REBOOT_JSON = '[{"type": "reboot", "reboot_required": false, "packages": []}]'


@pytest.mark.parametrize(
    ("needs", "attendu"),
    [
        ((1, REBOOT_JSON), Outcome.SUCCESS_RESTART),
        ((1, NO_REBOOT_JSON), Outcome.SUCCESS),
        ((1, ""), Outcome.SUCCESS),
        ((1, "Échec du téléchargement des métadonnées"), Outcome.SUCCESS),
        ((1, "{}"), Outcome.SUCCESS),
        ((1, "[]"), Outcome.SUCCESS),
        ((1, '[{"type": "reboot"}]'), Outcome.SUCCESS),
        ((1, '[{"type": "unit", "reboot_required": true}]'), Outcome.SUCCESS),
        ((1, "[" * 100_000), Outcome.SUCCESS),
        ((0, ""), Outcome.SUCCESS),
        ((0, NO_REBOOT_JSON), Outcome.SUCCESS),
        ((2, "erreur"), Outcome.SUCCESS),
        (OSError("absent"), Outcome.SUCCESS),
    ],
    ids=[
        "redemarrage",
        "json_sans_redemarrage",
        "rc1_sortie_vide",
        "rc1_texte_d_erreur",
        "rc1_json_objet",
        "rc1_json_tableau_vide",
        "rc1_json_sans_champ",
        "rc1_json_autre_type",
        "rc1_json_trop_imbrique",
        "aucun",
        "rc0_json",
        "erreur_de_dnf",
        "commande_absente",
    ],
)
def test_end_redemarrage_requis_selon_needs_restarting(
    tmp_path: Path,
    needs: Reply,
    attendu: Outcome,
) -> None:
    write_state_file(tmp_path)

    runner, _ = run_end(tmp_path, history=HISTORY_RUN, needs=needs)

    assert parse_notify(notify_calls(runner)[0])["summary"] == END_TEXTS[attendu][0]


def test_end_needs_restarting_demande_json_sans_depots_distants(
    tmp_path: Path,
) -> None:
    write_state_file(tmp_path)

    runner, _ = run_end(tmp_path, history=HISTORY_RUN, needs=(0, ""))

    # `--disablerepo=*` : le résultat ne dépend que du système, pas du réseau.
    expected = [DNF5, "needs-restarting", "--json", "--disablerepo=*"]
    assert expected in [a for a, _ in runner.calls]


@pytest.mark.parametrize(
    ("needs", "ecrit"),
    [
        ((2, "erreur"), True),
        ((1, ""), True),
        ((1, "Échec du téléchargement"), True),
        ((1, "[]"), True),
        ((1, "[" * 100_000), True),
        ((0, ""), False),
        ((1, REBOOT_JSON), False),
        ((1, NO_REBOOT_JSON), False),
    ],
    ids=[
        "rc_inattendu",
        "rc1_vide",
        "rc1_texte",
        "rc1_json_inattendu",
        "rc1_json_trop_imbrique",
        "rc_0",
        "rc1_redemarrage",
        "rc1_json_sans_redemarrage",
    ],
)
def test_end_needs_restarting_anomalie_ecrit_sur_stderr(
    tmp_path: Path,
    needs: Reply,
    ecrit: bool,
) -> None:
    write_state_file(tmp_path)

    _, recorder = run_end(tmp_path, history=HISTORY_RUN, needs=needs)

    assert any("needs-restarting" in m for m in recorder.messages) is ecrit


def test_end_rien_a_mettre_a_jour_ne_lance_pas_needs_restarting(
    tmp_path: Path,
) -> None:
    write_state_file(tmp_path)

    runner, _ = run_end(tmp_path, history=(0, "[]"))

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.NOTHING][0])
    )
    assert not any(a[:2] == [DNF5, "needs-restarting"] for a, _ in runner.calls)


def test_end_sans_etat_donne_done_no_detail(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_B)

    runner, recorder = run_end(tmp_path, history=HISTORY_RUN)

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.DONE_NO_DETAIL][0])
    )
    assert any("état" in m for m in recorder.messages)
    state = read_state_file(tmp_path)
    assert (state["boot_id"], state["started_at"]) == (BOOT_B, 2000.0)


@pytest.mark.parametrize(
    "stale",
    [
        {"status": "done", "outcome": "success"},
        {"boot_id": BOOT_B},
    ],
    ids=["run_precedent_termine", "autre_boot"],
)
def test_end_etat_perime_donne_done_no_detail_sans_started_at_perime(
    tmp_path: Path,
    stale: dict[str, object],
) -> None:
    write_state_file(tmp_path, **stale)  # started_at = 1000.0 : celui du run précédent
    write_boot_id(tmp_path, BOOT_A)

    runner, recorder = run_end(tmp_path, history=HISTORY_RUN)

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.DONE_NO_DETAIL][0])
    )
    assert not any(argv[0] == DNF5 for argv, _ in runner.calls)
    assert any("état" in m for m in recorder.messages)
    state = read_state_file(tmp_path)
    assert (state["boot_id"], state["started_at"]) == (BOOT_A, 2000.0)


def test_end_etat_perime_ne_reutilise_aucun_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_state_file(tmp_path, status="done", outcome="success")  # started_at 1000.0
    root = root_id_path(tmp_path, os.getuid())
    root.parent.mkdir(parents=True)
    root.write_text("77")
    written = write_id(tmp_path, os.getuid(), b"55")
    os.utime(written, (1500.0, 1500.0))  # postérieur au started_at périmé
    monkeypatch.setattr(
        "linuxtools.jobnotify.runtime.list_graphical_sessions",
        lambda ctx: [Session(uid=os.getuid(), user="u")],
    )

    runner, _ = run_end(tmp_path, history=HISTORY_RUN)

    assert parse_notify(notify_calls(runner)[0])["replaces"] == "0"


def test_end_commandes_systemd_en_echec_continue(tmp_path: Path) -> None:
    write_state_file(tmp_path)

    runner, recorder = run_end(
        tmp_path,
        history=HISTORY_RUN,
        running=OSError("absent"),
    )

    assert len(notify_calls(runner)) == 1
    assert recorder.messages != []


def test_end_envoi_echoue_ne_marque_pas_livre(tmp_path: Path) -> None:
    write_state_file(tmp_path)

    _, recorder = run_end(tmp_path, history=HISTORY_RUN, notify=(1, ""))

    assert read_state_file(tmp_path)["delivered"] == []
    assert any("envoi impossible" in m for m in recorder.messages)


def test_etat_ne_contient_que_les_champs_attendus(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    start_runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    start(ctx_for(start_runner, tmp_path, Recorder(), euid=0))
    after_start = (tmp_path / STATE_RELATIVE).read_text()

    run_end(tmp_path, history=HISTORY_RUN)
    after_end = (tmp_path / STATE_RELATIVE).read_text()

    for text in (after_start, after_end):
        assert set(json.loads(text)) == STATE_KEYS
        assert "alice" not in text
        assert str(tmp_path) not in text
        assert "dnf5 automatic" not in text


def test_main_refuse_job_different_du_descripteur(tmp_path: Path) -> None:
    # Q-07 : le descripteur flatpak est chargé, l'argument vise un autre job.
    recorder = Recorder()
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    ctx = ctx_for(runner, tmp_path, recorder, euid=0, job=FLATPAK_DESC)

    rc = main(["start", "dnf5-auto"], ctx)

    assert rc == 0
    assert recorder.messages == [
        "flatpak-auto-notify : verbe ou job invalide ['start', 'dnf5-auto'] "
        "(start|end|login|snapshot [flatpak-auto])\n"
    ]
    assert runner.calls == []
    assert files_under(tmp_path) == {}


def test_main_charge_le_descripteur_voisin_du_script(tmp_path: Path) -> None:
    write_boot_id(tmp_path / "root", BOOT_A)
    script = tmp_path / "dnf5-auto-notify"
    script.with_suffix(".json").write_text(DNF5_JOB.to_descriptor())
    script.with_suffix(".json").chmod(0o644)
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    ctx = Ctx(
        runner=runner,
        root_dir=tmp_path / "root",
        geteuid=lambda: 0,
        stderr=Recorder(),
        script=script,
    )

    rc = main(["start", "dnf5-auto"], ctx)

    assert rc == 0
    assert ctx.descriptor == DNF5_DESC
    assert len(notify_calls(runner)) == 1


def test_main_sans_descripteur_n_agit_pas_et_rend_zero(tmp_path: Path) -> None:
    recorder = Recorder()
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))
    ctx = ctx_for(runner, tmp_path, recorder, euid=0)
    ctx.descriptor = None
    ctx.script = tmp_path / "absent-notify"

    rc = main(["start"], ctx)

    assert rc == 0
    assert runner.calls == []
    assert len(recorder.messages) == 1
    assert recorder.messages[0].startswith("absent-notify : descripteur")


def test_verbe_sans_descripteur_leve_runtimeerror(tmp_path: Path) -> None:
    ctx = make_ctx(FakeRunner(lambda argv: (1, "")), tmp_path, Recorder())
    ctx.descriptor = None

    with pytest.raises(RuntimeError, match="descripteur"):
        start(ctx)
