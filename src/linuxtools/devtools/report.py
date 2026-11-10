"""Statuts, rapport final et code de sortie de ``bump-consumers``."""

# stdlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

_MAX_DETAIL_LINES = 20
_HEADERS = ("projet", "ancien pin", "statut", "contrôles", "problème")


class Status(Enum):
    """Issue de la montée d'un consommateur."""

    A_JOUR = "À JOUR"
    EN_ATTENTE = "EN ATTENTE"
    SIMULE = "SIMULÉ"
    POUSSE = "POUSSÉ"
    COMMITE = "COMMITÉ"
    REFUSE = "REFUSÉ"
    BLOQUE = "BLOQUÉ"
    ECHEC = "ÉCHEC"
    PUSH_ECHOUE = "PUSH ÉCHOUÉ"


_FAILURES = frozenset(
    {Status.REFUSE, Status.BLOQUE, Status.ECHEC, Status.PUSH_ECHOUE}
)


@dataclass(frozen=True)
class BumpOutcome:
    """Résultat de la montée d'un consommateur."""

    project: str
    old_pin: str
    status: Status
    checks: str = ""
    detail: str = ""


def _row(outcome: BumpOutcome) -> tuple[str, ...]:
    """Cellules du tableau pour un résultat."""
    problem = ""
    if outcome.status in _FAILURES and outcome.detail:
        problem = outcome.detail.splitlines()[0]
    return (
        outcome.project,
        outcome.old_pin,
        outcome.status.value,
        outcome.checks,
        problem,
    )


def _truncate(detail: str) -> list[str]:
    """Tronque un détail à ``_MAX_DETAIL_LINES`` lignes."""
    lines = detail.splitlines()
    kept = lines[:_MAX_DETAIL_LINES]
    dropped = len(lines) - len(kept)
    if dropped:
        kept.append(f"[… {dropped} ligne(s) tronquée(s)]")
    return kept


def format_report(outcomes: Sequence[BumpOutcome]) -> str:
    """Rend le tableau récapitulatif suivi des détails.

    Le bloc « Détails » reprend ``detail`` (tronqué à 20 lignes) des
    échecs et des simulations (plan d'exécution).

    Args:
        outcomes: Résultats par consommateur.

    Returns:
        Rapport texte multiligne.
    """
    rows = [_HEADERS, *(_row(o) for o in outcomes)]
    widths = [max(len(r[i]) for r in rows) for i in range(len(_HEADERS))]

    def render(row: tuple[str, ...]) -> str:
        cells = [c.ljust(w) for c, w in zip(row, widths, strict=True)]
        return " | ".join(cells).rstrip()

    lines = [render(rows[0]), "-+-".join("-" * w for w in widths)]
    lines.extend(render(r) for r in rows[1:])

    shown = [
        o
        for o in outcomes
        if o.detail and (o.status in _FAILURES or o.status is Status.SIMULE)
    ]
    if shown:
        lines.extend(["", "Détails"])
        for outcome in shown:
            lines.append(f"* {outcome.project} ({outcome.status.value})")
            lines.extend(f"    {ln}" for ln in _truncate(outcome.detail))
    return "\n".join(lines)


def exit_code(outcomes: Sequence[BumpOutcome]) -> int:
    """Code de sortie : 1 si au moins un statut d'échec, sinon 0.

    Args:
        outcomes: Résultats par consommateur.

    Returns:
        0 ou 1.
    """
    return 1 if any(o.status in _FAILURES for o in outcomes) else 0
