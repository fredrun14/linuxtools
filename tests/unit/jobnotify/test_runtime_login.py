"""Tests du verbe login du runtime."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from linuxtools.jobnotify import runtime
from linuxtools.jobnotify.runtime import (
    BUSCTL,
    SYSTEMCTL,
    Ctx,
    Outcome,
    login,
)
from tests.unit.jobnotify.runtime_support import (
    BOOT_A,
    BOOT_B,
    END_TEXTS,
    GUARD_UNIT,
    START_SUMMARY,
    STATE_RELATIVE,
    FakeRunner,
    Recorder,
    Reply,
    ctx_for,
    mode_of,
    notify_calls,
    parse_notify,
    raw_state,
    system_handler,
    user_id_path,
    write_boot_id,
    write_state_file,
)


def login_env(tmp_path: Path) -> dict[str, str]:
    return {"XDG_STATE_HOME": str(tmp_path / "state")}


def seen_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "fedora-post-install" / "dnf5-auto" / "seen"


def run_login(
    tmp_path: Path,
    *,
    env: Mapping[str, str] | None = None,
    euid: int = 1000,
    active: Reply = (0, "inactive\n"),
    guard: Reply = (3, "inactive\n"),
    notify: Reply | None = None,
) -> tuple[FakeRunner, Recorder]:
    runner = FakeRunner(system_handler(active=active, guard=guard, notify=notify))
    recorder = Recorder()
    ctx = ctx_for(
        runner,
        tmp_path,
        recorder,
        euid=euid,
        env=login_env(tmp_path) if env is None else env,
    )
    login(ctx)
    return runner, recorder


def test_login_rattrape_resultat_non_vu(tmp_path: Path) -> None:
    write_state_file(tmp_path, status="done", outcome="success")

    runner, _ = run_login(tmp_path)

    (argv,) = notify_calls(runner)
    summary, body = END_TEXTS[Outcome.SUCCESS]
    assert argv[:3] == [BUSCTL, "--user", "call"]  # direct : ni runuser ni env
    assert parse_notify(argv) == {
        "replaces": "0",
        "summary": summary,
        "body": body,
        "urgency": "1",
        "expire": "0",
    }
    assert seen_path(tmp_path).read_text().strip() == "1000.0"
    assert mode_of(seen_path(tmp_path)) == 0o600


@pytest.mark.parametrize(
    ("delivered", "seen"),
    [([1000], None), ([], "1000.0"), ([], "2000.0")],
    ids=["deja_livre", "vu_meme_run", "vu_run_plus_recent"],
)
def test_login_resultat_deja_vu_ne_renotifie_pas(
    tmp_path: Path,
    delivered: list[int],
    seen: str | None,
) -> None:
    write_state_file(tmp_path, status="done", outcome="success", delivered=delivered)
    if seen is not None:
        seen_path(tmp_path).parent.mkdir(parents=True)
        seen_path(tmp_path).write_text(seen)

    runner, _ = run_login(tmp_path)

    assert notify_calls(runner) == []


def test_login_resultat_plus_recent_que_seen_est_affiche(tmp_path: Path) -> None:
    write_state_file(tmp_path, status="done", outcome="failure", started_at=1500.0)
    seen_path(tmp_path).parent.mkdir(parents=True)
    seen_path(tmp_path).write_text("1000.0")

    runner, _ = run_login(tmp_path)

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.FAILURE][0])
    )
    assert seen_path(tmp_path).read_text().strip() == "1500.0"


def test_login_resultat_sans_issue_connue_dit_done_no_detail(tmp_path: Path) -> None:
    write_state_file(tmp_path, status="done", outcome=None)

    runner, _ = run_login(tmp_path)

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.DONE_NO_DETAIL][0])
    )


def test_login_etat_interrompu_ecrit_par_end_est_rattrape(tmp_path: Path) -> None:
    write_state_file(tmp_path, status="interrupted", outcome="interrupted")

    runner, _ = run_login(tmp_path)

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.INTERRUPTED][0])
    )


@pytest.mark.parametrize("active", ["activating", "active"])
def test_login_run_en_cours_renotifie_et_ecrit_l_id_utilisateur(
    tmp_path: Path,
    active: str,
) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    runner, _ = run_login(tmp_path, active=(0, active + "\n"))

    (argv,) = notify_calls(runner)
    assert parse_notify(argv)["summary"] == START_SUMMARY
    assert parse_notify(argv)["urgency"] == "2"
    assert user_id_path(tmp_path, 1000).read_text().strip() == "42"
    assert mode_of(user_id_path(tmp_path, 1000)) == 0o600
    assert not seen_path(tmp_path).exists()
    assert [SYSTEMCTL, "is-active", "dnf5-automatic.service"] in [
        a for a, _ in runner.calls
    ]


def test_login_run_en_cours_envoi_en_echec_n_ecrit_pas_d_id(tmp_path: Path) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    _, recorder = run_login(tmp_path, active=(0, "active\n"), notify=(1, ""))

    assert not user_id_path(tmp_path, 1000).exists()
    assert any("envoi impossible" in m for m in recorder.messages)


def test_login_boot_id_different_signale_interruption(tmp_path: Path) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_B)

    runner, _ = run_login(tmp_path, active=(0, "active\n"))
    second, _ = run_login(tmp_path, active=(0, "active\n"))

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.INTERRUPTED][0])
    )
    assert seen_path(tmp_path).read_text().strip() == "1000.0"
    assert notify_calls(second) == []  # déjà signalée : pas de répétition


@pytest.mark.parametrize(
    "active",
    [(3, "inactive\n"), (0, "failed\n"), OSError("absent")],
    ids=["inactive", "failed", "commande_absente"],
)
def test_login_unite_inactive_signale_interruption(
    tmp_path: Path,
    active: Reply,
) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    runner, _ = run_login(tmp_path, active=active)

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.INTERRUPTED][0])
    )


@pytest.mark.parametrize("guard", ["active", "activating"])
def test_login_compagnon_actif_dnf_inactif_signale_en_cours(
    tmp_path: Path,
    guard: str,
) -> None:
    """F01 : dnf attend network-online, mais le compagnon, lui, est actif."""
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    runner, _ = run_login(tmp_path, active=(3, "inactive\n"), guard=(0, guard + "\n"))

    (argv,) = notify_calls(runner)
    assert parse_notify(argv)["summary"] == START_SUMMARY
    assert [SYSTEMCTL, "is-active", GUARD_UNIT] in [a for a, _ in runner.calls]


def test_login_dnf_deactivating_signale_en_cours(tmp_path: Path) -> None:
    """F01 : dnf en cours d'arrêt (ExecStopPost) : le run n'est pas interrompu."""
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    runner, _ = run_login(tmp_path, active=(0, "deactivating\n"))

    (argv,) = notify_calls(runner)
    assert parse_notify(argv)["summary"] == START_SUMMARY


def test_login_compagnon_et_dnf_inactifs_signale_interruption(
    tmp_path: Path,
) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    runner, _ = run_login(tmp_path, active=(3, "inactive\n"), guard=(3, "inactive\n"))

    (argv,) = notify_calls(runner)
    assert parse_notify(argv)["summary"] == END_TEXTS[Outcome.INTERRUPTED][0]


def test_login_boot_id_illisible_signale_interruption(tmp_path: Path) -> None:
    write_state_file(tmp_path)

    runner, _ = run_login(tmp_path, active=(0, "active\n"))

    assert (
        parse_notify(notify_calls(runner)[0])["summary"]
        == (END_TEXTS[Outcome.INTERRUPTED][0])
    )


def test_login_refuse_de_tourner_en_root(tmp_path: Path) -> None:
    write_state_file(tmp_path, status="done", outcome="success")

    runner, recorder = run_login(tmp_path, euid=0)

    assert runner.calls == []
    assert any("root" in m for m in recorder.messages)


def test_login_sans_etat_ne_fait_rien_sans_bruit(tmp_path: Path) -> None:
    runner, recorder = run_login(tmp_path)

    assert runner.calls == []
    assert recorder.messages == []


CORRUPT_STATES = {
    "json_invalide": b"pas du json",
    "pas_un_objet": b"[]",
    "cles_absentes": b'{"boot_id": "a"}',
    "boot_id_non_texte": raw_state(boot_id="1"),
    "started_at_booleen": raw_state(started_at="true"),
    "started_at_nan": raw_state(started_at="NaN"),
    "statut_inconnu": raw_state(status='"?"'),
    "statut_non_texte": raw_state(status='["done"]'),
    "issue_inconnue": raw_state(outcome='"x"'),
    "issue_non_texte": raw_state(outcome="3"),
    "delivered_non_entiers": raw_state(delivered='["a"]'),
    "delivered_booleens": raw_state(delivered="[true]"),
    "delivered_non_liste": raw_state(delivered="5"),
    "octets_invalides": b"\xff\xfe",
    "trop_gros": b" " * 5000,
    "trop_imbrique": b"[" * 3000,
}


@pytest.mark.parametrize(
    "contenu",
    list(CORRUPT_STATES.values()),
    ids=list(CORRUPT_STATES),
)
def test_etat_corrompu_est_ignore_avec_message(
    tmp_path: Path,
    contenu: bytes,
) -> None:
    path = tmp_path / STATE_RELATIVE
    path.parent.mkdir(parents=True)
    path.write_bytes(contenu)

    runner, recorder = run_login(tmp_path)

    assert notify_calls(runner) == []
    assert len(recorder.messages) == 1


def test_etat_lien_symbolique_ou_non_regulier_est_ignore(tmp_path: Path) -> None:
    vrai = tmp_path / "vrai.json"
    vrai.write_text(
        '{"boot_id": "a", "started_at": 1.0, "status": "done",'
        ' "outcome": "success", "delivered": []}',
    )
    path = tmp_path / STATE_RELATIVE
    path.parent.mkdir(parents=True)
    path.symlink_to(vrai)

    runner, recorder = run_login(tmp_path)

    assert notify_calls(runner) == []
    assert len(recorder.messages) == 1


def test_login_seen_hostile_est_ignore_et_la_cible_reste_intacte(
    tmp_path: Path,
) -> None:
    write_state_file(tmp_path, status="done", outcome="success")
    victime = tmp_path / "victime"
    victime.write_text("9999.0")
    seen_path(tmp_path).parent.mkdir(parents=True)
    seen_path(tmp_path).symlink_to(victime)

    runner, _ = run_login(tmp_path)

    assert len(notify_calls(runner)) == 1
    assert victime.read_text() == "9999.0"
    assert not seen_path(tmp_path).is_symlink()


@pytest.mark.parametrize(
    "contenu",
    [b"abc", b"nan", b"inf", b"\xff", b"1" * 100],
    ids=["texte", "nan", "infini", "octets_invalides", "trop_gros"],
)
def test_login_seen_invalide_vaut_jamais_vu(tmp_path: Path, contenu: bytes) -> None:
    write_state_file(tmp_path, status="done", outcome="success")
    seen_path(tmp_path).parent.mkdir(parents=True)
    seen_path(tmp_path).write_bytes(contenu)

    runner, _ = run_login(tmp_path)

    assert len(notify_calls(runner)) == 1
    assert seen_path(tmp_path).read_text().strip() == "1000.0"


@pytest.mark.parametrize(
    ("env", "attendu"),
    [
        ({"HOME": "{tmp}/home"}, "{tmp}/home/.local/state"),
        (
            {"XDG_STATE_HOME": "relatif", "HOME": "{tmp}/home"},
            "{tmp}/home/.local/state",
        ),
        ({"XDG_STATE_HOME": "{tmp}/xdg", "HOME": "{tmp}/home"}, "{tmp}/xdg"),
    ],
    ids=["home", "xdg_relatif_ignore", "xdg_absolu"],
)
def test_login_repertoire_d_etat_xdg_ou_home(
    tmp_path: Path,
    env: dict[str, str],
    attendu: str,
) -> None:
    write_state_file(tmp_path, status="done", outcome="success")
    resolved = {k: v.format(tmp=tmp_path) for k, v in env.items()}

    run_login(tmp_path, env=resolved)

    seen = Path(attendu.format(tmp=tmp_path)) / "fedora-post-install/dnf5-auto/seen"
    assert seen.read_text().strip() == "1000.0"


@pytest.mark.parametrize(
    "env",
    [{}, {"HOME": "relatif"}, {"XDG_STATE_HOME": "relatif"}],
    ids=["vide", "home_relatif", "xdg_relatif"],
)
def test_login_sans_repertoire_d_etat_ne_notifie_pas_le_resultat(
    tmp_path: Path,
    env: dict[str, str],
) -> None:
    write_state_file(tmp_path, status="done", outcome="success")

    runner, recorder = run_login(tmp_path, env=env)

    assert notify_calls(runner) == []
    assert any("HOME" in m for m in recorder.messages)


def test_login_envoi_en_echec_n_ecrit_pas_seen(tmp_path: Path) -> None:
    write_state_file(tmp_path, status="done", outcome="success")

    _, recorder = run_login(tmp_path, notify=(1, ""))

    assert not seen_path(tmp_path).exists()
    assert any("envoi impossible" in m for m in recorder.messages)


def run_login_end_pendant_l_envoi(
    tmp_path: Path,
    *,
    fin: Mapping[str, object],
    boot_apres: str | None = None,
) -> tuple[FakeRunner, Recorder]:
    """Rejoue ``login`` ; l'état change dès que « en cours » est envoyée."""
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)
    base = system_handler(active=(0, "active\n"))

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        result = base(argv)
        if BUSCTL in argv and len(notify_calls(runner)) == 1:
            write_state_file(tmp_path, **fin)  # ``end`` termine pendant l'envoi
            if boot_apres is not None:
                write_boot_id(tmp_path, boot_apres)
        return result

    runner = FakeRunner(handler)
    recorder = Recorder()
    login(
        ctx_for(runner, tmp_path, recorder, euid=1000, env=login_env(tmp_path)),
    )
    return runner, recorder


