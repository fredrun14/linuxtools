"""Description d'un job systemd notifié : issues, sondes et `NotifiedJob`.

Ce module ne contient que des données et leur validation : aucun chemin,
aucune E/S. Le descripteur JSON qu'il produit est relu, en stdlib seule, par
`runtime.py` sur le poste.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

# Source unique des motifs, plafonds et issues : `runtime.py` (F05). `Outcome` est
# celui du runtime (un seul type exposé) ; le sens runtime -> spec reste interdit.
from linuxtools.jobnotify.runtime import (
    CONTROL_RE,
    DESCRIPTOR_VERSION,
    MAX_TEXT_LEN,
    NAME_RE,
    REACHABLE,
    UNIT_RE,
    WHY_FORBIDDEN_RE,
    Outcome,
    fingerprint_argv_ok,
)

_PAIR_LEN = 2  # (résumé, corps)

__all__ = [
    "Dnf5Probe",
    "FingerprintProbe",
    "NoProbe",
    "NotifiedJob",
    "Outcome",
    "Probe",
]


@dataclass(frozen=True)
class NoProbe:
    """Aucune sonde : l'issue d'un run réussi est SUCCESS."""


@dataclass(frozen=True)
class FingerprintProbe:
    """Instantané avant/après (flatpak).

    Attributes:
        argv: Commande de l'instantané, du catalogue fermé `PROBE_COMMANDS`
            (binaire exact, sous-commande et options fixées).
    """

    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        """Gèle `argv` en tuple : une liste passée par l'appelant est copiée."""
        object.__setattr__(self, "argv", tuple(self.argv))


@dataclass(frozen=True)
class Dnf5Probe:
    """Historique dnf5 et `needs-restarting` (algorithme porté verbatim)."""


Probe = NoProbe | FingerprintProbe | Dnf5Probe

_PROBE_KINDS: Mapping[type[object], str] = {
    NoProbe: "none",
    FingerprintProbe: "fingerprint",
    Dnf5Probe: "dnf5",
}


def _check_name(value: str) -> None:
    """Valide un nom de job ou de propriétaire."""
    if NAME_RE.fullmatch(value) is None:
        raise ValueError(f"nom de job invalide : {value!r}")


def _check_unit(value: str) -> None:
    """Valide un nom d'unité `.service`."""
    if UNIT_RE.fullmatch(value) is None:
        raise ValueError(f"unité invalide : {value!r}")


def _check_text(label: str, value: object) -> None:
    """Valide un texte affiché : chaîne plafonnée, sans caractère de contrôle."""
    if (
        not isinstance(value, str)
        or len(value) > MAX_TEXT_LEN
        or CONTROL_RE.search(value) is not None
    ):
        raise ValueError(f"texte invalide ({label}) : {str(value)[:40]!r}")


def _check_pair(label: str, value: object) -> tuple[str, str]:
    """Valide un couple (résumé, corps) et le rend en tuple (copie)."""
    if not isinstance(value, tuple | list) or len(value) != _PAIR_LEN:
        raise ValueError(f"couple (résumé, corps) invalide ({label}) : {value!r}")
    summary, body = value
    _check_text(label, summary)
    _check_text(label, body)
    return summary, body


def _check_probe(probe: Probe) -> None:
    """Valide les paramètres d'une sonde (catalogue fermé, F20, F26)."""
    if isinstance(probe, FingerprintProbe) and not fingerprint_argv_ok(probe.argv):
        raise ValueError(
            f"argv de sonde invalide (hors catalogue de sondes) : {probe.argv!r}"
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
    # Exclu du hash (un mapping n'est pas hachable) ; comparé par valeur.
    end_texts: Mapping[Outcome, tuple[str, str]] = field(hash=False)
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
        if type(self.lock) is not bool:
            # `1` serait refusé plus tard, en silence, par le runtime (F16).
            raise ValueError(f"lock invalide (booléen attendu) : {self.lock!r}")
        object.__setattr__(self, "guard_after", tuple(self.guard_after))
        for unit in self.guard_after:
            _check_unit(unit)
        if self.scope not in ("system", "user"):
            raise ValueError(f"scope invalide : {self.scope!r}")
        if (
            CONTROL_RE.search(self.inhibit_why) is not None
            or WHY_FORBIDDEN_RE.search(self.inhibit_why) is not None
        ):
            raise ValueError(f"inhibit_why invalide : {self.inhibit_why!r}")
        _check_text("icon", self.icon)
        # Copies gelées : une mutation ultérieure, par l'appelant, ne peut plus
        # produire un job que le runtime refuserait en silence.
        start = _check_pair("start_texts", self.start_texts)
        ends = {
            Outcome(issue): _check_pair("end_texts", pair)
            for issue, pair in self.end_texts.items()
        }
        object.__setattr__(self, "start_texts", start)
        object.__setattr__(self, "end_texts", MappingProxyType(ends))
        _check_probe(self.probe)
        missing = sorted(REACHABLE[_PROBE_KINDS[type(self.probe)]] - ends.keys())
        if missing:
            raise ValueError(f"end_texts : issue manquante {missing[0].value}")

    def to_descriptor(self) -> str:
        """Rend le descripteur JSON lu par le runtime.

        Returns:
            JSON à clés triées, accents conservés, terminé par un saut de ligne.
        """
        argv = list(self.probe.argv) if isinstance(self.probe, FingerprintProbe) else []
        data = {
            "version": DESCRIPTOR_VERSION,
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
