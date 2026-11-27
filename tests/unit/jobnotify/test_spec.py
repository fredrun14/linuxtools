"""Tests de `linuxtools.jobnotify.spec` : issues, sondes et `NotifiedJob`."""

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from linuxtools.jobnotify.spec import (
    Dnf5Probe,
    FingerprintProbe,
    NoProbe,
    NotifiedJob,
    Outcome,
)

TEXTE = ("Résumé", "Corps")
BASE = (Outcome.SUCCESS, Outcome.FAILURE, Outcome.INTERRUPTED)
FLATPAK = (*BASE, Outcome.NOTHING, Outcome.DONE_NO_DETAIL)


def _textes(*issues: Outcome) -> dict[Outcome, tuple[str, str]]:
    """Construit un `end_texts` couvrant exactement `issues`."""
    return {issue: (f"fin {issue.value}", "corps") for issue in issues}


def _job(**surcharges: Any) -> NotifiedJob:
    """Construit un job valide, avec surcharges."""
    champs: dict[str, Any] = {
        "name": "demo",
        "owner": "demo-app",
        "watched_unit": "demo.service",
        "scope": "system",
        "start_texts": TEXTE,
        "end_texts": _textes(*BASE),
    }
    champs.update(surcharges)
    return NotifiedJob(**champs)


def test_outcome_valeurs_du_schema_fige() -> None:
    assert [o.value for o in Outcome] == [
        "success",
        "success_restart",
        "nothing",
        "done_no_detail",
        "failure",
        "interrupted",
    ]


@pytest.mark.parametrize("name", ["", "Demo", "-demo", "de mo", "a" * 65, "d/../x"])
def test_notifiedjob_leve_valueerror_si_name_invalide(name: str) -> None:
    with pytest.raises(ValueError, match="nom de job invalide"):
        _job(name=name)


def test_notifiedjob_leve_valueerror_si_owner_invalide() -> None:
    with pytest.raises(ValueError, match="nom de job invalide"):
        _job(owner="Demo App")


@pytest.mark.parametrize("unit", ["demo", "demo.timer", "de mo.service", ""])
def test_notifiedjob_refuse_watched_unit_invalide(unit: str) -> None:
    with pytest.raises(ValueError, match="unité"):
        _job(watched_unit=unit)


def test_notifiedjob_refuse_guard_after_invalide() -> None:
    with pytest.raises(ValueError, match="unité"):
        _job(guard_after=("ok.service", "mauvais.target"))


def test_notifiedjob_refuse_scope_inconnu() -> None:
    with pytest.raises(ValueError, match="scope"):
        _job(scope="global")


@pytest.mark.parametrize("why", ["a\tb", 'dit "x"', "100%", "$HOME", "ligne\nsuite"])
def test_notifiedjob_refuse_inhibit_why_avec_pourcent_ou_guillemet(why: str) -> None:
    with pytest.raises(ValueError, match="inhibit_why"):
        _job(inhibit_why=why)


@pytest.mark.parametrize(
    "texte",
    [("a\x00b", "ok"), ("ok", "a\nb"), ("x" * 201, "ok"), ("ok", "x" * 201)],
)
def test_notifiedjob_refuse_texte_hors_limites_ou_de_controle(
    texte: tuple[str, str],
) -> None:
    with pytest.raises(ValueError, match="texte"):
        _job(start_texts=texte)


def test_notifiedjob_refuse_texte_de_fin_hostile() -> None:
    fins = _textes(*BASE)
    fins[Outcome.FAILURE] = ("ok", "a\x07b")
    with pytest.raises(ValueError, match="texte"):
        _job(end_texts=fins)


def test_notifiedjob_refuse_icon_avec_caractere_de_controle() -> None:
    with pytest.raises(ValueError, match="icon"):
        _job(icon="a\nb")


@pytest.mark.parametrize(
    ("probe", "manquante"),
    [
        (NoProbe(), Outcome.INTERRUPTED),
        (FingerprintProbe(argv=("/usr/bin/flatpak", "list")), Outcome.NOTHING),
        (Dnf5Probe(), Outcome.SUCCESS_RESTART),
    ],
)
def test_notifiedjob_leve_si_end_texts_incomplet_pour_dnf5(
    probe: NoProbe | FingerprintProbe | Dnf5Probe, manquante: Outcome
) -> None:
    attendues = {
        NoProbe: BASE,
        FingerprintProbe: FLATPAK,
        Dnf5Probe: tuple(Outcome),
    }[type(probe)]
    fins = _textes(*(o for o in attendues if o is not manquante))
    with pytest.raises(ValueError, match=manquante.value):
        _job(probe=probe, end_texts=fins)


