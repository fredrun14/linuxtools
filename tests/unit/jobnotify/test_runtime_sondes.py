"""Tests des sondes du runtime : issues dnf5 et flatpak, empreinte, snapshot."""

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from linuxtools.jobnotify.runtime import (
    BUSCTL,
    SYSTEMCTL,
    Descriptor,
    Outcome,
    compute_dnf5_outcome,
    compute_flatpak_outcome,
    main,
    parse_descriptor,
    resolve_outcome,
    snapshot,
)
from linuxtools.jobnotify.spec import NotifiedJob
from linuxtools.jobnotify.spec import Outcome as SpecOutcome
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BASE_OUTCOMES,
    BOB_PROPS,
    BOOT_A,
    BOOT_B,
    DNF5_DESC,
    FLATPAK_DESC,
    FLATPAK_GUARD,
    FLATPAK_JOB,
    FLATPAK_LIST_ARGV,
    FLATPAK_START_SUMMARY,
    FLATPAK_WATCHED,
    HASH_AB,
    HASH_OTHER,
    LISTING_AB,
    LISTING_BA,
    RUN_ANTERIEUR,
    RUN_MANUEL,
    RUN_OK,
    SHUTDOWN_OK,
    STARTED_AT,
    STATE_RELATIVE,
    FakeRunner,
    Recorder,
    answer,
    before_path,
    ctx_for,
    descriptor_of,
    end_env,
    end_flatpak,
    files_under,
    flatpak_handler,
    mode_of,
    notify_calls,
    parse_notify,
    run_flatpak,
    sent_texts,
    system_handler,
    write_before,
    write_boot_id,
    write_flatpak_state,
)


def test_compute_dnf5_outcome_echec_si_service_result_different_de_success() -> None:
    outcome = compute_dnf5_outcome(
        service_result="exit-code",
        system_stopping=False,
        transactions=[],
        started_at=1000.0,
        needs_restart=False,
    )

    assert outcome is Outcome.FAILURE


def test_compute_dnf5_outcome_systeme_en_arret_interrompu() -> None:
    outcome = compute_dnf5_outcome(
        service_result="exit-code",
        system_stopping=True,
        transactions=[],
        started_at=1000.0,
        needs_restart=False,
    )

    assert outcome is Outcome.INTERRUPTED


@pytest.mark.parametrize(
    ("service_result", "stopping", "transactions", "needs_restart", "attendu"),
    [
        ("success", False, [RUN_OK], False, Outcome.SUCCESS),
        ("success", False, [RUN_OK], True, Outcome.SUCCESS_RESTART),
        ("success", False, [], False, Outcome.NOTHING),
        ("success", False, [], True, Outcome.NOTHING),
        ("success", False, [RUN_ANTERIEUR, RUN_MANUEL], True, Outcome.NOTHING),
        ("success", False, None, False, Outcome.DONE_NO_DETAIL),
        ("success", False, None, True, Outcome.DONE_NO_DETAIL),
        ("exit-code", False, [RUN_OK], False, Outcome.FAILURE),
        ("exit-code", False, None, False, Outcome.FAILURE),
        ("", False, [RUN_OK], False, Outcome.FAILURE),
        ("success", True, [RUN_OK], False, Outcome.INTERRUPTED),
        ("success", True, None, False, Outcome.INTERRUPTED),
        ("signal", True, [], True, Outcome.INTERRUPTED),
    ],
    ids=[
        "succes",
        "succes_redemarrage_requis",
        "rien_a_mettre_a_jour",
        "rien_malgre_redemarrage_en_attente",
        "transactions_hors_run_ignorees",
        "historique_illisible",
        "historique_illisible_redemarrage",
        "echec",
        "echec_historique_illisible",
        "service_result_vide_est_un_echec",
        "arret_systeme_apres_succes",
        "arret_systeme_historique_illisible",
        "arret_systeme_apres_signal",
    ],
)
def test_compute_dnf5_outcome_table_complete(
    service_result: str,
    stopping: bool,
    transactions: list[dict[str, object]] | None,
    needs_restart: bool,
    attendu: Outcome,
) -> None:
    outcome = compute_dnf5_outcome(
        service_result=service_result,
        system_stopping=stopping,
        transactions=transactions,
        started_at=STARTED_AT,
        needs_restart=needs_restart,
    )

    assert outcome is attendu