def test_login_run_termine_pendant_l_envoi_remplace_la_notification(
    tmp_path: Path,
) -> None:
    runner, _ = run_login_end_pendant_l_envoi(
        tmp_path, fin={"status": "done", "outcome": "success"}
    )

    envoi, remplacement = (parse_notify(a) for a in notify_calls(runner))
    assert envoi["summary"] == START_SUMMARY
    assert remplacement["replaces"] == "42"  # l'ID renvoyé par le premier envoi
    assert remplacement["summary"] == END_TEXTS[Outcome.SUCCESS][0]
    assert remplacement["urgency"] == "1"
    assert seen_path(tmp_path).read_text().strip() == "1000.0"


def test_login_boot_change_pendant_l_envoi_remplace_par_interruption(
    tmp_path: Path,
) -> None:
    runner, _ = run_login_end_pendant_l_envoi(tmp_path, fin={}, boot_apres="bbbb-2222")

    remplacement = parse_notify(notify_calls(runner)[1])
    assert remplacement["replaces"] == "42"
    assert remplacement["summary"] == END_TEXTS[Outcome.INTERRUPTED][0]


def test_login_ecrit_son_id_avant_de_relire_l_etat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # F21, E9 : c'est l'ordre « ID écrit, puis état relu » qui garantit qu'``end``
    # ou ``login`` voit l'écriture de l'autre ; la relecture suit donc l'écriture.
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)
    ids = user_id_path(tmp_path, 1000)
    reads_after_send: list[bool] = []
    real_read_state = runtime._read_state

    def spy(ctx: Ctx) -> object:
        reads_after_send.append(ids.exists())
        return real_read_state(ctx)

    monkeypatch.setattr(runtime, "_read_state", spy)

    run_login(tmp_path, active=(0, "active\n"))

    assert reads_after_send == [False, True]  # lecture initiale, puis relecture


def test_login_run_toujours_en_cours_apres_l_envoi_ne_remplace_rien(
    tmp_path: Path,
) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)

    runner, _ = run_login(tmp_path, active=(0, "active\n"))

    assert len(notify_calls(runner)) == 1


def test_login_etat_illisible_apres_l_envoi_ne_remplace_rien(tmp_path: Path) -> None:
    write_state_file(tmp_path)
    write_boot_id(tmp_path, BOOT_A)
    base = system_handler(active=(0, "active\n"))

    def handler(argv: Sequence[str]) -> tuple[int, str]:
        if BUSCTL in argv:
            (tmp_path / STATE_RELATIVE).write_text("{pas du json")
        return base(argv)

    runner = FakeRunner(handler)
    login(
        ctx_for(runner, tmp_path, Recorder(), euid=1000, env=login_env(tmp_path)),
    )

    assert len(notify_calls(runner)) == 1