def test_notifiedjob_accepte_issues_supplementaires_non_atteignables() -> None:
    job = _job(end_texts=_textes(*Outcome))
    assert Outcome.SUCCESS_RESTART in job.end_texts


@pytest.mark.parametrize("argv", [(), ("flatpak", "list"), ("./flatpak",)])
def test_notifiedjob_refuse_argv_relatif_pour_fingerprint(
    argv: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="argv"):
        _job(probe=FingerprintProbe(argv=argv), end_texts=_textes(*FLATPAK))


def test_notifiedjob_refuse_argv_avec_octet_nul() -> None:
    with pytest.raises(ValueError, match="argv"):
        _job(
            probe=FingerprintProbe(argv=("/usr/bin/x", "a\x00b")),
            end_texts=_textes(*FLATPAK),
        )


def test_notifiedjob_construit_depuis_donnees_seules() -> None:
    job = _job()
    assert job.lock is False
    assert job.probe == NoProbe()
    assert job.icon == "system-software-update"
    assert job.inhibit_why == "Mise à jour en cours"
    assert job.guard_after == ()


def test_notifiedjob_est_fige() -> None:
    job = _job()
    champ = "name"
    with pytest.raises(FrozenInstanceError):
        setattr(job, champ, "autre")


def test_to_descriptor_roundtrip() -> None:
    job = _job(
        lock=True,
        guard_after=("a.service",),
        probe=FingerprintProbe(argv=("/usr/bin/flatpak", "list", "--columns=ref")),
        end_texts=_textes(*FLATPAK),
        scope="user",
    )

    brut = job.to_descriptor()

    assert brut.endswith("\n")
    donnees = json.loads(brut)
    assert donnees == {
        "version": 1,
        "name": "demo",
        "owner": "demo-app",
        "watched_unit": "demo.service",
        "scope": "user",
        "start_texts": ["Résumé", "Corps"],
        "end_texts": {o.value: [f"fin {o.value}", "corps"] for o in FLATPAK},
        "lock": True,
        "probe": {
            "kind": "fingerprint",
            "argv": ["/usr/bin/flatpak", "list", "--columns=ref"],
        },
        "icon": "system-software-update",
        "inhibit_why": "Mise à jour en cours",
        "guard_after": ["a.service"],
    }
    assert list(donnees) == sorted(donnees)


@pytest.mark.parametrize(
    ("probe", "kind"), [(NoProbe(), "none"), (Dnf5Probe(), "dnf5")]
)
def test_to_descriptor_kind_de_sonde_sans_argv(
    probe: NoProbe | Dnf5Probe, kind: str
) -> None:
    fins = _textes(*Outcome)
    donnees = json.loads(_job(probe=probe, end_texts=fins).to_descriptor())
    assert donnees["probe"] == {"kind": kind, "argv": []}


def test_to_descriptor_conserve_les_accents_sans_echappement() -> None:
    assert "Résumé" in _job().to_descriptor()


@pytest.mark.parametrize("lock", [1, 0, "oui", None])
def test_notifiedjob_refuse_lock_non_booleen(lock: Any) -> None:
    # `lock=1` serait accepté ici puis refusé en silence par le runtime (F16)
    with pytest.raises(ValueError, match="lock"):
        _job(lock=lock)


def test_notifiedjob_gele_guard_after_et_argv_en_tuples_hachables() -> None:
    # Arrange : listes mutables passées par l'appelant
    guard_after: Any = ["a.service"]
    argv: Any = ["/usr/bin/flatpak", "list"]

    # Act
    job = _job(
        guard_after=guard_after,
        probe=FingerprintProbe(argv=argv),
        end_texts=_textes(*FLATPAK),
    )
    guard_after.append("pirate.service")
    argv.append("--evil")

    # Assert : copies gelées, hachables, descripteur inchangé
    assert job.guard_after == ("a.service",)
    assert job.probe == FingerprintProbe(argv=("/usr/bin/flatpak", "list"))
    assert isinstance(hash(job), int)
    assert json.loads(job.to_descriptor())["probe"]["argv"] == [
        "/usr/bin/flatpak",
        "list",
    ]