@pytest.mark.parametrize(
    "transaction",
    [
        "pas un mapping",
        {},
        {"start_time": 1010},
        {"command_line": "dnf5 automatic"},
        {"start_time": "1010", "command_line": "dnf5 automatic"},
        {"start_time": True, "command_line": "dnf5 automatic"},
        {"start_time": 1010, "command_line": None},
    ],
    ids=[
        "pas_un_mapping",
        "vide",
        "sans_command_line",
        "sans_start_time",
        "start_time_texte",
        "start_time_booleen",
        "command_line_nulle",
    ],
)
def test_compute_dnf5_outcome_ignore_transaction_mal_formee(
    transaction: object,
) -> None:
    transactions = cast("list[Mapping[str, object]]", [transaction, RUN_OK])

    outcome = compute_dnf5_outcome(
        service_result="success",
        system_stopping=False,
        transactions=transactions,
        started_at=STARTED_AT,
        needs_restart=False,
    )

    assert outcome is Outcome.SUCCESS


@pytest.mark.parametrize(
    ("command_line", "attendu"),
    [
        ("dnf5 automatic", Outcome.SUCCESS),
        ("/usr/bin/dnf5 automatic", Outcome.SUCCESS),
        ("dnf5 automatic --timer", Outcome.SUCCESS),
        ("dnf install -y dnf5-plugin-automatic", Outcome.NOTHING),
        ("dnf5 install -y dnf5-plugin-automatic", Outcome.NOTHING),
        ("dnf5 remove automatic-tools", Outcome.NOTHING),
        ("", Outcome.NOTHING),
        ("dnf5", Outcome.NOTHING),
    ],
    ids=[
        "automatic",
        "chemin_absolu",
        "avec_option",
        "dnf_install_plugin",
        "dnf5_install_plugin",
        "sous_commande_autre",
        "vide",
        "sans_sous_commande",
    ],
)
def test_compute_dnf5_outcome_filtre_sur_sous_commande_automatic(
    command_line: str, attendu: Outcome
) -> None:
    transactions = [{"start_time": 1010, "command_line": command_line}]

    outcome = compute_dnf5_outcome(
        service_result="success",
        system_stopping=False,
        transactions=transactions,
        started_at=STARTED_AT,
        needs_restart=False,
    )

    assert outcome is attendu


def test_snapshot_ecrit_l_empreinte_triee_en_0600_dans_un_dossier_0700(
    tmp_path: Path,
) -> None:
    handler = flatpak_handler(listings=[(0, LISTING_BA)])

    _, _, codes = run_flatpak(tmp_path, ["snapshot"], handler)

    assert codes == [0]
    assert before_path(tmp_path).read_text() == HASH_AB + "\n"
    assert mode_of(before_path(tmp_path)) == 0o600
    assert mode_of(before_path(tmp_path).parent) == 0o700


def test_snapshot_empreinte_independante_de_l_ordre_des_lignes(tmp_path: Path) -> None:
    contenus = []
    for name, listing in (("ba", LISTING_BA), ("ab", LISTING_AB)):
        root = tmp_path / name
        run_flatpak(root, ["snapshot"], flatpak_handler(listings=[(0, listing)]))
        contenus.append(before_path(root).read_text())

    assert contenus[0] == contenus[1] == HASH_AB + "\n"


def test_snapshot_argv_flatpak_list_system_columns_ref_active_f(
    tmp_path: Path,
) -> None:
    handler = flatpak_handler(listings=[(0, LISTING_AB)])

    runner, _, _ = run_flatpak(tmp_path, ["snapshot"], handler)

    assert [argv for argv, _ in runner.calls] == [
        ["/usr/bin/flatpak", "list", "--system", "--columns=ref,active:f"]
    ]


