"""Description d'un job systemd notifié : issues, sondes et `NotifiedJob`.

Ce module ne contient que des données et leur validation : aucun chemin,
aucune E/S. Le descripteur JSON qu'il produit est relu, en stdlib seule, par
`runtime.py` sur le poste.
"""

import enum
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_UNIT_RE = re.compile(r"[A-Za-z0-9:_.@-]+\.service")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WHY_FORBIDDEN_RE = re.compile(r"[\"'%$\\]")
_MAX_TEXT_LEN = 200
_DESCRIPTOR_VERSION = 1


class Outcome(enum.StrEnum):
    """Issue d'un run surveillé (valeurs identiques au hook : schéma figé)."""

    SUCCESS = "success"
    SUCCESS_RESTART = "success_restart"  # réussi, redémarrage requis
    NOTHING = "nothing"  # rien à mettre à jour
    DONE_NO_DETAIL = "done_no_detail"  # terminé, détail illisible
    FAILURE = "failure"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class NoProbe:
    """Aucune sonde : l'issue d'un run réussi est SUCCESS."""


@dataclass(frozen=True)
class FingerprintProbe:
    """Instantané avant/après (flatpak).

    Attributes:
        argv: Commande de l'instantané ; `argv[0]` est un chemin absolu.
    """

    argv: tuple[str, ...]


@dataclass(frozen=True)
class Dnf5Probe:
    """Historique dnf5 et `needs-restarting` (algorithme porté verbatim)."""


Probe = NoProbe | FingerprintProbe | Dnf5Probe

_BASE_OUTCOMES = frozenset({Outcome.SUCCESS, Outcome.FAILURE, Outcome.INTERRUPTED})
# Issues atteignables par sonde ; Flatpak n'annonce jamais de redémarrage.
_REACHABLE: Mapping[type[object], frozenset[Outcome]] = {
    NoProbe: _BASE_OUTCOMES,
    FingerprintProbe: _BASE_OUTCOMES | {Outcome.NOTHING, Outcome.DONE_NO_DETAIL},
    Dnf5Probe: frozenset(Outcome),
}
_PROBE_KINDS: Mapping[type[object], str] = {
    NoProbe: "none",
    FingerprintProbe: "fingerprint",
    Dnf5Probe: "dnf5",
}


def _check_name(value: str) -> None:
    """Valide un nom de job ou de propriétaire."""
    if _NAME_RE.fullmatch(value) is None:
        raise ValueError(f"nom de job invalide : {value!r}")


def _check_unit(value: str) -> None:
    """Valide un nom d'unité `.service`."""
    if _UNIT_RE.fullmatch(value) is None:
        raise ValueError(f"unité invalide : {value!r}")


def _check_text(label: str, value: str) -> None:
    """Valide un texte affiché : longueur plafonnée, sans caractère de contrôle."""
    if len(value) > _MAX_TEXT_LEN or _CONTROL_RE.search(value) is not None:
        raise ValueError(f"texte invalide ({label}) : {value[:40]!r}")


def _check_probe(probe: Probe) -> None:
    """Valide les paramètres d'une sonde (binaire en chemin absolu)."""
    if isinstance(probe, FingerprintProbe) and (
        not probe.argv
        or not probe.argv[0].startswith("/")
        or any("\x00" in arg for arg in probe.argv)
    ):
        raise ValueError(
            f"argv de sonde invalide (binaire en chemin absolu) : {probe.argv!r}"
        )


@dataclass(frozen=True)
class NotifiedJob:
    """Job systemd notifié, décrit par ses seules données.

    Attributes:
        name: Nom du job (`^[a-z0-9][a-z0-9-]{0,63}$`).
        owner: Application propriétaire (même motif), sert aux chemins.
        watched_unit: Unité `.service` surveillée.
        scope: `system` (root) ou `user` (session de l'utilisateur).
        start_texts: Couple (résumé, corps) de la notification de début.
        end_texts: Couple (résumé, corps) par issue atteignable.
        lock: Pose un verrou d'inhibition pendant le run.
        probe: Sonde qui déduit l'issue d'un run réussi.
        icon: Nom d'icône de la notification.
        inhibit_why: Motif affiché par l'inhibiteur.
        guard_after: Unités après lesquelles démarre le compagnon du verrou.
    """

    name: str
    owner: str
    watched_unit: str
    scope: Literal["system", "user"]
    start_texts: tuple[str, str]
    end_texts: Mapping[Outcome, tuple[str, str]]
    lock: bool = False
    probe: Probe = field(default_factory=NoProbe)
    icon: str = "system-software-update"
    inhibit_why: str = "Mise à jour en cours"
    guard_after: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Valide tous les champs.

        Raises:
            ValueError: Si un champ est hors motif, un texte hors limites ou
                si `end_texts` ne couvre pas toutes les issues de la sonde.
        """
        _check_name(self.name)
        _check_name(self.owner)
        _check_unit(self.watched_unit)
        for unit in self.guard_after:
            _check_unit(unit)
        if self.scope not in ("system", "user"):
            raise ValueError(f"scope invalide : {self.scope!r}")
        if (
            _CONTROL_RE.search(self.inhibit_why) is not None
            or _WHY_FORBIDDEN_RE.search(self.inhibit_why) is not None
        ):
            raise ValueError(f"inhibit_why invalide : {self.inhibit_why!r}")
        _check_text("icon", self.icon)
        for texts in (self.start_texts, *self.end_texts.values()):
            for text in texts:
                _check_text("résumé ou corps", text)
        _check_probe(self.probe)
        missing = sorted(_REACHABLE[type(self.probe)] - self.end_texts.keys())
        if missing:
            raise ValueError(f"end_texts : issue manquante {missing[0].value}")

    def to_descriptor(self) -> str:
        """Rend le descripteur JSON lu par le runtime.

        Returns:
            JSON à clés triées, accents conservés, terminé par un saut de ligne.
        """
        argv = list(self.probe.argv) if isinstance(self.probe, FingerprintProbe) else []
        data = {
            "version": _DESCRIPTOR_VERSION,
            "name": self.name,
            "owner": self.owner,
            "watched_unit": self.watched_unit,
            "scope": self.scope,
            "start_texts": list(self.start_texts),
            "end_texts": {o.value: list(t) for o, t in self.end_texts.items()},
            "lock": self.lock,
            "probe": {"kind": _PROBE_KINDS[type(self.probe)], "argv": argv},
            "icon": self.icon,
            "inhibit_why": self.inhibit_why,
            "guard_after": list(self.guard_after),
        }
        return json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n"
