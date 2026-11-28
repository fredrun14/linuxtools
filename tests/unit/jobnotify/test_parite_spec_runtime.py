"""Parité entre `NotifiedJob` (spec) et `parse_descriptor` (runtime) — F05.

Le runtime refuse EN SILENCE un descripteur hors schéma : toute divergence avec la
validation de `spec.py` devient un job qui ne notifie plus, sans erreur à
l'installation. Ces tests comparent, sur les mêmes données, ce que `NotifiedJob`
accepte et ce que `parse_descriptor` accepte.
"""

import json
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

import pytest

import linuxtools.jobnotify.runtime as runtime_module
import linuxtools.jobnotify.spec as spec_module
from linuxtools.jobnotify.runtime import parse_descriptor
from linuxtools.jobnotify.spec import (
    Dnf5Probe,
    FingerprintProbe,
    FwupdProbe,
    NoProbe,
    NotifiedJob,
    Outcome,
    Probe,
)

_BASE = (Outcome.SUCCESS, Outcome.FAILURE, Outcome.INTERRUPTED)
_FLATPAK = (*_BASE, Outcome.NOTHING, Outcome.DONE_NO_DETAIL)


def _textes(*issues: Outcome) -> dict[Outcome, tuple[str, str]]:
    """`end_texts` couvrant exactement `issues`."""
    return {issue: (f"fin {issue.value}", "corps") for issue in issues}


def _descripteur_valide() -> dict[str, Any]:
    """Descripteur JSON (sonde fingerprint) produit par un job valide."""
    job = NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts=_textes(*_FLATPAK),
        probe=FingerprintProbe(argv=("/usr/bin/flatpak", "list")),
    )
    data: dict[str, Any] = json.loads(job.to_descriptor())
    return data


def _sonde(probe: dict[str, Any]) -> Probe:
    """Sonde de la spec décrite par la sonde JSON."""
    if probe["kind"] == "fingerprint":
        return FingerprintProbe(argv=tuple(probe["argv"]))
    if probe["kind"] == "dnf5":
        return Dnf5Probe()
    return FwupdProbe() if probe["kind"] == "fwupd" else NoProbe()


def _job_depuis(data: dict[str, Any]) -> NotifiedJob:
    """Construit le `NotifiedJob` que décrit ce descripteur (lève `ValueError`)."""
    return NotifiedJob(
        name=data["name"],
        owner=data["owner"],
        watched_unit=data["watched_unit"],
        scope=data["scope"],
        start_texts=tuple(data["start_texts"]),
        end_texts={Outcome(k): tuple(v) for k, v in data["end_texts"].items()},
        lock=data["lock"],
        probe=_sonde(data["probe"]),
        icon=data["icon"],
        inhibit_why=data["inhibit_why"],
        guard_after=tuple(data["guard_after"]),
    )


def _sans(data: dict[str, Any], outcome: Outcome) -> dict[str, Any]:
    """Copie de `end_texts` privée d'une issue."""
    return {k: v for k, v in data["end_texts"].items() if k != outcome.value}


