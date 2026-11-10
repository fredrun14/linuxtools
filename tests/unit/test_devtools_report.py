"""Tests du rapport de montée (linuxtools.devtools.report)."""

from __future__ import annotations

import pytest

from linuxtools.devtools.report import (
    BumpOutcome,
    Status,
    exit_code,
    format_report,
)

_SUCCES = [
    Status.A_JOUR,
    Status.EN_ATTENTE,
    Status.SIMULE,
    Status.POUSSE,
    Status.COMMITE,
]
_ECHECS = [
    Status.REFUSE,
    Status.BLOQUE,
    Status.ECHEC,
    Status.PUSH_ECHOUE,
]


def _outcome(
    status: Status, project: str = "p", detail: str = ""
) -> BumpOutcome:
    return BumpOutcome(project, "v1.0.0", status, detail=detail)


def test_exit_code_zero_si_tout_reussit() -> None:
    outcomes = [_outcome(s) for s in _SUCCES]

    assert exit_code(outcomes) == 0


def test_exit_code_zero_si_liste_vide() -> None:
    assert exit_code([]) == 0


@pytest.mark.parametrize("echec", _ECHECS)
def test_exit_code_un_si_un_echec(echec: Status) -> None:
    outcomes = [_outcome(Status.POUSSE), _outcome(echec)]

    assert exit_code(outcomes) == 1


def test_format_report_aligne_les_colonnes() -> None:
    outcomes = [
        BumpOutcome("court", "v1.0.0", Status.POUSSE, checks="ok"),
        BumpOutcome(
            "un-projet-long", "v10.20.30", Status.REFUSE, detail="motif"
        ),
    ]

    lignes = format_report(outcomes).splitlines()

    assert lignes[0].startswith("projet")
    colonnes = {lignes[i].index("|") for i in (0, 2, 3)}
    assert colonnes == {lignes[1].index("+")}
    assert "POUSSÉ" in lignes[2]
    assert lignes[3].rstrip().endswith("motif")


def test_format_report_tronque_le_detail() -> None:
    detail = "\n".join(f"ligne {i}" for i in range(1, 31))

    rapport = format_report([_outcome(Status.ECHEC, "proj", detail)])

    assert "ligne 20" in rapport
    assert "ligne 21" not in rapport
    assert "10 ligne(s) tronquée(s)" in rapport


def test_format_report_detail_des_echecs_et_simulations_seulement() -> None:
    outcomes = [
        _outcome(Status.POUSSE, "ok", "bruit"),
        _outcome(Status.SIMULE, "sim", "plan simulé"),
    ]

    rapport = format_report(outcomes)

    assert "bruit" not in rapport
    assert "plan simulé" in rapport


def test_format_report_sans_detail_pas_de_bloc_details() -> None:
    rapport = format_report([_outcome(Status.POUSSE)])

    assert "Détails" not in rapport