def test_snapshot_supprime_l_ancienne_empreinte_avant_d_ecrire(tmp_path: Path) -> None:
    before_path(tmp_path).parent.mkdir(parents=True)
    before_path(tmp_path).write_text(HASH_OTHER + "\n")

    _, recorder, _ = run_flatpak(
        tmp_path, ["snapshot"], flatpak_handler(listings=[(1, "")])
    )

    assert not before_path(tmp_path).exists()
    assert any("flatpak list illisible" in m for m in recorder.messages)


def test_snapshot_lien_symbolique_sur_before_non_suivi(tmp_path: Path) -> None:
    temoin = tmp_path / "temoin"
    temoin.write_text("intact")
    before_path(tmp_path).parent.mkdir(parents=True)
    before_path(tmp_path).symlink_to(temoin)

    run_flatpak(tmp_path, ["snapshot"], flatpak_handler(listings=[(0, LISTING_AB)]))

    assert temoin.read_text() == "intact"
    assert not before_path(tmp_path).is_symlink()
    assert before_path(tmp_path).read_text() == HASH_AB + "\n"


def test_snapshot_refuse_pour_dnf5_auto_rc0_sans_ecriture(tmp_path: Path) -> None:
    recorder = Recorder()
    runner = FakeRunner(system_handler())

    rc = main(["snapshot"], ctx_for(runner, tmp_path, recorder, euid=0))

    assert rc == 0
    assert recorder.messages == [
        "dnf5-auto-notify : snapshot sans objet pour dnf5-auto\n"
    ]
    assert runner.calls == []
    assert files_under(tmp_path) == {}


def test_snapshot_appele_directement_sans_job_par_defaut_rien_pour_dnf(
    tmp_path: Path,
) -> None:
    recorder = Recorder()
    runner = FakeRunner(system_handler())

    snapshot(ctx_for(runner, tmp_path, recorder, euid=0))

    assert runner.calls == []
    assert len(recorder.messages) == 1


def test_snapshot_liste_vide_est_une_empreinte_valide(tmp_path: Path) -> None:
    run_flatpak(tmp_path, ["snapshot"], flatpak_handler(listings=[(0, "\n  \n")]))

    # sha256 de la chaîne vide
    assert before_path(tmp_path).read_text() == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n"
    )


@pytest.mark.parametrize(
    ("service_result", "stopping", "has_state", "before", "after", "attendu"),
    [
        ("exit-code", True, True, HASH_AB, HASH_OTHER, Outcome.INTERRUPTED),
        ("success", True, True, HASH_AB, HASH_OTHER, Outcome.INTERRUPTED),
        ("exit-code", False, True, HASH_AB, HASH_OTHER, Outcome.FAILURE),
        ("", False, True, HASH_AB, HASH_OTHER, Outcome.FAILURE),
        ("success", False, False, HASH_AB, HASH_OTHER, Outcome.DONE_NO_DETAIL),
        ("success", False, True, None, HASH_OTHER, Outcome.DONE_NO_DETAIL),
        ("success", False, True, HASH_AB, None, Outcome.DONE_NO_DETAIL),
        ("success", False, True, HASH_AB, HASH_AB, Outcome.NOTHING),
        ("success", False, True, HASH_OTHER, HASH_AB, Outcome.SUCCESS),
    ],
    ids=[
        "arret_prioritaire_sur_echec",
        "arret",
        "echec",
        "service_result_vide",
        "sans_etat",
        "sans_avant",
        "sans_apres",
        "empreintes_egales",
        "empreintes_differentes",
    ],
)
def test_compute_flatpak_outcome_table(
    service_result: str,
    stopping: bool,
    has_state: bool,
    before: str | None,
    after: str | None,
    attendu: Outcome,
) -> None:
    outcome = compute_flatpak_outcome(
        service_result=service_result,
        system_stopping=stopping,
        has_state=has_state,
        before=before,
        after=after,
    )

    assert outcome is attendu


def test_end_flatpak_rien_a_mettre_a_jour_si_empreintes_egales(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path, before=HASH_AB, listings=[(0, LISTING_AB)])

    assert sent_texts(runner) == [
        (
            "Mise à jour Flatpak automatique terminée",
            f"Aucune application Flatpak à mettre à jour. {SHUTDOWN_OK}",
        )
    ]