# (identifiant, surcharges du descripteur, accepté ?) : attendu écrit à la main.
_CAS: list[tuple[str, dict[str, Any], bool]] = [
    ("valide", {}, True),
    ("start_texts a 3 elements", {"start_texts": ["a", "b", "c"]}, False),
    ("start_texts a 1 element", {"start_texts": ["a"]}, False),
    ("start_texts non texte", {"start_texts": ["a", 3]}, False),
    ("start_texts trop long", {"start_texts": ["a", "x" * 201]}, False),
    ("start_texts a 200", {"start_texts": ["a", "x" * 200]}, True),
    ("start_texts controle", {"start_texts": ["a", "b\x07"]}, False),
    ("nom majuscule", {"name": "Demo"}, False),
    ("owner invalide", {"owner": "demo app"}, False),
    ("unite sans .service", {"watched_unit": "demo.timer"}, False),
    ("scope inconnu", {"scope": "global"}, False),
    ("guard_after invalide", {"guard_after": ["x y.service"]}, False),
    ("guard_after valide", {"guard_after": ["network.service"]}, True),
    ("icon controle", {"icon": "a\nb"}, False),
    ("why guillemet", {"inhibit_why": 'a"b'}, False),
    ("why espaces", {"inhibit_why": "Mise à jour en cours"}, True),
    ("why dollar", {"inhibit_why": "a$b"}, False),
    (
        "argv relatif",
        {"probe": {"kind": "fingerprint", "argv": ["flatpak"]}},
        False,
    ),
    (
        "argv vide",
        {"probe": {"kind": "fingerprint", "argv": []}},
        False,
    ),
    (
        "argv octet nul",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "a\x00b"]}},
        False,
    ),
    (
        "argv flatpak sans sous-commande",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak"]}},
        False,
    ),
    (
        "argv flatpak list system",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": [
                    "/usr/bin/flatpak",
                    "list",
                    "--system",
                    "--columns=ref,active:f",
                ],
            }
        },
        True,
    ),
    (
        "argv binaire hors liste blanche /usr/bin",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/x", "list"]}},
        False,
    ),
    (
        "argv binaire sous /usr/sbin",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/sbin/flatpak"]}},
        False,
    ),
    (
        "argv binaire sous /bin",
        {"probe": {"kind": "fingerprint", "argv": ["/bin/flatpak"]}},
        False,
    ),
    (
        "argv binaire sous /sbin",
        {"probe": {"kind": "fingerprint", "argv": ["/sbin/flatpak"]}},
        False,
    ),
    (
        "argv binaire avec ..",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/../bin/flatpak"]}},
        False,
    ),
    (
        "argv binaire sous /usr/local/bin",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/local/bin/flatpak"]}},
        False,
    ),
    (
        "argv binaire sous /home",
        {"probe": {"kind": "fingerprint", "argv": ["/home/u/venv/bin/flatpak"]}},
        False,
    ),
    (
        "argv binaire double slash",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin//flatpak"]}},
        False,
    ),
    (
        "argv binaire point",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/./flatpak"]}},
        False,
    ),
    (
        "argv binaire suffixe",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak-x"]}},
        False,
    ),
    (
        "argv argument relatif avec ..",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "../a"]}},
        False,
    ),
    (
        "argv argument .. seul",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", ".."]}},
        False,
    ),
    (
        "argv argument .. dans une option",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "--d=../a"]}},
        False,
    ),
    (
        "argv argument .. sans segment",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "a..b"]}},
        False,
    ),
    (
        "argv argument absolu sous /usr/bin",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "/usr/bin/y"]}},
        False,
    ),
    (
        "argv argument absolu sous /tmp",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "/tmp/x"]}},
        False,
    ),
    (
        "argv argument absolu hors dossiers systeme",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/flatpak", "/home/u/x.py"],
            }
        },
        False,
    ),
    (
        "argv argument relatif avec slash",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "tmp/x"]}},
        False,
    ),
    (
        "argv argument option collee a un chemin",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "-f../x"]}},
        False,
    ),
    (
        "argv argument avec espace",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "a b"]}},
        False,
    ),
    (
        "argv argument commence par un tiret seul",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "-"]}},
        False,
    ),
    (
        "argv argument trois tirets",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "---x"]}},
        False,
    ),
    (
        "argv argument vide",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", ""]}},
        False,
    ),
    (
        "argv argument avec point-virgule",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "a;id"]}},
        False,
    ),
    (
        "argv argument avec dollar",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "$x"]}},
        False,
    ),
    (
        "argv argument option courte hors liste",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "list", "-y"]}},
        False,
    ),
    (
        "argv option en premier sans sous-commande",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/flatpak", "--columns=ref,active:f"],
            }
        },
        False,
    ),
    (
        "argv argument mot nu",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", "list"]}},
        True,
    ),
    (
        "argv interpreteur python3",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/python3", "-V"]}},
        False,
    ),
    (
        "argv lanceur env",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/env", "x"]}},
        False,
    ),
    (
        "argv shell bash",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/bash", "-c", "id"]}},
        False,
    ),
    (
        "argv node-22",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/node-22", "-e", "x"]}},
        False,
    ),
    (
        "argv luajit versionne",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/luajit-2.1.1767980792", "-e", "x"],
            }
        },
        False,
    ),
    (
        "argv rpm --eval",
        {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/rpm", "--eval", "%(id)"]}},
        False,
    ),
    (
        "argv sed",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/sed", "-n", "1e id", "etc/hostname"],
            }
        },
        False,
    ),
    (
        "argv flock -c",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/flock", "tmp/l", "-c", "id"],
            }
        },
        False,
    ),
    (
        "argv git -c",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/git", "-c", "alias.x=!id", "x"],
            }
        },
        False,
    ),
    (
        "argv time bash",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/time", "/usr/bin/bash", "-c", "id"],
            }
        },
        False,
    ),
    (
        "argv cp relatifs",
        {
            "probe": {
                "kind": "fingerprint",
                "argv": ["/usr/bin/cp", "tmp/evil", "etc/sudoers.d/x"],
            }
        },
        False,
    ),
    *[
        (
            f"argv flatpak {nom} (F26)",
            {"probe": {"kind": "fingerprint", "argv": ["/usr/bin/flatpak", *args]}},
            attendu,
        )
        for nom, args, attendu in [
            ("uninstall --all", ["uninstall", "--all"], False),
            ("run --command", ["run", "--command=sh", "org.x.App"], False),
            ("install", ["install", "org.x.App"], False),
            ("override", ["override", "--user", "--filesystem=host"], False),
            ("remote-modify", ["remote-modify", "--no-enumerate", "r"], False),
            ("sous-commande en second", ["--system", "list"], False),
            ("list option inconnue", ["list", "--all"], False),
            ("list option --columns vide", ["list", "--columns="], False),
            ("list --columns majuscule", ["list", "--columns=Ref"], False),
            ("list --columns avec tiret", ["list", "--columns=ref,all-x"], False),
            ("list mot en plus", ["list", "org.x.App"], False),
            ("list --app --runtime", ["list", "--app", "--runtime"], True),
            ("list --user", ["list", "--user"], True),
            ("list --columns=ref", ["list", "--columns=ref"], True),
        ]
    ],
    ("dnf5 sans fin complete", {"probe": {"kind": "dnf5", "argv": []}}, False),
    ("fwupd sans fin complete", {"probe": {"kind": "fwupd", "argv": []}}, False),
    (
        "fwupd argv non vide",
        {"probe": {"kind": "fwupd", "argv": ["/usr/bin/x"]}},
        False,
    ),
]


