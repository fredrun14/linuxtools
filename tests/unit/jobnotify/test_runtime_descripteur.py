"""Tests du descripteur du runtime : lecture sûre, schéma strict, échec fermé."""

import copy
import errno
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from linuxtools.jobnotify.runtime import (
    Ctx,
    Outcome,
    load_descriptor,
    parse_descriptor,
)
from linuxtools.jobnotify.spec import FwupdProbe, NotifiedJob
from linuxtools.jobnotify.spec import Outcome as SpecOutcome
from tests.unit.jobnotify.runtime_support import (
    DNF5_JOB,
    FLATPAK_JOB,
    Recorder,
    descriptor_of,
)

SCRIPT = "dnf5-auto-notify"


def _ctx(directory: Path, recorder: Recorder, **extra: Any) -> Ctx:
    """Contexte dont le script est `directory/dnf5-auto-notify`."""
    return Ctx(
        runner=lambda argv, timeout: (1, ""),
        script=directory / SCRIPT,
        stderr=recorder,
        **extra,
    )


def _write(directory: Path, text: str, mode: int = 0o644) -> Path:
    path = directory / f"{SCRIPT}.json"
    path.write_text(text)
    path.chmod(mode)
    return path


def _data(job: NotifiedJob = DNF5_JOB) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(job.to_descriptor())
    return loaded


def test_load_descriptor_lit_le_descripteur_voisin_du_script(tmp_path: Path) -> None:
    _write(tmp_path, DNF5_JOB.to_descriptor())
    recorder = Recorder()

    descriptor = load_descriptor(_ctx(tmp_path, recorder))

    assert descriptor == descriptor_of(DNF5_JOB)
    assert descriptor is not None
    assert (descriptor.name, descriptor.owner, descriptor.scope) == (
        "dnf5-auto",
        "fedora-post-install",
        "system",
    )
    assert (
        descriptor.end_texts[Outcome.FAILURE] == DNF5_JOB.end_texts[SpecOutcome.FAILURE]
    )
    assert recorder.messages == []


def test_load_descriptor_refuse_lien_symbolique(tmp_path: Path) -> None:
    cible = tmp_path / "ailleurs.json"
    cible.write_text(DNF5_JOB.to_descriptor())
    (tmp_path / f"{SCRIPT}.json").symlink_to(cible)
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


@pytest.mark.parametrize("mode", [0o664, 0o646, 0o666, 0o620])
def test_load_descriptor_refuse_fichier_inscriptible_groupe_ou_autres(
    tmp_path: Path, mode: int
) -> None:
    _write(tmp_path, DNF5_JOB.to_descriptor(), mode)
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


def test_load_descriptor_refuse_mauvais_proprietaire(tmp_path: Path) -> None:
    _write(tmp_path, DNF5_JOB.to_descriptor())
    recorder = Recorder()
    ctx = _ctx(tmp_path, recorder, trusted_uids=frozenset({os.getuid() + 1}))

    assert load_descriptor(ctx) is None
    assert len(recorder.messages) == 1


def test_load_descriptor_refuse_fichier_trop_gros(tmp_path: Path) -> None:
    _write(tmp_path, " " * (16 * 1024 + 1) + DNF5_JOB.to_descriptor())
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


def test_load_descriptor_refuse_fichier_non_regulier(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / f"{SCRIPT}.json", 0o644)
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


def test_load_descriptor_absent_rend_none_avec_message(tmp_path: Path) -> None:
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1
    assert recorder.messages[0].startswith(f"{SCRIPT} : ")


@pytest.mark.parametrize(
    "contenu",
    [b"pas du json", b"\xff\xfe", b"[]", b'"texte"', b"null", b"[" * 5000],
    ids=["json_invalide", "octets_invalides", "liste", "chaine", "null", "profond"],
)
def test_load_descriptor_refuse_contenu_qui_n_est_pas_un_objet_json(
    tmp_path: Path, contenu: bytes
) -> None:
    (tmp_path / f"{SCRIPT}.json").write_bytes(contenu)
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


def test_load_descriptor_refuse_schema_inconnu(tmp_path: Path) -> None:
    data = _data()
    data["intrus"] = 1
    _write(tmp_path, json.dumps(data))
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