def test_end_flatpak_reussi_si_empreintes_differentes(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path, before=HASH_OTHER, listings=[(0, LISTING_AB)])

    assert sent_texts(runner) == [
        (
            "Mise à jour Flatpak automatique terminée",
            f"Les applications Flatpak ont été mises à jour. {SHUTDOWN_OK}",
        )
    ]


def test_end_flatpak_echec_renvoie_vers_journalctl_flatpak(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path, result="exit-code")

    assert sent_texts(runner) == [
        (
            "Mise à jour Flatpak automatique en échec",
            (
                "La mise à jour a échoué : consultez « journalctl -u "
                f"flatpak-automatic » pour le détail. {SHUTDOWN_OK}"
            ),
        )
    ]
    assert FLATPAK_LIST_ARGV not in [argv for argv, _ in runner.calls]


def test_end_flatpak_interrompu_si_le_systeme_s_arrete(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path, running=(0, "stopping\n"))

    assert sent_texts(runner) == [
        (
            "Mise à jour Flatpak automatique interrompue",
            f"La mise à jour a été interrompue avant la fin. {SHUTDOWN_OK}",
        )
    ]
    assert FLATPAK_LIST_ARGV not in [argv for argv, _ in runner.calls]


def test_end_flatpak_sans_etat_donne_done_no_detail_sans_relire_flatpak(
    tmp_path: Path,
) -> None:
    runner, _ = end_flatpak(tmp_path, with_state=False)

    assert sent_texts(runner) == [
        (
            "Mise à jour Flatpak automatique terminée",
            (
                "La mise à jour est terminée, mais son détail est illisible. "
                f"{SHUTDOWN_OK}"
            ),
        )
    ]
    assert FLATPAK_LIST_ARGV not in [argv for argv, _ in runner.calls]


def test_end_flatpak_apres_illisible_donne_done_no_detail(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path, listings=[(1, "")])

    assert [s for s, _ in sent_texts(runner)] == [
        "Mise à jour Flatpak automatique terminée"
    ]
    assert "détail est illisible" in sent_texts(runner)[0][1]


def test_end_flatpak_remplace_la_notification_de_lancement(tmp_path: Path) -> None:
    handler = flatpak_handler(sessions={"1": ALICE_PROPS}, listings=[(0, LISTING_AB)])
    runner = FakeRunner(handler)
    write_boot_id(tmp_path, BOOT_A)
    for verb in ("snapshot", "start", "end"):
        env = end_env()
        main(
            [verb, "flatpak-auto"],
            ctx_for(runner, tmp_path, Recorder(), euid=0, job=FLATPAK_DESC, env=env),
        )

    start_call, end_call = notify_calls(runner)
    assert parse_notify(start_call)["summary"] == FLATPAK_START_SUMMARY
    assert parse_notify(start_call)["replaces"] == "0"
    assert parse_notify(end_call)["replaces"] == "42"  # ID renvoyé au lancement


def test_end_flatpak_notifie_chaque_session(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path, sessions={"1": ALICE_PROPS, "2": BOB_PROPS})

    assert len(notify_calls(runner)) == 2
    assert read_flatpak_delivered(tmp_path) == [1000, 1001]


def read_flatpak_delivered(root: Path) -> object:
    path = root / "var/lib/fedora-post-install/flatpak-auto/state.json"
    return json.loads(path.read_text())["delivered"]


@pytest.mark.parametrize(
    "scenario",
    [
        {},
        {"before": HASH_OTHER},
        {"result": "exit-code"},
        {"running": (0, "stopping\n")},
        {"with_state": False},
        {"listings": [(1, "")]},
    ],
    ids=["rien", "reussi", "echec", "interrompu", "sans_etat", "apres_illisible"],
)
def test_end_flatpak_supprime_l_empreinte_apres_lecture(
    tmp_path: Path, scenario: dict[str, Any]
) -> None:
    end_flatpak(tmp_path, **scenario)

    assert not before_path(tmp_path).exists()


