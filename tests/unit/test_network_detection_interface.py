"""Tests de _detect_interface sur un faux arbre sysfs (indépendants de la machine)."""

from pathlib import Path

import pytest

from linuxtools.network.scanner import _detect_interface


@pytest.fixture
def sys_net(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Faux /sys/class/net sous tmp_path, substitué au vrai pour le test."""
    racine = tmp_path / "net"
    racine.mkdir()
    monkeypatch.setattr("linuxtools.network.scanner._SYS_NET", str(racine))
    return racine


def _iface(
    racine: Path,
    nom: str,
    etat: str | None = "up",
    *,
    wifi: str | None = None,
) -> None:
    """Crée une interface factice (``wifi`` : 'wireless' ou 'phy80211')."""
    dossier = racine / nom
    dossier.mkdir()
    if etat is not None:
        (dossier / "operstate").write_text(f"{etat}\n", encoding="utf-8")
    if wifi:
        (dossier / wifi).mkdir()


def test_arbre_sysfs_absent_donne_une_chaine_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans répertoire des interfaces, aucune interface n'est détectée."""
    monkeypatch.setattr("linuxtools.network.scanner._SYS_NET", str(tmp_path / "absent"))

    assert _detect_interface() == ""


def test_aucune_interface_donne_une_chaine_vide(sys_net: Path) -> None:
    """Un répertoire vide ne donne aucune interface."""
    assert _detect_interface() == ""


@pytest.mark.parametrize(
    "prefixe", ["lo", "docker0", "br-1", "veth1", "tun0", "tap0", "virbr0"]
)
def test_interfaces_virtuelles_sont_ignorees(sys_net: Path, prefixe: str) -> None:
    """Les interfaces virtuelles actives ne sont jamais retenues."""
    _iface(sys_net, prefixe)

    assert _detect_interface() == ""


def test_operstate_absent_est_ignore(sys_net: Path) -> None:
    """Une interface sans fichier operstate est ignorée."""
    _iface(sys_net, "eth0", etat=None)

    assert _detect_interface() == ""


def test_operstate_illisible_est_ignore(sys_net: Path) -> None:
    """Une interface dont operstate est un dossier (illisible) est ignorée."""
    (sys_net / "eth0" / "operstate").mkdir(parents=True)

    assert _detect_interface() == ""


@pytest.mark.parametrize("etat", ["down", "unknown"])
def test_interface_non_up_est_ignoree(sys_net: Path, etat: str) -> None:
    """Une interface dont l'état n'est pas 'up' n'est pas retenue."""
    _iface(sys_net, "eth0", etat=etat)

    assert _detect_interface() == ""


def test_interface_filaire_active_est_retenue(sys_net: Path) -> None:
    """Une interface filaire 'up' est retournée."""
    _iface(sys_net, "enp4s0")

    assert _detect_interface() == "enp4s0"


@pytest.mark.parametrize("marqueur", ["wireless", "phy80211"])
def test_wifi_seul_est_retenu(sys_net: Path, marqueur: str) -> None:
    """Sans filaire, l'interface Wi-Fi active est retournée."""
    _iface(sys_net, "wlan0", wifi=marqueur)

    assert _detect_interface() == "wlan0"


@pytest.mark.parametrize("marqueur", ["wireless", "phy80211"])
def test_filaire_est_prioritaire_sur_le_wifi(sys_net: Path, marqueur: str) -> None:
    """Filaire et Wi-Fi actifs : le filaire l'emporte, même listé après."""
    _iface(sys_net, "eth0")
    _iface(sys_net, "aaa-wifi", wifi=marqueur)

    assert _detect_interface() == "eth0"


def test_premiere_interface_par_ordre_alphabetique(sys_net: Path) -> None:
    """Entre deux filaires actifs, la première par ordre alphabétique."""
    _iface(sys_net, "eth1")
    _iface(sys_net, "eth0")

    assert _detect_interface() == "eth0"