def _set(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        data[key] = value

    return mutate


def _drop(key: str) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        del data[key]

    return mutate


def _set_probe(**champs: object) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        data["probe"] = {**data["probe"], **champs}

    return mutate


def _drop_end_text(issue: str) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        del data["end_texts"][issue]

    return mutate


def _set_end_text(issue: str, value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        data["end_texts"][issue] = value

    return mutate


MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    "version_inconnue": _set("version", 2),
    "version_booleenne": _set("version", True),
    "cle_absente": _drop("owner"),
    "cle_etrangere": _set("extra", "x"),
    "name_hors_motif": _set("name", "Evil/../x"),
    "name_vide": _set("name", ""),
    "name_non_chaine": _set("name", 7),
    "owner_hors_motif": _set("owner", "-evil"),
    "unite_sans_service": _set("watched_unit", "dnf5-automatic.timer"),
    "unite_avec_espace": _set("watched_unit", "a b.service"),
    "scope_inconnu": _set("scope", "global"),
    "start_texts_pas_un_couple": _set("start_texts", ["seul"]),
    "start_texts_non_chaines": _set("start_texts", ["a", 3]),
    "start_texts_pas_une_liste": _set("start_texts", "ab"),
    "texte_trop_long": _set("start_texts", ["a", "x" * 201]),
    "texte_avec_controle": _set("start_texts", ["a\nb", "c"]),
    "end_texts_pas_un_objet": _set("end_texts", []),
    "end_texts_issue_inconnue": _set_end_text("exotique", ["a", "b"]),
    "end_texts_issue_manquante": _drop_end_text("interrupted"),
    "end_texts_couple_invalide": _set_end_text("success", ["a"]),
    "end_texts_texte_non_chaine": _set_end_text("success", ["a", 1]),
    "lock_non_booleen": _set("lock", 1),
    "sonde_inconnue": _set_probe(kind="inconnue"),
    "sonde_pas_un_objet": _set("probe", "dnf5"),
    "sonde_cles_etrangeres": _set("probe", {"kind": "dnf5", "argv": [], "x": 1}),
    "sonde_kind_non_chaine": _set_probe(kind=3),
    "sonde_argv_pas_une_liste": _set_probe(argv="/usr/bin/flatpak"),
    "sonde_argv_non_chaines": _set_probe(argv=[1]),
    "icon_avec_controle": _set("icon", "a\x00b"),
    "icon_non_chaine": _set("icon", None),
    "inhibit_why_avec_pourcent": _set("inhibit_why", "100% sur"),
    "inhibit_why_avec_guillemet": _set("inhibit_why", 'a"b'),
    "inhibit_why_avec_controle": _set("inhibit_why", "a\nb"),
    "guard_after_pas_une_liste": _set("guard_after", "x.service"),
    "guard_after_unite_invalide": _set("guard_after", ["x.timer"]),
    "guard_after_non_chaine": _set("guard_after", [1]),
}


@pytest.mark.parametrize("nom", sorted(MUTATIONS))
def test_parse_descriptor_refuse_les_valeurs_hors_schema(nom: str) -> None:
    data = _data()
    MUTATIONS[nom](data)

    assert parse_descriptor(data) is None


def test_parse_descriptor_refuse_ce_qui_n_est_pas_un_objet() -> None:
    assert parse_descriptor(["version"]) is None


def test_parse_descriptor_refuse_fingerprint_hors_catalogue_binaire_relatif() -> None:
    data = _data(FLATPAK_JOB)
    data["probe"]["argv"] = ["flatpak", "list"]

    assert parse_descriptor(data) is None


def test_parse_descriptor_refuse_fingerprint_sans_argv() -> None:
    data = _data(FLATPAK_JOB)
    data["probe"]["argv"] = []

    assert parse_descriptor(data) is None


def test_parse_descriptor_refuse_fingerprint_argv_avec_octet_nul() -> None:
    data = _data(FLATPAK_JOB)
    data["probe"]["argv"] = ["/usr/bin/flatpak", "a\x00b"]

    assert parse_descriptor(data) is None


def test_parse_descriptor_refuse_sonde_sans_argv_si_aucune_attendue() -> None:
    data = _data()
    data["probe"]["argv"] = ["/usr/bin/x"]

    assert parse_descriptor(data) is None


def test_parse_descriptor_flatpak_garde_l_argv_declare() -> None:
    descriptor = parse_descriptor(copy.deepcopy(_data(FLATPAK_JOB)))

    assert descriptor is not None
    assert descriptor.probe_kind == "fingerprint"
    assert descriptor.probe_argv == (
        "/usr/bin/flatpak",
        "list",
        "--system",
        "--columns=ref,active:f",
    )


def test_load_descriptor_erreur_de_lecture_rend_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, DNF5_JOB.to_descriptor())

    def echec(fd: int, taille: int) -> bytes:
        raise OSError(errno.EIO, "lecture impossible")

    monkeypatch.setattr(os, "read", echec)
    recorder = Recorder()

    assert load_descriptor(_ctx(tmp_path, recorder)) is None
    assert len(recorder.messages) == 1


def _fwupd_job() -> NotifiedJob:
    """Job fwupd aux cinq issues atteignables (textes écrits à la main)."""
    return NotifiedJob(
        name="fwupd-auto",
        owner="fedora-post-install",
        watched_unit="fwupd-automatic.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts={
            SpecOutcome.SUCCESS_RESTART: ("Prêt", "Redémarrez"),
            SpecOutcome.NOTHING: ("À jour", "Rien"),
            SpecOutcome.DONE_NO_DETAIL: ("Fini", "Détail illisible"),
            SpecOutcome.FAILURE: ("Échec", "Voir le journal"),
            SpecOutcome.INTERRUPTED: ("Interrompu", "Relancé au prochain run"),
        },
        lock=False,
        probe=FwupdProbe(),
    )


def test_descripteur_fwupd_roundtrip() -> None:
    descriptor = descriptor_of(_fwupd_job())

    assert descriptor.probe_kind == "fwupd"
    assert descriptor.probe_argv == ()
    assert descriptor.lock is False
    assert set(descriptor.end_texts) == {
        Outcome.SUCCESS_RESTART,
        Outcome.NOTHING,
        Outcome.DONE_NO_DETAIL,
        Outcome.FAILURE,
        Outcome.INTERRUPTED,
    }


def test_descripteur_fwupd_argv_non_vide_refuse() -> None:
    data = _data(_fwupd_job())
    data["probe"] = {"kind": "fwupd", "argv": ["/usr/bin/fwupdmgr", "update"]}

    assert parse_descriptor(data) is None