def test_end_flatpak_ne_consulte_jamais_dnf5(tmp_path: Path) -> None:
    handler = flatpak_handler(
        sessions={"1": ALICE_PROPS},
        listings=[(0, LISTING_BA), (0, LISTING_AB + "x\t1\n")],
    )
    runner = FakeRunner(handler)
    write_boot_id(tmp_path, BOOT_A)
    for verb in ("snapshot", "start", "end"):
        main(
            [verb, "flatpak-auto"],
            ctx_for(
                runner, tmp_path, Recorder(), euid=0, job=FLATPAK_DESC, env=end_env()
            ),
        )

    assert [
        argv for argv, _ in runner.calls if argv[0].startswith("/usr/bin/dnf5")
    ] == []


def test_end_flatpak_arrete_uniquement_son_compagnon(tmp_path: Path) -> None:
    runner, _ = end_flatpak(tmp_path)

    stops = [argv for argv, _ in runner.calls if argv[:2] == [SYSTEMCTL, "stop"]]
    assert stops == [[SYSTEMCTL, "stop", FLATPAK_GUARD]]


def _make_fifo(path: Path) -> None:
    os.mkfifo(path)


def _make_symlink(path: Path) -> None:
    temoin = path.parent / "temoin-valide"
    temoin.write_text(HASH_AB + "\n")
    path.symlink_to(temoin)


def _make_text(content: str) -> Callable[[Path], None]:
    def make(path: Path) -> None:
        path.write_text(content)

    return make


@pytest.mark.parametrize(
    "make_before",
    [
        _make_text("a" * 66),
        _make_text("a" * 63),
        _make_text("g" * 64 + "\n"),
        _make_text("A" * 64 + "\n"),
        _make_text("é" * 32 + "\n"),
        _make_fifo,
        _make_symlink,
    ],
    ids=[
        "66_octets",
        "63_caracteres",
        "non_hexadecimal",
        "majuscules",
        "non_ascii",
        "fifo",
        "lien_symbolique",
    ],
)
def test_lecture_empreinte_refuse_fichier_trop_gros_ou_non_hexadecimal(
    tmp_path: Path, make_before: Callable[[Path], None]
) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_flatpak_state(tmp_path)
    before_path(tmp_path).parent.mkdir(parents=True)
    make_before(before_path(tmp_path))
    runner = FakeRunner(
        flatpak_handler(sessions={"1": ALICE_PROPS}, listings=[(0, LISTING_AB)])
    )
    recorder = Recorder()

    main(
        ["end", "flatpak-auto"],
        ctx_for(runner, tmp_path, recorder, euid=0, job=FLATPAK_DESC, env=end_env()),
    )

    assert "détail est illisible" in sent_texts(runner)[0][1]
    assert any("empreinte illisible" in m for m in recorder.messages)


def test_end_flatpak_aucun_nom_d_application_dans_notifications_ni_fichiers(
    tmp_path: Path,
) -> None:
    secret = "app/org.example.Secret/x86_64/stable\tabc"
    handler = flatpak_handler(
        sessions={"1": ALICE_PROPS},
        listings=[(0, secret + "1\n"), (0, secret + "2\n")],
    )
    runner = FakeRunner(handler)
    recorder = Recorder()
    write_boot_id(tmp_path, BOOT_A)
    for verb in ("snapshot", "start"):
        main(
            [verb, "flatpak-auto"],
            ctx_for(
                runner, tmp_path, recorder, euid=0, job=FLATPAK_DESC, env=end_env()
            ),
        )
    avant = files_under(tmp_path)
    main(
        ["end", "flatpak-auto"],
        ctx_for(runner, tmp_path, recorder, euid=0, job=FLATPAK_DESC, env=end_env()),
    )

    apres = files_under(tmp_path)
    assert any(f.endswith("before") for f in avant)
    assert "Mise à jour Flatpak automatique terminée" in sent_texts(runner)[-1][0]
    assert "mises à jour" in sent_texts(runner)[-1][1]  # empreintes différentes
    toutes_les_chaines = (
        [" ".join(argv) for argv, _ in runner.calls if BUSCTL in argv]
        + list(avant.values())
        + list(apres.values())
        + recorder.messages
    )
    assert all("org.example.Secret" not in chaine for chaine in toutes_les_chaines)