@pytest.mark.parametrize(
    ("surcharges", "attendu"),
    [pytest.param(s, a, id=i) for i, s, a in _CAS],
)
def test_spec_et_runtime_acceptent_les_memes_descripteurs(
    surcharges: dict[str, Any], attendu: bool
) -> None:
    # Arrange : un descripteur valide, modifié champ par champ
    data = {**_descripteur_valide(), **surcharges}

    # Act
    runtime_accepte = parse_descriptor(data) is not None
    try:
        _job_depuis(data)
        spec_accepte = True
    except ValueError:
        spec_accepte = False

    # Assert : l'attendu est écrit à la main, et les deux validations concordent
    assert runtime_accepte is attendu
    assert spec_accepte is attendu


def test_spec_et_runtime_concordent_sur_end_texts_incomplet_ou_inconnu() -> None:
    valide = _descripteur_valide()
    sans_nothing = {**valide, "end_texts": _sans(valide, Outcome.NOTHING)}
    issue_inconnue = {
        **valide,
        "end_texts": {**valide["end_texts"], "bizarre": ["a", "b"]},
    }
    avec_restart = {
        **valide,
        "end_texts": {**valide["end_texts"], "success_restart": ["a", "b"]},
    }

    for data, attendu in (
        (sans_nothing, False),
        (issue_inconnue, False),
        (avec_restart, True),
    ):
        try:
            _job_depuis(data)
            spec_accepte = True
        except ValueError:
            spec_accepte = False
        assert (parse_descriptor(data) is not None) is attendu
        assert spec_accepte is attendu


def test_end_texts_modifie_apres_construction_n_altere_pas_le_job() -> None:
    # Arrange : le consommateur garde une référence à son dict
    textes = _textes(*_BASE)
    job = NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts=textes,
    )
    avant = job.to_descriptor()

    # Act : mutation après coup (texte hors limites, issue retirée)
    textes[Outcome.SUCCESS] = ("a", "x" * 500)
    del textes[Outcome.FAILURE]

    # Assert : le job est inchangé et son descripteur reste accepté par le runtime
    assert job.to_descriptor() == avant
    assert parse_descriptor(json.loads(job.to_descriptor())) is not None


def test_end_texts_du_job_est_en_lecture_seule() -> None:
    job = NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts=_textes(*_BASE),
    )

    mutable = cast("MutableMapping[Outcome, tuple[str, str]]", job.end_texts)
    with pytest.raises(TypeError):
        mutable[Outcome.SUCCESS] = ("a", "b")


def test_hash_du_job_ne_leve_pas_et_egalite_par_valeur() -> None:
    def fabrique() -> NotifiedJob:
        return NotifiedJob(
            name="demo",
            owner="demo-app",
            watched_unit="demo.service",
            scope="system",
            start_texts=("Début", "Corps"),
            end_texts=_textes(*_BASE),
        )

    assert hash(fabrique()) == hash(fabrique())
    assert fabrique() == fabrique()
    assert len({fabrique(), fabrique()}) == 1


def test_spec_n_a_qu_une_source_de_constantes() -> None:
    source = Path(spec_module.__file__).read_text(encoding="utf-8")

    assert spec_module.Outcome is runtime_module.Outcome
    assert "re.compile" not in source


_FWUPD = (
    Outcome.SUCCESS_RESTART,
    Outcome.NOTHING,
    Outcome.DONE_NO_DETAIL,
    Outcome.FAILURE,
    Outcome.INTERRUPTED,
)


def test_sonde_fwupd_est_au_catalogue_du_runtime_et_de_la_spec() -> None:
    # Attendu écrit à la main : cinq issues atteignables, jamais SUCCESS.
    assert "fwupd" in runtime_module._PROBES
    assert spec_module._PROBE_KINDS[FwupdProbe] == "fwupd"
    assert set(runtime_module.REACHABLE["fwupd"]) == {Outcome(o.value) for o in _FWUPD}
    assert runtime_module.Outcome.SUCCESS not in runtime_module.REACHABLE["fwupd"]
    assert "fwupd" not in runtime_module._SNAPSHOTS


def test_spec_et_runtime_acceptent_un_job_fwupd_aux_cinq_issues() -> None:
    job = NotifiedJob(
        name="demo",
        owner="demo-app",
        watched_unit="demo.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts=_textes(*_FWUPD),
        probe=FwupdProbe(),
    )
    data = json.loads(job.to_descriptor())

    assert data["probe"] == {"kind": "fwupd", "argv": []}
    assert parse_descriptor(data) is not None
    assert _job_depuis(data) == job