def test_start_flatpak_notification_persistante_textes_flatpak(
    tmp_path: Path,
) -> None:
    handler = flatpak_handler(sessions={"1": ALICE_PROPS})

    runner, _, _ = run_flatpak(tmp_path, ["start"], handler)

    (argv,) = notify_calls(runner)
    assert parse_notify(argv) == {
        "replaces": "0",
        "summary": FLATPAK_START_SUMMARY,
        "body": (
            "N'éteignez pas le poste et ne le mettez pas en veille "
            "jusqu'à la fin de la mise à jour."
        ),
        "urgency": "2",
        "expire": "0",
    }
    state = tmp_path / "var/lib/fedora-post-install/flatpak-auto/state.json"
    assert json.loads(state.read_text())["status"] == "running"
    assert not (tmp_path / STATE_RELATIVE).exists()  # rien côté dnf


def test_login_flatpak_utilise_ses_propres_chemins(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_flatpak_state(tmp_path)
    active = {FLATPAK_GUARD: "inactive", FLATPAK_WATCHED: "activating"}
    handler = flatpak_handler(active=active)
    home = tmp_path / "home" / "alice"

    runner, _, _ = run_flatpak(
        tmp_path, ["login"], handler, env={"HOME": str(home)}, euid=1000
    )

    queried = [
        argv[2] for argv, _ in runner.calls if argv[:2] == [SYSTEMCTL, "is-active"]
    ]
    assert queried == [FLATPAK_GUARD, FLATPAK_WATCHED]
    id_file = tmp_path / "run/user/1000/fedora-post-install/flatpak-auto.id"
    assert id_file.read_text() == "42\n"


def test_login_flatpak_resultat_vu_sous_le_dossier_seen_flatpak(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_flatpak_state(tmp_path, status="done", outcome="nothing")
    home = tmp_path / "home" / "alice"

    runner, _, _ = run_flatpak(
        tmp_path, ["login"], flatpak_handler(), env={"HOME": str(home)}, euid=1000
    )

    seen = home / ".local/state/fedora-post-install/flatpak-auto/seen"
    assert seen.read_text() == "1000.0\n"
    assert sent_texts(runner)[0][0] == "Mise à jour Flatpak automatique terminée"


def test_login_flatpak_signale_un_run_interrompu(tmp_path: Path) -> None:
    write_boot_id(tmp_path, BOOT_B)  # le boot courant n'est plus celui du run
    write_flatpak_state(tmp_path, boot_id=BOOT_A)
    home = tmp_path / "home" / "alice"

    runner, _, _ = run_flatpak(
        tmp_path, ["login"], flatpak_handler(), env={"HOME": str(home)}, euid=1000
    )

    assert sent_texts(runner) == [
        (
            "Mise à jour Flatpak automatique interrompue",
            f"La mise à jour a été interrompue avant la fin. {SHUTDOWN_OK}",
        )
    ]


@pytest.mark.parametrize("verb", ["start", "end", "login", "snapshot"])
def test_main_flatpak_rend_0_si_toutes_les_commandes_echouent(
    tmp_path: Path, verb: str
) -> None:
    write_boot_id(tmp_path, BOOT_A)
    write_flatpak_state(tmp_path)

    _, recorder, codes = run_flatpak(
        tmp_path, [verb], lambda argv: answer(OSError("boom")), euid=1000
    )

    assert codes == [0]
    assert recorder.messages != []
    assert all(m.startswith("flatpak-auto-notify : ") for m in recorder.messages)


def test_snapshot_ignore_les_lignes_blanches_et_les_espaces_de_bord(
    tmp_path: Path,
) -> None:
    sale = "\n  " + LISTING_AB.replace("\n", "  \n  \n")
    run_flatpak(tmp_path, ["snapshot"], flatpak_handler(listings=[(0, sale)]))

    assert before_path(tmp_path).read_text() == HASH_AB + "\n"


def _none_job() -> Descriptor:
    return descriptor_of(
        NotifiedJob(
            name="demo",
            owner="demo-app",
            watched_unit="demo.service",
            scope="system",
            start_texts=("début", "corps"),
            end_texts=dict.fromkeys(BASE_OUTCOMES, ("fin", "corps")),
        )
    )


@pytest.mark.parametrize(
    ("service_result", "stopping", "attendu"),
    [
        ("success", False, Outcome.SUCCESS),
        ("exit-code", False, Outcome.FAILURE),
        ("", False, Outcome.FAILURE),
        ("success", True, Outcome.INTERRUPTED),
    ],
    ids=["succes", "echec", "service_result_vide", "arret_systeme"],
)
def test_resolve_none_selon_service_result_et_arret(
    tmp_path: Path, service_result: str, stopping: bool, attendu: Outcome
) -> None:
    ctx = ctx_for(
        FakeRunner(lambda argv: (1, "")),
        tmp_path,
        Recorder(),
        euid=0,
        env={"SERVICE_RESULT": service_result},
    )
    descriptor = _none_job()

    assert resolve_outcome(ctx, descriptor, None, stopping=stopping) is attendu


def _etat_en_cours() -> Any:
    """État de ``start`` d'un run en cours, démarré à ``STARTED_AT``."""
    return cast(
        "Any",
        {
            "boot_id": BOOT_A,
            "started_at": STARTED_AT,
            "status": "running",
            "outcome": None,
            "delivered": [],
        },
    )


def test_sonde_inconnue_invalide_le_descripteur() -> None:
    data = json.loads(FLATPAK_JOB.to_descriptor())
    data["probe"] = {"kind": "inconnue", "argv": []}

    assert parse_descriptor(data) is None


def test_resolve_none_rend_success(tmp_path: Path) -> None:
    runner = FakeRunner(lambda argv: (1, ""))
    ctx = ctx_for(
        runner, tmp_path, Recorder(), euid=0, env={"SERVICE_RESULT": "success"}
    )

    outcome = resolve_outcome(ctx, _none_job(), None, stopping=False)

    assert outcome is Outcome.SUCCESS
    assert runner.calls == []  # la sonde `none` n'interroge aucun binaire


def test_resolve_fingerprint_inchange_si_empreinte_identique(tmp_path: Path) -> None:
    write_before(tmp_path, HASH_AB)
    runner = FakeRunner(flatpak_handler(listings=[(0, LISTING_AB)]))
    ctx = ctx_for(
        runner,
        tmp_path,
        Recorder(),
        euid=0,
        job=FLATPAK_DESC,
        env=end_env("success"),
    )

    outcome = resolve_outcome(ctx, FLATPAK_DESC, _etat_en_cours(), stopping=False)

    assert outcome is Outcome.NOTHING


def test_resolve_dnf5_redemarrage_requis(tmp_path: Path) -> None:
    reboot = '[{"type": "reboot", "reboot_required": true, "packages": ["kernel"]}]'
    runner = FakeRunner(
        system_handler(history=(0, json.dumps([RUN_OK])), needs=(1, reboot))
    )
    ctx = ctx_for(runner, tmp_path, Recorder(), euid=0, env=end_env("success"))

    outcome = resolve_outcome(ctx, DNF5_DESC, _etat_en_cours(), stopping=False)

    assert outcome is Outcome.SUCCESS_RESTART


def test_snapshot_sans_effet_pour_une_sonde_sans_instantane(tmp_path: Path) -> None:
    recorder = Recorder()
    runner = FakeRunner(lambda argv: (1, ""))
    ctx = ctx_for(runner, tmp_path, recorder, euid=0, job=_none_job())

    rc = main(["snapshot"], ctx)

    assert rc == 0
    assert runner.calls == []
    assert files_under(tmp_path) == {}


def test_outcome_runtime_et_spec_ont_les_memes_noms_et_valeurs() -> None:
    runtime = {member.name: member.value for member in Outcome}
    spec = {member.name: member.value for member in SpecOutcome}

    assert runtime == spec
    assert runtime["SUCCESS_RESTART"] == "success_restart"  # schéma figé (Q-06)
