"""Tests unitaires de NotifiedJobInstaller (root_dir / home = tmp_path).

Portage de ``test_auto_update_notify_installer.py`` (fedora-post-install) : les
assertions de comportement sont reprises, seuls changent l'import, le
``NotifiedJob`` et les chemins paramétrés par ``owner``. Aucun accès au vrai
/etc, /usr, /var ni /run : tout vit sous ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Collection, Iterator
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock

import pytest

from linuxtools.filesystem.linux import write_text_secure
from linuxtools.jobnotify import installer as installer_module
from linuxtools.jobnotify import runtime
from linuxtools.jobnotify.installer import NotifiedJobInstaller
from linuxtools.jobnotify.spec import (
    Dnf5Probe,
    FingerprintProbe,
    NoProbe,
    NotifiedJob,
    Outcome,
    Probe,
)
from linuxtools.logging.base import Logger
from linuxtools.systemd.executor import SystemdExecutor, UserSystemdExecutor
from tests.unit.jobnotify.systemd_support import user_manager, wire_user_manager

_OWNER_DIR = "usr/local/libexec/fedora-post-install"
_HOOK = f"{_OWNER_DIR}/dnf5-auto-notify"
_DESC = f"{_HOOK}.json"
_GUARD = "etc/systemd/system/fedora-post-install-dnf5-auto-guard.service"
_DROPIN_DIR = "etc/systemd/system/dnf5-automatic.service.d"
_DROPIN = f"{_DROPIN_DIR}/fedora-post-install-notify.conf"
_DESKTOP = "etc/xdg/autostart/fedora-post-install-dnf5-auto-notify.desktop"
_STATE = "var/lib/fedora-post-install/dnf5-auto"
_RUN = "run/fedora-post-install/dnf5-auto"
_FILES = (_HOOK, _DESC, _GUARD, _DROPIN, _DESKTOP)
_REAL_HOOK = "/usr/local/libexec/fedora-post-install/dnf5-auto-notify"
_PACKAGE_HOOK = Path(runtime.__file__)

# Attendus écrits à la main (source indépendante du code de production).
_EXPECTED_GUARD = (
    "[Unit]\n"
    "Description=Verrou d'extinction et de veille pendant dnf5-automatic\n"
    "BindsTo=dnf5-automatic.service\n"
    "\n"
    "[Service]\n"
    "Type=exec\n"
    "ExecStart=/usr/bin/systemd-inhibit "
    "--what=shutdown:sleep:handle-lid-switch --mode=block "
    "--who=fedora-post-install "
    "--why=Mise-à-jour-automatique-en-cours /usr/bin/sleep 3600\n"
    f"ExecStartPost=-/usr/bin/python3 -I {_REAL_HOOK} start dnf5-auto\n"
)
_EXPECTED_DROPIN = (
    "[Unit]\n"
    "Wants=fedora-post-install-dnf5-auto-guard.service\n"
    "\n"
    "[Service]\n"
    f"ExecStopPost=-/usr/bin/python3 -I {_REAL_HOOK} end dnf5-auto\n"
)

# Chemins du job Flatpak (littéraux écrits à la main).
_F_HOOK = f"{_OWNER_DIR}/flatpak-auto-notify"
_F_DESC = f"{_F_HOOK}.json"
_F_GUARD = "etc/systemd/system/fedora-post-install-flatpak-auto-guard.service"
_F_DROPIN = (
    "etc/systemd/system/flatpak-automatic.service.d/fedora-post-install-notify.conf"
)
_F_DESKTOP = "etc/xdg/autostart/fedora-post-install-flatpak-auto-notify.desktop"
_F_STATE = "var/lib/fedora-post-install/flatpak-auto"
_F_RUN = "run/fedora-post-install/flatpak-auto"
_F_FILES = (_F_HOOK, _F_DESC, _F_GUARD, _F_DROPIN, _F_DESKTOP)
_F_REAL_HOOK = "/usr/local/libexec/fedora-post-install/flatpak-auto-notify"

_DEFERRED_DNF = "différé : dnf5-automatic en cours d'exécution"
_DEFERRED_FLATPAK = "différé : flatpak-automatic en cours d'exécution"


def _texts() -> dict[Outcome, tuple[str, str]]:
    """Textes de fin pour toutes les issues."""
    return dict.fromkeys(Outcome, ("Titre", "Corps"))


def _dnf_job(
    *,
    scope: Literal["system", "user"] = "system",
    lock: bool = True,
    probe: Probe | None = None,
    inhibit_why: str = "Mise-à-jour-automatique-en-cours",
) -> NotifiedJob:
    """Job système avec verrou et sonde dnf5 (équivalent de ``DNF5_AUTO``)."""
    return NotifiedJob(
        name="dnf5-auto",
        owner="fedora-post-install",
        watched_unit="dnf5-automatic.service",
        scope=scope,
        start_texts=("Début", "Corps"),
        end_texts=_texts(),
        lock=lock,
        probe=Dnf5Probe() if probe is None else probe,
        inhibit_why=inhibit_why,
    )


def _flatpak_job() -> NotifiedJob:
    """Job système avec verrou et sonde à instantané (``FLATPAK_AUTO``)."""
    return NotifiedJob(
        name="flatpak-auto",
        owner="fedora-post-install",
        watched_unit="flatpak-automatic.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts=_texts(),
        lock=True,
        probe=FingerprintProbe(argv=("/usr/bin/flatpak", "list")),
        inhibit_why="Mise-à-jour-Flatpak-automatique-en-cours",
        guard_after=("dnf5-automatic.service",),
    )


@pytest.fixture
def systemd() -> MagicMock:
    """SystemdExecutor mocké : unité inactive, reload réussi."""
    mock = MagicMock(spec=SystemdExecutor)
    mock.get_status.return_value = "inactive"
    mock.reload_systemd.return_value = True
    return mock


@pytest.fixture
def logger() -> MagicMock:
    """Logger mocké."""
    return MagicMock(spec=Logger)


@pytest.fixture
def installer(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> NotifiedJobInstaller:
    """Installeur du job dnf sous une racine temporaire."""
    return NotifiedJobInstaller(_dnf_job(), systemd, logger, root_dir=tmp_path)


@pytest.fixture
def flatpak_installer(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> NotifiedJobInstaller:
    """Installeur du job Flatpak sous la même racine temporaire."""
    return NotifiedJobInstaller(_flatpak_job(), systemd, logger, root_dir=tmp_path)


def _snapshot(root: Path) -> dict[str, tuple[bool, int, bytes]]:
    """Photographie une arborescence : (dossier ?, mode, contenu)."""
    return {
        str(p.relative_to(root)): (
            p.is_dir(),
            stat.S_IMODE(p.stat().st_mode),
            b"" if p.is_dir() else p.read_bytes(),
        )
        for p in sorted(root.rglob("*"))
    }


def _mode(root: Path, relative: str) -> int:
    """Mode POSIX d'un chemin relatif."""
    return stat.S_IMODE((root / relative).stat().st_mode)


def _simulate_hook_run_dir(root: Path, relative: str = _RUN) -> None:
    """Crée le dossier tmpfs comme le fait le runtime (``start``) : 0700."""
    run = root / relative
    run.mkdir(parents=True)
    run.chmod(0o700)


# ----------------------------------------------------------------------
# Constructeur : cohérence exécuteur / scope
# ----------------------------------------------------------------------


def test_init_leve_valueerror_si_executeur_ne_correspond_pas_au_scope(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange : un exécuteur système pour un job user, puis l'inverse
    user_job = _dnf_job(scope="user", lock=False, probe=NoProbe())
    user_systemd = MagicMock(spec=UserSystemdExecutor)

    # Act / Assert
    with pytest.raises(ValueError, match="scope"):
        NotifiedJobInstaller(user_job, systemd, logger, home=tmp_path)
    with pytest.raises(ValueError, match="scope"):
        NotifiedJobInstaller(_dnf_job(), user_systemd, logger, root_dir=tmp_path)


# ----------------------------------------------------------------------
# Installation (scope système)
# ----------------------------------------------------------------------


def test_sync_enabled_installe_les_artefacts_avec_les_bons_modes(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert : 5 fichiers en 0644, dossier d'état 0755 ; le dossier tmpfs est
    # créé par le runtime (0700), pas par l'installeur
    for relative in _FILES:
        assert (tmp_path / relative).is_file()
        assert _mode(tmp_path, relative) == 0o644
    assert _mode(tmp_path, _STATE) == 0o755
    assert not (tmp_path / _RUN).exists()
    assert len(actions) == 6
    assert all(not a.startswith("[dry-run]") for a in actions)


def test_dossiers_crees_en_0755_malgre_un_umask_restrictif(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange
    old = os.umask(0o077)
    try:
        # Act
        installer.sync(enabled=True, dry_run=False)
    finally:
        os.umask(old)

    # Assert
    assert _mode(tmp_path, "etc/systemd/system") == 0o755
    assert _mode(tmp_path, _OWNER_DIR) == 0o755


def test_compagnon_contenu_exact(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    installer.sync(enabled=True, dry_run=False)
    text = (tmp_path / _GUARD).read_text(encoding="utf-8")

    # Assert
    assert text == _EXPECTED_GUARD
    assert "--what=shutdown:sleep:handle-lid-switch" in text
    assert "/usr/bin/sleep 3600" in text
    assert "BindsTo=dnf5-automatic.service" in text
    assert "[Install]" not in text
    assert str(tmp_path) not in text  # chemin réel de production, jamais root_dir


def test_dropin_contenu_exact_sans_after_prefixe_tiret(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    installer.sync(enabled=True, dry_run=False)
    text = (tmp_path / _DROPIN).read_text(encoding="utf-8")

    # Assert
    assert text == _EXPECTED_DROPIN
    assert "After=" not in text
    assert "ExecStopPost=-" in text


def test_desktop_contenu_exact(installer: NotifiedJobInstaller, tmp_path: Path) -> None:
    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (tmp_path / _DESKTOP).read_text(encoding="utf-8") == (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Notification dnf5-auto\n"
        f"Exec=/usr/bin/python3 -I {_REAL_HOOK} login dnf5-auto\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-Phase=Applications\n"
    )


def test_runtime_installe_est_identique_au_fichier_du_paquet(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : octet pour octet
    assert (tmp_path / _HOOK).read_bytes() == _PACKAGE_HOOK.read_bytes()


def test_descripteur_installe_est_celui_du_job(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (tmp_path / _DESC).read_text(encoding="utf-8") == _dnf_job().to_descriptor()


def test_sync_ecrit_descripteur_runtime_unites_puis_reload(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : journal ordonné des écritures (fichier final) et du reload
    events: list[str] = []
    real_write = write_text_secure

    def _spy(path: Path, content: str, mode: int, *, exclusive: bool) -> None:
        events.append(Path(path).name.split(".", 1)[1].rsplit(".", 2)[0])
        real_write(path, content, mode, exclusive=exclusive)

    monkeypatch.setattr(installer_module, "write_text_secure", _spy)

    def _reload() -> bool:
        events.append("RELOAD")
        return True

    systemd.reload_systemd.side_effect = _reload

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : descripteur, runtime, unités, puis UN seul reload en dernier
    assert events[:2] == ["dnf5-auto-notify.json", "dnf5-auto-notify"]
    assert events.index("fedora-post-install-dnf5-auto-guard.service") > 1
    assert events.index("fedora-post-install-notify.conf") > 1
    assert events.count("RELOAD") == 1
    assert events[-1] == "RELOAD"


def test_sync_dossier_tmpfs_disparu_apres_reboot_deja_conforme(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange : le runtime a créé le dossier tmpfs, puis un reboot l'efface
    installer.sync(enabled=True, dry_run=False)
    _simulate_hook_run_dir(tmp_path)
    shutil.rmtree(tmp_path / "run")

    # Act / Assert
    assert installer.sync(enabled=True, dry_run=False) == []
    assert not (tmp_path / _RUN).exists()


def test_sync_idempotent_retourne_liste_vide_et_aucun_reload(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    systemd.reload_systemd.reset_mock()
    before = _snapshot(tmp_path)

    # Act
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert
    assert actions == []
    systemd.reload_systemd.assert_not_called()
    assert _snapshot(tmp_path) == before


def test_sync_derive_reecrite_et_reload(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange : contenu de l'unité altéré
    installer.sync(enabled=True, dry_run=False)
    systemd.reload_systemd.reset_mock()
    (tmp_path / _GUARD).write_text("altéré\n", encoding="utf-8")

    # Act
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert
    assert len(actions) == 1
    assert (tmp_path / _GUARD).read_text(encoding="utf-8") == _EXPECTED_GUARD
    systemd.reload_systemd.assert_called_once_with()


def test_sync_derive_de_mode_corrigee_sans_reload_pour_un_fichier_non_unite(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange : mode du runtime dérivé
    installer.sync(enabled=True, dry_run=False)
    systemd.reload_systemd.reset_mock()
    (tmp_path / _HOOK).chmod(0o666)

    # Act
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert
    assert len(actions) == 1
    assert _mode(tmp_path, _HOOK) == 0o644
    systemd.reload_systemd.assert_not_called()


def test_sync_derive_de_mode_du_dossier_d_etat_corrigee(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    (tmp_path / _STATE).chmod(0o777)

    # Act
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert
    assert len(actions) == 1
    assert _mode(tmp_path, _STATE) == 0o755


# ----------------------------------------------------------------------
# Verrou, sonde et lignes Exec
# ----------------------------------------------------------------------


def test_sans_verrou_aucun_compagnon_ni_inhibiteur(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange
    job = _dnf_job(lock=False, probe=NoProbe())
    installer = NotifiedJobInstaller(job, systemd, logger, root_dir=tmp_path)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : ni compagnon, ni inhibiteur, ni Wants ; le drop-in démarre le run
    assert not (tmp_path / _GUARD).exists()
    dropin = (tmp_path / _DROPIN).read_text(encoding="utf-8")
    assert dropin == (
        "[Service]\n"
        f"ExecStartPre=-/usr/bin/python3 -I {_REAL_HOOK} start dnf5-auto\n"
        f"ExecStopPost=-/usr/bin/python3 -I {_REAL_HOOK} end dnf5-auto\n"
    )
    for path in tmp_path.rglob("*"):
        if (
            path.is_file()
            and path.suffix != ".json"
            and path.name != "dnf5-auto-notify"
        ):
            text = path.read_text(encoding="utf-8")
            assert "systemd-inhibit" not in text
            assert "Wants=" not in text
            assert "BindsTo" not in text


def test_unites_avec_verrou(
    flatpak_installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    flatpak_installer.sync(enabled=True, dry_run=False)
    guard = (tmp_path / _F_GUARD).read_text(encoding="utf-8")
    dropin = (tmp_path / _F_DROPIN).read_text(encoding="utf-8")

    # Assert : compagnon verrouillé, ordonné après dnf, démarre le run ; drop-in
    # qui le réclame et prend l'instantané avant le run
    assert "--what=shutdown:sleep:handle-lid-switch" in guard
    assert "BindsTo=flatpak-automatic.service\n" in guard
    assert "After=dnf5-automatic.service\n" in guard
    assert (
        f"ExecStartPost=-/usr/bin/python3 -I {_F_REAL_HOOK} start flatpak-auto\n"
        in guard
    )
    assert "Wants=fedora-post-install-flatpak-auto-guard.service\n" in dropin
    assert (
        f"ExecStartPre=-/usr/bin/python3 -I {_F_REAL_HOOK} snapshot flatpak-auto\n"
        in dropin
    )
    assert " start\n" not in dropin


def test_unites_lignes_exec_tolerantes(
    installer: NotifiedJobInstaller,
    flatpak_installer: NotifiedJobInstaller,
    tmp_path: Path,
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    flatpak_installer.sync(enabled=True, dry_run=False)

    # Act : toute ligne Exec qui lance le runtime, dans toutes les unités écrites
    lignes = [
        ligne
        for relative in (_GUARD, _DROPIN, _F_GUARD, _F_DROPIN)
        for ligne in (tmp_path / relative).read_text(encoding="utf-8").splitlines()
        if "/usr/bin/python3" in ligne
    ]

    # Assert : préfixe `-` partout (A-07 : un échec ne casse pas le service)
    assert len(lignes) == 5
    assert all(ligne.split("=", 1)[1].startswith("-") for ligne in lignes)


def test_why_avec_espaces_est_cite_dans_le_compagnon(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange : le motif par défaut contient des espaces
    job = _dnf_job(inhibit_why="Mise à jour en cours")
    installer = NotifiedJobInstaller(job, systemd, logger, root_dir=tmp_path)

    # Act
    installer.sync(enabled=True, dry_run=False)
    text = (tmp_path / _GUARD).read_text(encoding="utf-8")

    # Assert : un seul argument pour systemd (découpe sur les espaces)
    assert '"--why=Mise à jour en cours"' in text


def test_why_des_compagnons_sans_caractere_a_echapper(
    installer: NotifiedJobInstaller,
    flatpak_installer: NotifiedJobInstaller,
    tmp_path: Path,
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    flatpak_installer.sync(enabled=True, dry_run=False)

    for relative in (_GUARD, _F_GUARD):
        line = next(
            ln
            for ln in (tmp_path / relative).read_text(encoding="utf-8").splitlines()
            if ln.startswith("ExecStart=")
        )

        # Act
        why = next(arg for arg in line.split() if arg.startswith("--why="))

        # Assert : ni guillemet, ni % ni $ ni backslash (interprétés par systemd)
        assert not any(c in why for c in "\"'%$\\")


def test_passage_sans_verrou_retire_le_compagnon_perime(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange : installé avec verrou, puis le job n'en veut plus
    installer.sync(enabled=True, dry_run=False)
    systemd.reload_systemd.reset_mock()
    sans = NotifiedJobInstaller(
        _dnf_job(lock=False, probe=NoProbe()), systemd, logger, root_dir=tmp_path
    )

    # Act
    actions = sans.sync(enabled=True, dry_run=False)

    # Assert : compagnon retiré, drop-in réécrit, un reload
    assert not (tmp_path / _GUARD).exists()
    assert any("Retiré" in a and "guard.service" in a for a in actions)
    assert "Wants=" not in (tmp_path / _DROPIN).read_text(encoding="utf-8")
    systemd.reload_systemd.assert_called_once_with()


def test_passage_sans_verrou_en_dry_run_annonce_le_retrait_du_compagnon(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    systemd.reload_systemd.reset_mock()
    before = _snapshot(tmp_path)
    sans = NotifiedJobInstaller(
        _dnf_job(lock=False, probe=NoProbe()), systemd, logger, root_dir=tmp_path
    )

    # Act
    actions = sans.sync(enabled=True, dry_run=True)

    # Assert : rien n'est touché, l'action est annoncée
    assert _snapshot(tmp_path) == before
    assert any(a.startswith("[dry-run] Retirerait") and "guard" in a for a in actions)
    systemd.reload_systemd.assert_not_called()


# ----------------------------------------------------------------------
# Retrait
# ----------------------------------------------------------------------


def test_sync_enabled_false_retire_les_artefacts_et_dossiers_d_etat(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange : le runtime a créé le dossier tmpfs et son état
    installer.sync(enabled=True, dry_run=False)
    _simulate_hook_run_dir(tmp_path)
    (tmp_path / _STATE / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / _RUN / "lock").write_text("", encoding="utf-8")
    systemd.reload_systemd.reset_mock()

    # Act
    actions = installer.sync(enabled=False, dry_run=False)

    # Assert : tout a disparu, dossiers vides compris
    for relative in (*_FILES, _STATE, _RUN):
        assert not (tmp_path / relative).exists()
    assert not (tmp_path / _OWNER_DIR).exists()
    assert not (tmp_path / _DROPIN_DIR).exists()
    assert not (tmp_path / "var/lib/fedora-post-install").exists()
    assert not (tmp_path / "run/fedora-post-install").exists()
    assert len(actions) == 13  # 5 artefacts, 2 fichiers d'état, 6 dossiers
    systemd.reload_systemd.assert_called_once_with()


def test_sync_enabled_false_garde_un_dossier_non_vide(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange : un fichier étranger dans le dossier du drop-in
    installer.sync(enabled=True, dry_run=False)
    foreign = tmp_path / _DROPIN_DIR / "autre.conf"
    foreign.write_text("[Service]\n", encoding="utf-8")

    # Act
    installer.sync(enabled=False, dry_run=False)

    # Assert : le fichier étranger et son dossier subsistent
    assert foreign.is_file()


def test_sync_retrait_efface_les_ids_numeriques_et_elague_run(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange : le runtime a écrit un ID par uid (fichier 0600) sous `ids/` (F02)
    installer.sync(enabled=True, dry_run=False)
    ids = tmp_path / _RUN / "ids"
    ids.mkdir(parents=True, mode=0o700, exist_ok=True)
    for uid in ("0", "1000"):
        (ids / uid).write_text("42\n", encoding="utf-8")

    # Act
    actions = installer.sync(enabled=False, dry_run=False)

    # Assert : ni `ids/`, ni `run/<owner>/<job>`, ni `run/<owner>` ne subsistent
    assert not (tmp_path / "run/fedora-post-install").exists()
    assert f"Retiré {ids / '1000'}" in actions


def test_sync_retrait_dry_run_annonce_les_ids_numeriques(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    ids = tmp_path / _RUN / "ids"
    ids.mkdir(parents=True, mode=0o700, exist_ok=True)
    (ids / "1000").write_text("42\n", encoding="utf-8")

    # Act
    actions = installer.sync(enabled=False, dry_run=True)

    # Assert : annoncé, rien retiré
    assert f"[dry-run] Retirerait {ids / '1000'}" in actions
    assert (ids / "1000").is_file()


def test_sync_retrait_ne_suit_pas_un_lien_ni_un_dossier_nomme_comme_un_uid(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange : `ids/1000` est un lien, `ids/1001` un dossier : jamais retirés
    installer.sync(enabled=True, dry_run=False)
    ids = tmp_path / _RUN / "ids"
    ids.mkdir(parents=True, mode=0o700, exist_ok=True)
    cible = tmp_path / "cible"
    cible.write_text("x", encoding="utf-8")
    (ids / "1000").symlink_to(cible)
    (ids / "1001").mkdir()

    # Act
    installer.sync(enabled=False, dry_run=False)

    # Assert
    assert (ids / "1000").is_symlink()
    assert cible.read_text(encoding="utf-8") == "x"
    assert (ids / "1001").is_dir()


def test_sync_retrait_ne_touche_que_les_chemins_constants(
    installer: NotifiedJobInstaller,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : fichiers etrangers dans chacun des dossiers gérés ; rmtree interdit
    installer.sync(enabled=True, dry_run=False)
    _simulate_hook_run_dir(tmp_path)
    etrangers = [
        tmp_path / _OWNER_DIR / "autre-notify",
        tmp_path / _STATE / "autre.json",
        tmp_path / _RUN / "ids" / "autre",
        tmp_path / "var/lib/fedora-post-install" / "autre-job" / "state.json",
    ]
    for path in etrangers:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    def _interdit(*_args: object, **_kwargs: object) -> None:
        pytest.fail("rmtree interdit au retrait")

    monkeypatch.setattr(shutil, "rmtree", _interdit)

    # Act
    installer.sync(enabled=False, dry_run=False)

    # Assert : les artefacts constants ont disparu, tout le reste est intact
    for relative in _FILES:
        assert not (tmp_path / relative).exists()
    for path in etrangers:
        assert path.read_text(encoding="utf-8") == "x"


def test_sync_enabled_false_a_vide_retourne_liste_vide(
    installer: NotifiedJobInstaller, systemd: MagicMock
) -> None:
    # Act
    actions = installer.sync(enabled=False, dry_run=False)

    # Assert
    assert actions == []
    systemd.reload_systemd.assert_not_called()


def test_sync_enabled_false_sans_unite_ne_recharge_pas_systemd(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange : seul le .desktop est présent
    desktop = tmp_path / _DESKTOP
    desktop.parent.mkdir(parents=True)
    desktop.write_text("x", encoding="utf-8")

    # Act
    actions = installer.sync(enabled=False, dry_run=False)

    # Assert
    assert len(actions) == 1
    assert not desktop.exists()
    systemd.reload_systemd.assert_not_called()


def test_sync_ne_touche_ni_automatic_conf_ni_timer(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange
    conf = tmp_path / "etc/dnf/automatic.conf"
    timer = tmp_path / "etc/systemd/system/dnf5-automatic.timer.d/override.conf"
    conf.parent.mkdir(parents=True)
    timer.parent.mkdir(parents=True)
    conf.write_text("[commands]\napply_updates = yes\n", encoding="utf-8")
    timer.write_text("[Timer]\nOnCalendar=daily\n", encoding="utf-8")
    conf.chmod(0o600)
    expected = (
        conf.read_bytes(),
        timer.read_bytes(),
        _mode(tmp_path, "etc/dnf/automatic.conf"),
    )

    # Act : installation puis retrait
    installer.sync(enabled=True, dry_run=False)
    installer.sync(enabled=False, dry_run=False)

    # Assert
    assert (
        conf.read_bytes(),
        timer.read_bytes(),
        _mode(tmp_path, "etc/dnf/automatic.conf"),
    ) == expected


# ----------------------------------------------------------------------
# Dry-run
# ----------------------------------------------------------------------


def test_sync_dry_run_n_ecrit_rien(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange : racine vide, puis racine installée
    empty = _snapshot(tmp_path)

    # Act / Assert : installation simulée
    actions = installer.sync(enabled=True, dry_run=True)
    assert _snapshot(tmp_path) == empty
    assert len(actions) == 6
    assert all(a.startswith("[dry-run]") for a in actions)

    # Retrait simulé sur une racine installée
    installer.sync(enabled=True, dry_run=False)
    _simulate_hook_run_dir(tmp_path)
    installed = _snapshot(tmp_path)
    systemd.reset_mock()
    actions = installer.sync(enabled=False, dry_run=True)
    assert _snapshot(tmp_path) == installed
    assert all(a.startswith("[dry-run] Retirerait") for a in actions)
    assert any(_RUN in a for a in actions)
    systemd.reload_systemd.assert_not_called()


def test_sync_dry_run_n_appelle_ni_reload_ni_mkdir(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : toute écriture ou création de dossier ferait échouer le test
    def _interdit(*_args: object, **_kwargs: object) -> None:
        pytest.fail("écriture interdite en dry-run")

    monkeypatch.setattr(Path, "mkdir", _interdit)
    monkeypatch.setattr(installer_module, "write_text_secure", _interdit)

    # Act
    installer.sync(enabled=True, dry_run=True)

    # Assert
    systemd.reload_systemd.assert_not_called()


def test_sync_dry_run_sans_sudo_dossier_run_illisible_sans_traceback(
    installer: NotifiedJobInstaller,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : /run/<owner> (root 0700) existe et est illisible pour un non-root.
    # On simule l'illisibilité en faisant lever PermissionError à is_symlink().
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    _simulate_hook_run_dir(tmp_path)
    parent = tmp_path / "run" / "fedora-post-install"
    original = Path.is_symlink

    def _is_symlink(self: Path) -> bool:
        if parent in self.parents:
            raise PermissionError(13, "Permission denied", str(self))
        return original(self)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)

    # Act
    actions = installer.sync(enabled=True, dry_run=True)

    # Assert : les actions sont rendues, aucune exception
    assert len(actions) == 6
    assert all(a.startswith("[dry-run]") for a in actions)


@pytest.fixture
def run_illisible(tmp_path: Path) -> Iterator[Path]:
    """`/run/<owner>` en 0000 (réel, non simulé) : illisible pour un non-root."""
    if os.geteuid() == 0:
        pytest.skip("root traverse un dossier 0000")
    _simulate_hook_run_dir(tmp_path)
    parent = tmp_path / "run" / "fedora-post-install"
    parent.chmod(0o000)
    yield parent
    parent.chmod(0o700)


def test_sync_retrait_dry_run_sans_sudo_dossier_run_illisible_tolere(
    installer: NotifiedJobInstaller, run_illisible: Path
) -> None:
    # Arrange : /run/<owner> illisible (F01), rien d'installé

    # Act
    actions = installer.sync(enabled=False, dry_run=True)

    # Assert : rien à planifier sous le dossier illisible, aucune exception
    assert all(a.startswith("[dry-run]") for a in actions)
    assert not any(str(run_illisible) in a for a in actions)


def test_sync_retrait_reel_dossier_run_illisible_leve_runtimeerror(
    installer: NotifiedJobInstaller, run_illisible: Path
) -> None:
    # Arrange : idem, mais le retrait est réel

    # Act / Assert : le contrat est RuntimeError, jamais PermissionError brute
    with pytest.raises(RuntimeError, match="illisible") as excinfo:
        installer.sync(enabled=False, dry_run=False)
    assert isinstance(excinfo.value.__cause__, PermissionError)


# ----------------------------------------------------------------------
# Liens symboliques et erreurs d'écriture [SEC]
# ----------------------------------------------------------------------


def test_sync_refuse_lien_symbolique_avant_toute_action(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange : un composant du chemin du compagnon est un lien hors racine
    outside = tmp_path.parent / f"{tmp_path.name}-dehors"
    outside.mkdir()
    link = tmp_path / "etc/systemd/system"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    # Act / Assert : refus, y compris en dry-run, avant tout appel systemd
    for dry_run in (True, False):
        with pytest.raises(RuntimeError, match="Lien symbolique refusé"):
            installer.sync(enabled=True, dry_run=dry_run)
    assert list(outside.iterdir()) == []
    assert not (tmp_path / _HOOK).exists()
    assert not (tmp_path / _DESC).exists()
    systemd.get_status.assert_not_called()
    systemd.reload_systemd.assert_not_called()


@pytest.mark.parametrize(
    ("job", "link_relative"),
    [
        (_dnf_job(), "etc/systemd/system"),  # composant parent
        (_dnf_job(), _GUARD),  # cible elle-même
        (_dnf_job(), _DESC),  # descripteur
        (_dnf_job(), "var/lib/fedora-post-install"),  # parent d'état
        (_dnf_job(), _RUN),  # dossier d'exécution lui-même
        (_dnf_job(), f"{_RUN}/ids"),  # dossier des ids (F19)
        (_flatpak_job(), "etc/systemd/system"),
        (_flatpak_job(), _F_GUARD),
        (_flatpak_job(), "var/lib/fedora-post-install"),
        (_flatpak_job(), _F_RUN),
    ],
    ids=[
        "dnf-parent",
        "dnf-cible",
        "dnf-descripteur",
        "dnf-parent-etat",
        "dnf-run",
        "dnf-ids",
        "flatpak-parent",
        "flatpak-cible",
        "flatpak-parent-etat",
        "flatpak-run",
    ],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_sync_lien_symbolique_refuse(
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
    job: NotifiedJob,
    link_relative: str,
    *,
    enabled: bool,
) -> None:
    # Arrange : le lien pointe hors de la racine
    installer = NotifiedJobInstaller(job, systemd, logger, root_dir=tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-dehors"
    outside.mkdir()
    link = tmp_path / link_relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Lien symbolique refusé"):
        installer.sync(enabled=enabled, dry_run=False)

    # Rien n'a été écrit à travers le lien, ni ailleurs
    assert list(outside.iterdir()) == []
    assert not (tmp_path / _OWNER_DIR / f"{job.name}-notify").exists()


def test_sync_retrait_ne_parcourt_pas_ids_devenu_lien_apres_le_controle(
    installer: NotifiedJobInstaller,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : course simulée, `ids` devient un lien vers un dossier d'uid
    installer.sync(enabled=True, dry_run=False)
    outside = tmp_path.parent / f"{tmp_path.name}-dehors"
    outside.mkdir()
    (outside / "1000").write_text("x", encoding="utf-8")
    ids = tmp_path / _RUN / "ids"
    ids.parent.mkdir(parents=True, exist_ok=True)
    ids.symlink_to(outside)
    monkeypatch.setattr(installer, "_refuse_all_symlinks", lambda **_: None)

    # Act / Assert : `iterdir()` ne suit jamais le lien (F19)
    for dry_run in (True, False):
        with pytest.raises(RuntimeError, match="Lien symbolique refusé"):
            installer.sync(enabled=False, dry_run=dry_run)
    assert (outside / "1000").read_text(encoding="utf-8") == "x"


def test_sync_racine_symbolique_exempte(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange : root_dir lui-même est un lien (ex. /tmp macOS-like)
    real = tmp_path / "reel"
    real.mkdir()
    link = tmp_path / "lien"
    link.symlink_to(real)
    installer = NotifiedJobInstaller(_dnf_job(), systemd, logger, root_dir=link)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (real / _HOOK).is_file()


def test_sync_ecriture_refusee_traduite_en_runtime_error(
    installer: NotifiedJobInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange : course simulée (la cible devient un lien après le contrôle)
    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("ELOOP")

    monkeypatch.setattr(installer_module, "write_text_secure", _refuse)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Écriture refusée") as info:
        installer.sync(enabled=True, dry_run=False)
    assert isinstance(info.value.__cause__, OSError)


def test_sync_creation_de_dossier_refusee_traduite_en_runtime_error(
    installer: NotifiedJobInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", _refuse)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Écriture refusée") as info:
        installer.sync(enabled=True, dry_run=False)
    assert isinstance(info.value.__cause__, OSError)


def test_sync_retrait_refuse_traduit_en_runtime_error(
    installer: NotifiedJobInstaller, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "unlink", _refuse)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Retrait refusé") as info:
        installer.sync(enabled=False, dry_run=False)
    assert isinstance(info.value.__cause__, OSError)


def test_sync_reload_en_echec_leve_runtime_error(
    installer: NotifiedJobInstaller, systemd: MagicMock
) -> None:
    # Arrange
    systemd.reload_systemd.return_value = False

    # Act / Assert
    with pytest.raises(RuntimeError, match="daemon-reload"):
        installer.sync(enabled=True, dry_run=False)


# ----------------------------------------------------------------------
# Report si un run est en cours
# ----------------------------------------------------------------------


def test_sync_differe_si_run_en_cours(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange
    systemd.get_status.return_value = "activating"

    # Act
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert : rien n'est modifié, avertissement journalisé
    assert actions == [_DEFERRED_DNF]
    assert list(tmp_path.rglob("*")) == []
    systemd.get_status.assert_any_call("fedora-post-install-dnf5-auto-guard.service")
    systemd.reload_systemd.assert_not_called()
    assert any("⚠" in c.args[0] for c in logger.log_info.call_args_list)


@pytest.mark.parametrize(
    ("guard", "dnf"),
    [
        ("inactive", "deactivating"),
        ("inactive", "active"),
        ("active", "inactive"),
        ("activating", "inactive"),
    ],
    ids=["dnf_deactivating", "dnf_active", "compagnon_actif", "compagnon_activating"],
)
def test_sync_retrait_differe_pendant_toute_la_fenetre_du_run(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
    guard: str,
    dnf: str,
) -> None:
    # Arrange : artefacts installés, puis un run en cours (F22, R1)
    installer.sync(enabled=True, dry_run=False)
    before = _snapshot(tmp_path)
    systemd.reload_systemd.reset_mock()
    states = {
        "dnf5-automatic.service": dnf,
        "fedora-post-install-dnf5-auto-guard.service": guard,
    }
    systemd.get_status.side_effect = lambda unit: states[unit]

    # Act
    actions = installer.sync(enabled=False, dry_run=False)

    # Assert : artefacts intacts, avertissement, action différée
    assert actions == [_DEFERRED_DNF]
    assert _snapshot(tmp_path) == before
    systemd.reload_systemd.assert_not_called()
    assert any("⚠" in c.args[0] for c in logger.log_info.call_args_list)


def test_sync_retrait_normal_si_compagnon_et_dnf_inactifs(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    systemd.get_status.side_effect = lambda _unit: "inactive"

    # Act
    installer.sync(enabled=False, dry_run=False)

    # Assert
    assert not (tmp_path / _OWNER_DIR).exists()


def test_sync_differe_aussi_le_retrait_si_run_en_cours(
    installer: NotifiedJobInstaller, systemd: MagicMock, tmp_path: Path
) -> None:
    # Arrange
    installer.sync(enabled=True, dry_run=False)
    before = _snapshot(tmp_path)
    systemd.get_status.return_value = "activating"

    # Act
    actions = installer.sync(enabled=False, dry_run=False)

    # Assert
    assert actions == [_DEFERRED_DNF]
    assert _snapshot(tmp_path) == before


def test_sync_ne_differe_pas_si_aucune_unite_ne_change(
    installer: NotifiedJobInstaller, systemd: MagicMock
) -> None:
    # Arrange : installé et conforme, puis un run démarre
    installer.sync(enabled=True, dry_run=False)
    systemd.get_status.return_value = "active"

    # Act / Assert : rien à faire, donc rien à différer
    assert installer.sync(enabled=True, dry_run=False) == []


@pytest.mark.parametrize(
    ("state", "attendu"),
    [
        ("activating", True),
        ("active", True),
        ("deactivating", True),
        ("inactive", False),
        ("failed", False),
        ("", False),
    ],
)
def test_run_in_progress_vrai_pour_activating_active_deactivating(
    installer: NotifiedJobInstaller,
    systemd: MagicMock,
    state: str,
    *,
    attendu: bool,
) -> None:
    # Arrange : seule l'unité surveillée est dans l'état testé
    states = {
        "dnf5-automatic.service": state,
        "fedora-post-install-dnf5-auto-guard.service": "inactive",
    }
    systemd.get_status.side_effect = lambda unit: states[unit]

    # Act / Assert
    assert installer.run_in_progress() is attendu


@pytest.mark.parametrize("guard", ["active", "activating"])
def test_run_in_progress_vrai_si_le_compagnon_tourne(
    installer: NotifiedJobInstaller, systemd: MagicMock, guard: str
) -> None:
    # Arrange
    states = {
        "dnf5-automatic.service": "inactive",
        "fedora-post-install-dnf5-auto-guard.service": guard,
    }
    systemd.get_status.side_effect = lambda unit: states[unit]

    # Act / Assert
    assert installer.run_in_progress() is True


def test_run_in_progress_ignore_deactivating_du_compagnon(
    installer: NotifiedJobInstaller, systemd: MagicMock
) -> None:
    # Arrange : « deactivating » ne vaut que pour l'unité surveillée
    states = {
        "dnf5-automatic.service": "inactive",
        "fedora-post-install-dnf5-auto-guard.service": "deactivating",
    }
    systemd.get_status.side_effect = lambda unit: states[unit]

    # Act / Assert
    assert installer.run_in_progress() is False


# ----------------------------------------------------------------------
# Réécriture atomique du runtime (F10)
# ----------------------------------------------------------------------


def _installe_runtime_ancien(root: Path) -> Path:
    """Place un runtime obsolète, au bon mode, avant une réécriture."""
    hook = root / _HOOK
    hook.parent.mkdir(parents=True)
    hook.write_text("ancien contenu\n", encoding="utf-8")
    hook.chmod(0o644)
    return hook


def test_sync_reecriture_du_runtime_jamais_vide_ni_tronquee(
    installer: NotifiedJobInstaller,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : un observateur s'intercale juste avant la substitution
    hook = _installe_runtime_ancien(tmp_path)
    attendu = _PACKAGE_HOOK.read_bytes()
    vus: list[tuple[bytes, bytes]] = []
    real_replace = Path.replace

    def _observateur(self: Path, target: str | Path) -> Path:
        if Path(target) == hook:
            vus.append((Path(target).read_bytes(), self.read_bytes()))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", _observateur)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : avant la substitution la cible est encore l'ancienne version
    # entière, et le temporaire déjà complet ; après, la nouvelle version.
    assert vus == [(b"ancien contenu\n", attendu)]
    assert hook.read_bytes() == attendu


def test_sync_reecriture_du_runtime_sans_temporaire_residuel_ni_mode_derive(
    installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange
    hook = _installe_runtime_ancien(tmp_path)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert sorted(p.name for p in hook.parent.iterdir()) == [
        hook.name,
        f"{hook.name}.json",
    ]
    assert _mode(tmp_path, _HOOK) == 0o644


def test_sync_echec_de_substitution_laisse_la_cible_et_nettoie_le_temporaire(
    installer: NotifiedJobInstaller,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    hook = _installe_runtime_ancien(tmp_path)

    def _echec(_self: Path, _target: str | Path) -> Path:
        raise OSError("EXDEV")

    monkeypatch.setattr(Path, "replace", _echec)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Écriture refusée"):
        installer.sync(enabled=True, dry_run=False)
    assert hook.read_bytes() == b"ancien contenu\n"
    assert [p.name for p in hook.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_sync_lien_symbolique_pose_apres_le_controle_n_est_pas_suivi(
    installer: NotifiedJobInstaller,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : course simulée, la cible devient un lien juste avant l'écriture
    hook = _installe_runtime_ancien(tmp_path)
    cible = tmp_path / "ailleurs"
    cible.write_text("intact", encoding="utf-8")
    real_write = write_text_secure
    deja: list[bool] = []

    def _course(path: Path, content: str, mode: int, *, exclusive: bool) -> None:
        if not deja:  # une seule fois, avant la première écriture
            deja.append(True)
            hook.unlink()
            hook.symlink_to(cible)
        real_write(path, content, mode, exclusive=exclusive)

    monkeypatch.setattr(installer_module, "write_text_secure", _course)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : le lien est substitué, jamais suivi
    assert cible.read_text(encoding="utf-8") == "intact"
    assert not hook.is_symlink()
    assert hook.read_bytes() == _PACKAGE_HOOK.read_bytes()


# ----------------------------------------------------------------------
# Job Flatpak (sonde à instantané) et jobs côte à côte
# ----------------------------------------------------------------------


def test_flatpak_installe_ses_artefacts_avec_les_bons_modes(
    flatpak_installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    actions = flatpak_installer.sync(enabled=True, dry_run=False)

    # Assert : 5 fichiers en 0644, dossier d'état 0755, rien côté dnf
    for relative in _F_FILES:
        assert (tmp_path / relative).is_file()
        assert _mode(tmp_path, relative) == 0o644
    assert _mode(tmp_path, _F_STATE) == 0o755
    assert not (tmp_path / _F_RUN).exists()
    assert len(actions) == 6
    for relative in (*_FILES, _STATE):
        assert not (tmp_path / relative).exists()


def test_flatpak_compagnon_contenu_exact(
    flatpak_installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    flatpak_installer.sync(enabled=True, dry_run=False)
    text = (tmp_path / _F_GUARD).read_text(encoding="utf-8")

    # Assert : littéral écrit à la main
    assert text == (
        "[Unit]\n"
        "Description=Verrou d'extinction et de veille pendant flatpak-automatic\n"
        "BindsTo=flatpak-automatic.service\n"
        "After=dnf5-automatic.service\n"
        "\n"
        "[Service]\n"
        "Type=exec\n"
        "ExecStart=/usr/bin/systemd-inhibit "
        "--what=shutdown:sleep:handle-lid-switch --mode=block "
        "--who=fedora-post-install "
        "--why=Mise-à-jour-Flatpak-automatique-en-cours /usr/bin/sleep 3600\n"
        f"ExecStartPost=-/usr/bin/python3 -I {_F_REAL_HOOK} start flatpak-auto\n"
    )
    assert "[Install]" not in text
    assert str(tmp_path) not in text  # chemin réel de production, jamais root_dir


def test_flatpak_dropin_contenu_exact_snapshot_puis_end(
    flatpak_installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Act
    flatpak_installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (tmp_path / _F_DROPIN).read_text(encoding="utf-8") == (
        "[Unit]\n"
        "Wants=fedora-post-install-flatpak-auto-guard.service\n"
        "\n"
        "[Service]\n"
        f"ExecStartPre=-/usr/bin/python3 -I {_F_REAL_HOOK} snapshot flatpak-auto\n"
        f"ExecStopPost=-/usr/bin/python3 -I {_F_REAL_HOOK} end flatpak-auto\n"
    )


def test_flatpak_sans_verrou_demarre_puis_prend_l_instantane(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange
    job = NotifiedJob(
        name="flatpak-auto",
        owner="fedora-post-install",
        watched_unit="flatpak-automatic.service",
        scope="system",
        start_texts=("Début", "Corps"),
        end_texts=_texts(),
        probe=FingerprintProbe(argv=("/usr/bin/flatpak", "list")),
    )
    installer = NotifiedJobInstaller(job, systemd, logger, root_dir=tmp_path)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : `start` puis `snapshot` avant le run, `end` après
    assert (tmp_path / _F_DROPIN).read_text(encoding="utf-8") == (
        "[Service]\n"
        f"ExecStartPre=-/usr/bin/python3 -I {_F_REAL_HOOK} start flatpak-auto\n"
        f"ExecStartPre=-/usr/bin/python3 -I {_F_REAL_HOOK} snapshot flatpak-auto\n"
        f"ExecStopPost=-/usr/bin/python3 -I {_F_REAL_HOOK} end flatpak-auto\n"
    )


def test_flatpak_idempotent_retourne_liste_vide_et_aucun_reload(
    flatpak_installer: NotifiedJobInstaller,
    systemd: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange
    flatpak_installer.sync(enabled=True, dry_run=False)
    systemd.reload_systemd.reset_mock()
    before = _snapshot(tmp_path)

    # Act
    actions = flatpak_installer.sync(enabled=True, dry_run=False)

    # Assert
    assert actions == []
    systemd.reload_systemd.assert_not_called()
    assert _snapshot(tmp_path) == before


def test_flatpak_dry_run_ne_modifie_aucun_fichier(
    flatpak_installer: NotifiedJobInstaller, tmp_path: Path
) -> None:
    # Arrange : racine vide, puis racine installée
    empty = _snapshot(tmp_path)

    # Act / Assert : installation simulée
    actions = flatpak_installer.sync(enabled=True, dry_run=True)
    assert _snapshot(tmp_path) == empty
    assert len(actions) == 6
    assert all(a.startswith("[dry-run]") for a in actions)

    # Retrait simulé sur une racine installée
    flatpak_installer.sync(enabled=True, dry_run=False)
    installed = _snapshot(tmp_path)
    actions = flatpak_installer.sync(enabled=False, dry_run=True)
    assert _snapshot(tmp_path) == installed
    assert all(a.startswith("[dry-run] Retirerait") for a in actions)


@pytest.mark.parametrize(
    ("guard", "flatpak"),
    [
        ("active", "inactive"),
        ("activating", "inactive"),
        ("inactive", "activating"),
        ("inactive", "active"),
        ("inactive", "deactivating"),
    ],
    ids=[
        "compagnon_actif",
        "compagnon_activating",
        "flatpak_activating",
        "flatpak_active",
        "flatpak_deactivating",
    ],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_flatpak_differe_si_run_flatpak_en_cours(
    flatpak_installer: NotifiedJobInstaller,
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
    guard: str,
    flatpak: str,
    *,
    enabled: bool,
) -> None:
    # Arrange : artefacts installés (puis, pour le retrait, un run démarre)
    flatpak_installer.sync(enabled=True, dry_run=False)
    (tmp_path / _F_GUARD).write_text("dérive\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    systemd.reload_systemd.reset_mock()
    states = {
        "flatpak-automatic.service": flatpak,
        "fedora-post-install-flatpak-auto-guard.service": guard,
    }
    systemd.get_status.side_effect = lambda unit: states[unit]

    # Act
    actions = flatpak_installer.sync(enabled=enabled, dry_run=False)

    # Assert : rien n'est modifié, avertissement préfixé par le job, action différée
    assert actions == [_DEFERRED_FLATPAK]
    assert _snapshot(tmp_path) == before
    systemd.reload_systemd.assert_not_called()
    assert any(
        c.args[0].startswith("[flatpak-auto] ⚠") for c in logger.log_info.call_args_list
    )


def test_flatpak_ne_differe_pas_pendant_un_run_dnf(
    flatpak_installer: NotifiedJobInstaller,
    systemd: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange : dnf tourne, Flatpak est inactif
    states = {
        "dnf5-automatic.service": "active",
        "fedora-post-install-dnf5-auto-guard.service": "active",
        "flatpak-automatic.service": "inactive",
        "fedora-post-install-flatpak-auto-guard.service": "inactive",
    }
    systemd.get_status.side_effect = lambda unit: states[unit]

    # Act
    actions = flatpak_installer.sync(enabled=True, dry_run=False)

    # Assert : installation normale
    assert len(actions) == 6
    for relative in _F_FILES:
        assert (tmp_path / relative).is_file()
    systemd.reload_systemd.assert_called_once_with()


def test_flatpak_retrait_enabled_false(
    flatpak_installer: NotifiedJobInstaller,
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange : le runtime a créé le dossier tmpfs
    flatpak_installer.sync(enabled=True, dry_run=False)
    _simulate_hook_run_dir(tmp_path, _F_RUN)
    systemd.reload_systemd.reset_mock()

    # Act
    flatpak_installer.sync(enabled=False, dry_run=False)

    # Assert : artefacts et dossiers d'état retirés, dossiers vides compris
    for relative in (*_F_FILES, _F_STATE, _F_RUN):
        assert not (tmp_path / relative).exists()
    assert not (tmp_path / _OWNER_DIR).exists()
    assert not (tmp_path / "etc/systemd/system/flatpak-automatic.service.d").exists()
    systemd.reload_systemd.assert_called_once_with()
    logged = [c.args[0] for c in logger.log_info.call_args_list]
    assert all(line.startswith("[flatpak-auto] ") for line in logged)


def _install_both(
    systemd: MagicMock, logger: MagicMock, root: Path
) -> tuple[NotifiedJobInstaller, NotifiedJobInstaller]:
    """Installe les deux jobs sous ``root`` et crée leurs dossiers tmpfs."""
    dnf = NotifiedJobInstaller(_dnf_job(), systemd, logger, root_dir=root)
    flatpak = NotifiedJobInstaller(_flatpak_job(), systemd, logger, root_dir=root)
    dnf.sync(enabled=True, dry_run=False)
    flatpak.sync(enabled=True, dry_run=False)
    for run in (_RUN, _F_RUN):
        _simulate_hook_run_dir(root, run)
    return dnf, flatpak


def _photo(root: Path, relatives: tuple[str, ...]) -> dict[str, object]:
    """Photographie de chemins : arborescence si dossier, octets sinon."""
    return {
        relative: _snapshot(root / relative)
        if (root / relative).is_dir()
        else (root / relative).read_bytes()
        for relative in relatives
    }


_SHARED = (_OWNER_DIR, "var/lib/fedora-post-install", "run/fedora-post-install")


def test_retrait_flatpak_laisse_intacts_les_artefacts_et_dossiers_dnf(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange : les deux jobs installés, photographie des chemins dnf
    _, flatpak = _install_both(systemd, logger, tmp_path)
    dnf_paths = (*_FILES, _STATE, _RUN)
    before = _photo(tmp_path, dnf_paths)

    # Act
    flatpak.sync(enabled=False, dry_run=False)

    # Assert : dnf intact, dossiers parents partagés présents
    assert _photo(tmp_path, dnf_paths) == before
    for shared in _SHARED:
        assert (tmp_path / shared).is_dir()
    for relative in (*_F_FILES, _F_STATE, _F_RUN):
        assert not (tmp_path / relative).exists()


def test_retrait_dnf_laisse_intacts_les_artefacts_flatpak(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange
    dnf, _ = _install_both(systemd, logger, tmp_path)
    flatpak_paths = (*_F_FILES, _F_STATE, _F_RUN)
    before = _photo(tmp_path, flatpak_paths)

    # Act
    dnf.sync(enabled=False, dry_run=False)

    # Assert : Flatpak intact, dossiers parents partagés présents
    assert _photo(tmp_path, flatpak_paths) == before
    for shared in _SHARED:
        assert (tmp_path / shared).is_dir()
    for relative in (*_FILES, _STATE, _RUN):
        assert not (tmp_path / relative).exists()


def test_jobs_sans_chemin_commun(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Arrange : chacun des deux jobs installé seul dans sa racine
    chemins: list[set[str]] = []
    for job in (_dnf_job(), _flatpak_job()):
        root = tmp_path / job.name
        root.mkdir()
        NotifiedJobInstaller(job, systemd, logger, root_dir=root).sync(
            enabled=True, dry_run=False
        )
        chemins.append(
            {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
        )

    # Assert : littéraux écrits à la main, aucun fichier en commun
    assert chemins[0] == set(_FILES)
    assert chemins[1] == set(_F_FILES)
    assert chemins[0].isdisjoint(chemins[1])


# ----------------------------------------------------------------------
# Scope user
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _sans_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun `XDG_*` dans l'environnement du processus de test.

    L'installeur ne lit plus `os.environ` (F15) : il lit celui du gestionnaire
    `systemd --user`, injecté par `show_environment`. La fixture garantit qu'un
    `XDG_*` de la machine ne s'y glisse jamais (les tests de F15 en posent
    volontairement pour prouver qu'il est ignoré).
    """
    for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def user_systemd(home: Path) -> MagicMock:
    """UserSystemdExecutor simulé (`UnitPath` par défaut, reload réussi)."""
    return user_manager(home)


def _user_job(*, lock: bool = False, guard_after: tuple[str, ...] = ()) -> NotifiedJob:
    """Job user, sans verrou par défaut (cas d'une sauvegarde par utilisateur)."""
    return NotifiedJob(
        name="backup",
        owner="backup-py",
        watched_unit="backup.service",
        scope="user",
        start_texts=("Début", "Corps"),
        end_texts=_texts(),
        lock=lock,
        guard_after=guard_after,
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Dossier personnel temporaire."""
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def user_installer(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> NotifiedJobInstaller:
    """Installeur user (sans verrou) sous un ``home`` temporaire."""
    return NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)


def test_init_scope_user_en_root_leve_valueerror(
    user_systemd: MagicMock,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : lancé en root, l'installeur écrirait sous /root (F11)
    monkeypatch.setattr(installer_module, "_is_root", lambda: True)

    # Act / Assert
    with pytest.raises(ValueError, match="root"):
        NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)


@pytest.mark.parametrize(("euid", "attendu"), [(0, True), (1000, False)])
def test_is_root_lit_l_euid_du_processus(
    monkeypatch: pytest.MonkeyPatch, euid: int, attendu: bool
) -> None:
    # Arrange : le vrai `_is_root`, que la fixture autouse remplace
    monkeypatch.undo()
    monkeypatch.setattr(os, "geteuid", lambda: euid)

    # Act / Assert
    assert installer_module._is_root() is attendu


def test_init_scope_systeme_en_root_est_permis(
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : le scope système s'installe, lui, en root
    monkeypatch.setattr(installer_module, "_is_root", lambda: True)

    # Act / Assert : aucune exception
    NotifiedJobInstaller(_dnf_job(), systemd, logger, root_dir=tmp_path)


def test_sync_scope_user_chemins_xdg(
    user_installer: NotifiedJobInstaller,
    user_systemd: MagicMock,
    home: Path,
) -> None:
    # Arrange
    script = home / ".local/share/backup-py/backup-notify"

    # Act
    actions = user_installer.sync(enabled=True, dry_run=False)

    # Assert : tout sous le home, runtime privé, unités et autostart XDG
    assert script.read_bytes() == _PACKAGE_HOOK.read_bytes()
    assert stat.S_IMODE(script.stat().st_mode) == 0o700
    descripteur = Path(f"{script}.json")
    assert descripteur.read_text(encoding="utf-8") == _user_job().to_descriptor()
    assert stat.S_IMODE(descripteur.stat().st_mode) == 0o600
    dropin = home / ".config/systemd/user/backup.service.d/backup-py-notify.conf"
    assert dropin.read_text(encoding="utf-8") == (
        "[Service]\n"
        f"Environment=XDG_STATE_HOME={home}/.local/state\n"
        f"ExecStartPre=-/usr/bin/python3 -I {script} start backup\n"
        f"ExecStopPost=-/usr/bin/python3 -I {script} end backup\n"
    )
    desktop = home / ".config/autostart/backup-py-backup-notify.desktop"
    assert desktop.read_text(encoding="utf-8") == (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Notification backup\n"
        f"Exec=/usr/bin/env XDG_STATE_HOME={home}/.local/state "
        f"/usr/bin/python3 -I {script} login backup\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-Phase=Applications\n"
    )
    state = home / ".local/state/backup-py/backup"
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert not (home / ".config/systemd/user/backup-py-backup-guard.service").exists()
    assert len(actions) == 5  # runtime, descripteur, drop-in, desktop, dossier d'état
    user_systemd.reload_systemd.assert_called_once_with()


def test_sync_scope_user_avec_verrou_le_debut_ne_depend_pas_du_compagnon(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : le verrou user dépend de polkit (Q-04), il peut être refusé (F04)
    job = _user_job(lock=True, guard_after=("network.service",))
    installer = NotifiedJobInstaller(job, user_systemd, logger, home=home)
    script = home / ".local/share/backup-py/backup-notify"

    # Act
    installer.sync(enabled=True, dry_run=False)
    unit_dir = home / ".config/systemd/user"
    guard = (unit_dir / "backup-py-backup-guard.service").read_text(encoding="utf-8")
    dropin = (unit_dir / "backup.service.d/backup-py-notify.conf").read_text(
        encoding="utf-8"
    )

    # Assert : le compagnon n'inhibe que (aucun appel au runtime) ; le début est
    # porté par le drop-in, comme sans verrou
    assert guard == (
        "[Unit]\n"
        "Description=Verrou d'extinction et de veille pendant backup\n"
        "BindsTo=backup.service\n"
        "After=network.service\n"
        "\n"
        "[Service]\n"
        "Type=exec\n"
        "ExecStart=/usr/bin/systemd-inhibit "
        "--what=shutdown:sleep:handle-lid-switch --mode=block "
        '--who=backup-py "--why=Mise à jour en cours" /usr/bin/sleep 3600\n'
    )
    assert dropin == (
        "[Unit]\n"
        "Wants=backup-py-backup-guard.service\n"
        "\n"
        "[Service]\n"
        f"Environment=XDG_STATE_HOME={home}/.local/state\n"
        f"ExecStartPre=-/usr/bin/python3 -I {script} start backup\n"
        f"ExecStopPost=-/usr/bin/python3 -I {script} end backup\n"
    )


def test_sync_scope_user_suit_les_dossiers_xdg_de_la_session(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : gestionnaire `systemd --user` avec XDG personnalisés (F03, F15)
    user_systemd.show_environment.return_value = {
        "XDG_DATA_HOME": f"{home}/donnees",
        "XDG_CONFIG_HOME": f"{home}/reglages",
        "XDG_STATE_HOME": f"{home}/etat",
    }
    wire_user_manager(user_systemd, home, [f"{home}/reglages/systemd/user"])
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)
    script = home / "donnees/backup-py/backup-notify"

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : runtime, unités, autostart et état suivent les XDG ; rien aux
    # emplacements par défaut ; l'unité fixe XDG_STATE_HOME à la valeur résolue
    assert script.is_file()
    assert Path(f"{script}.json").is_file()
    dropin = home / "reglages/systemd/user/backup.service.d/backup-py-notify.conf"
    assert dropin.read_text(encoding="utf-8") == (
        "[Service]\n"
        f"Environment=XDG_STATE_HOME={home}/etat\n"
        f"ExecStartPre=-/usr/bin/python3 -I {script} start backup\n"
        f"ExecStopPost=-/usr/bin/python3 -I {script} end backup\n"
    )
    assert (home / "reglages/autostart/backup-py-backup-notify.desktop").is_file()
    assert (home / "etat/backup-py/backup").is_dir()
    assert not (home / ".local").exists()
    assert not (home / ".config").exists()

    # Retrait : mêmes chemins, dossiers propres
    installer.sync(enabled=False, dry_run=False)
    assert [p for p in home.rglob("*") if p.is_file()] == []
    assert not (home / "donnees/backup-py").exists()
    assert not (home / "etat/backup-py").exists()


def test_sync_scope_user_xdg_vide_ou_relatif_est_ignore(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : la spec XDG ignore une valeur vide ou relative
    user_systemd.show_environment.return_value = {
        "XDG_DATA_HOME": "",
        "XDG_CONFIG_HOME": "relatif",
        "XDG_STATE_HOME": ".",
    }
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : repli sur les emplacements par défaut
    assert (home / ".local/share/backup-py/backup-notify").is_file()
    assert (home / ".config/systemd/user/backup.service.d").is_dir()
    assert (home / ".local/state/backup-py/backup").is_dir()


@pytest.mark.parametrize(
    "valeur",
    ["{home}/a b", "{home}/a%h", "{home}/../dehors", "/ailleurs/etat"],
    ids=["espace", "pourcent", "remontee", "hors-du-home"],
)
def test_init_refuse_un_xdg_dangereux_ou_hors_du_home(
    user_systemd: MagicMock, logger: MagicMock, home: Path, valeur: str
) -> None:
    # Arrange : XDG injecté dans une unité, et base des refus de lien symbolique
    user_systemd.show_environment.return_value = {
        "XDG_STATE_HOME": valeur.format(home=home)
    }

    # Act / Assert
    with pytest.raises(ValueError, match="XDG_STATE_HOME"):
        NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)


@pytest.mark.parametrize(
    "valeur",
    ["$'{home}/a b'", '"{home}/etat"', "'{home}/etat'"],
    ids=["dollar-quote", "guillemets", "apostrophes"],
)
def test_init_refuse_un_xdg_cite_par_systemd(
    user_systemd: MagicMock, logger: MagicMock, home: Path, valeur: str
) -> None:
    # Arrange : `show-environment` cite une valeur à caractères spéciaux (F23) ;
    # l'ignorer en silence écrirait ailleurs que là où le gestionnaire lit
    user_systemd.show_environment.return_value = {
        "XDG_STATE_HOME": valeur.format(home=home)
    }

    # Act / Assert
    with pytest.raises(ValueError, match=r"XDG_STATE_HOME cité"):
        NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)


def test_init_scope_user_lit_l_environnement_du_gestionnaire_pas_celui_du_processus(
    user_systemd: MagicMock,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : trois environnements distincts (F15). L'installeur (os.environ)
    # et la session pointent ailleurs que le gestionnaire `systemd --user`, seul
    # à fixer ce que verront les unités.
    monkeypatch.setenv("XDG_DATA_HOME", f"{home}/data-installeur")
    monkeypatch.setenv("XDG_CONFIG_HOME", f"{home}/config-installeur")
    monkeypatch.setenv("XDG_STATE_HOME", f"{home}/etat-installeur")
    user_systemd.show_environment.return_value = {
        "XDG_DATA_HOME": f"{home}/data-gestionnaire",
        "XDG_CONFIG_HOME": f"{home}/config-gestionnaire",
        "XDG_STATE_HOME": f"{home}/etat-gestionnaire",
    }
    wire_user_manager(user_systemd, home, [f"{home}/config-gestionnaire/systemd/user"])
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)
    script = home / "data-gestionnaire/backup-py/backup-notify"

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : tout suit le gestionnaire ; rien chez l'installeur
    assert script.is_file()
    dropin = home / "config-gestionnaire/systemd/user/backup.service.d"
    assert f"Environment=XDG_STATE_HOME={home}/etat-gestionnaire\n" in (
        dropin / "backup-py-notify.conf"
    ).read_text(encoding="utf-8")
    desktop = home / "config-gestionnaire/autostart/backup-py-backup-notify.desktop"
    assert (
        f"Exec=/usr/bin/env XDG_STATE_HOME={home}/etat-gestionnaire "
        f"/usr/bin/python3 -I {script} login backup\n"
    ) in desktop.read_text(encoding="utf-8")
    assert (home / "etat-gestionnaire/backup-py/backup").is_dir()
    assert not any(p.name.endswith("-installeur") for p in home.iterdir())
    user_systemd.show_environment.assert_called_once_with()


def test_init_scope_user_sans_xdg_du_gestionnaire_ignore_os_environ(
    user_systemd: MagicMock,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : le gestionnaire ne définit aucun XDG, l'installeur en a (F15)
    monkeypatch.setenv("XDG_STATE_HOME", f"{home}/etat-installeur")
    monkeypatch.setenv("XDG_CONFIG_HOME", f"{home}/config-installeur")
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : repli relatif au home
    assert (home / ".local/state/backup-py/backup").is_dir()
    assert (home / ".config/systemd/user/backup.service.d").is_dir()
    assert not (home / "etat-installeur").exists()
    assert not (home / "config-installeur").exists()


def test_init_scope_user_gestionnaire_illisible_repli_sous_le_home(
    user_systemd: MagicMock,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : `show-environment` échoue (bus injoignable) ; os.environ n'est
    # PAS une source de secours (F15)
    monkeypatch.setenv("XDG_STATE_HOME", f"{home}/etat-installeur")
    user_systemd.show_environment.side_effect = RuntimeError("bus injoignable")

    # Act
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)
    installer.sync(enabled=True, dry_run=False)

    # Assert : repli sous le home, avec un avertissement qui nomme la cause
    assert (home / ".local/state/backup-py/backup").is_dir()
    assert not (home / "etat-installeur").exists()
    logger.log_warning.assert_called_once()
    message = logger.log_warning.call_args.args[0]
    assert "bus injoignable" in message
    assert "backup" in message


def test_init_scope_systeme_n_interroge_pas_show_environment(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Act
    installer = NotifiedJobInstaller(_dnf_job(), systemd, logger, root_dir=tmp_path)
    installer.sync(enabled=True, dry_run=False)

    # Assert : le scope système ne lit aucun environnement ; son autostart reste
    # sans `env` (littéral du scope système)
    systemd.show_environment.assert_not_called()
    desktop = next((tmp_path / "etc/xdg/autostart").glob("*.desktop"))
    assert "Exec=/usr/bin/python3 -I /usr/local/libexec/" in desktop.read_text(
        encoding="utf-8"
    )


def test_sync_scope_user_home_par_defaut(
    user_systemd: MagicMock,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : sans `home`, le dossier personnel de l'utilisateur courant
    monkeypatch.setattr(Path, "home", lambda: home)
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (home / ".local/share/backup-py/backup-notify").is_file()


def test_sync_scope_user_retrait_et_dry_run(
    user_installer: NotifiedJobInstaller,
    user_systemd: MagicMock,
    home: Path,
) -> None:
    # Arrange : installé, avec l'état écrit par le runtime
    user_installer.sync(enabled=True, dry_run=False)
    state = home / ".local/state/backup-py/backup"
    (state / "state.json").write_text("{}", encoding="utf-8")
    (state / "seen").write_text("1\n", encoding="utf-8")
    installed = _snapshot(home)
    user_systemd.reload_systemd.reset_mock()

    # Act / Assert : retrait simulé
    simulated = user_installer.sync(enabled=False, dry_run=True)
    assert _snapshot(home) == installed
    assert all(a.startswith("[dry-run] Retirerait") for a in simulated)
    user_systemd.reload_systemd.assert_not_called()

    # Retrait réel : fichiers, dossiers du job et parents propres, home intact
    user_installer.sync(enabled=False, dry_run=False)
    assert [p for p in home.rglob("*") if p.is_file()] == []
    assert not (home / ".local/share/backup-py").exists()
    assert not (home / ".local/state/backup-py").exists()
    assert not (home / ".config/systemd/user/backup.service.d").exists()
    user_systemd.reload_systemd.assert_called_once_with()


def test_sync_scope_user_refuse_lien_symbolique(
    user_installer: NotifiedJobInstaller, home: Path, tmp_path: Path
) -> None:
    # Arrange
    outside = tmp_path / "dehors"
    outside.mkdir()
    (home / ".config").symlink_to(outside)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Lien symbolique refusé"):
        user_installer.sync(enabled=True, dry_run=True)
    assert list(outside.iterdir()) == []


def test_sync_scope_user_suit_un_dossier_en_lien_sous_le_home(
    user_installer: NotifiedJobInstaller, home: Path
) -> None:
    # Arrange : dotfiles gérés par stow, `~/.config/systemd/user` est un lien
    # vers un dossier du home (F18) ; pas de frontière de privilège en user
    stowed = home / "dotfiles/systemd-user"
    stowed.mkdir(parents=True)
    unit_dir = home / ".config/systemd/user"
    unit_dir.parent.mkdir(parents=True)
    unit_dir.symlink_to(stowed)

    # Act
    user_installer.sync(enabled=True, dry_run=False)

    # Assert : écrit dans la cible du lien, le lien est conservé
    assert unit_dir.is_symlink()
    assert (stowed / "backup.service.d/backup-py-notify.conf").is_file()
    assert (unit_dir / "backup.service.d/backup-py-notify.conf").is_file()


def test_sync_scope_user_remplace_un_lien_final_sans_le_suivre(
    user_installer: NotifiedJobInstaller, home: Path
) -> None:
    # Arrange : le descripteur est un lien (stow) vers un fichier du home
    stowed = home / "dotfiles/descripteur.json"
    stowed.parent.mkdir()
    stowed.write_text("intact", encoding="utf-8")
    descriptor = home / ".local/share/backup-py/backup-notify.json"
    descriptor.parent.mkdir(parents=True)
    descriptor.symlink_to(stowed)

    # Act
    user_installer.sync(enabled=True, dry_run=False)

    # Assert : le lien est remplacé par un fichier, la cible n'est pas écrite
    assert not descriptor.is_symlink()
    assert descriptor.is_file()
    assert stowed.read_text(encoding="utf-8") == "intact"


@pytest.mark.parametrize(
    "link_relative",
    [".config/systemd/user", ".local/share/backup-py/backup-notify.json"],
    ids=["dossier", "fichier-final"],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_sync_scope_user_refuse_un_lien_dont_la_cible_sort_du_home(
    user_installer: NotifiedJobInstaller,
    home: Path,
    tmp_path: Path,
    link_relative: str,
    *,
    enabled: bool,
) -> None:
    # Arrange : le lien pointe hors du home (F18)
    outside = tmp_path / "dehors"
    outside.mkdir()
    link = home / link_relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    # Act / Assert : refus avant toute action, rien d'écrit à travers le lien
    with pytest.raises(RuntimeError, match="Lien symbolique refusé"):
        user_installer.sync(enabled=enabled, dry_run=False)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "link_relative",
    [".local/share/backup-py", ".local/state/backup-py/backup"],
    ids=["dossier-de-donnees", "dossier-d-etat"],
)
def test_sync_scope_user_retrait_laisse_un_dossier_elagable_en_lien(
    user_installer: NotifiedJobInstaller,
    user_systemd: MagicMock,
    home: Path,
    link_relative: str,
) -> None:
    # Arrange : dossier du job géré par stow (lien vers un dossier du home), F21
    stowed = home / "dotfiles" / "cible"
    stowed.mkdir(parents=True)
    link = home / link_relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(stowed)
    user_installer.sync(enabled=True, dry_run=False)
    user_systemd.reload_systemd.reset_mock()

    # Act : le retrait ne lève pas (`rmdir` d'un lien donnerait NotADirectoryError)
    actions = user_installer.sync(enabled=False, dry_run=False)

    # Assert : le lien n'est jamais élagué ni cité, ses fichiers sont retirés, et
    # le gestionnaire est rechargé (le drop-in a bien été retiré)
    assert link.is_symlink()
    assert f"Retiré {link}" not in actions
    assert [p for p in stowed.rglob("*") if p.is_file()] == []
    user_systemd.reload_systemd.assert_called_once_with()


def test_sync_scope_user_retrait_recharge_meme_si_une_etape_suivante_echoue(
    user_installer: NotifiedJobInstaller,
    user_systemd: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : le drop-in est retiré, puis le retrait de l'autostart échoue (F21)
    user_installer.sync(enabled=True, dry_run=False)
    user_systemd.reload_systemd.reset_mock()
    desktop = home / ".config/autostart/backup-py-backup-notify.desktop"
    real_unlink = Path.unlink

    def unlink_refuse(self: Path, *, missing_ok: bool = False) -> None:
        if self == desktop:
            raise PermissionError
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink_refuse)

    # Act / Assert : l'erreur remonte, mais l'unité retirée est déjà rechargée
    with pytest.raises(RuntimeError, match="Retrait refusé"):
        user_installer.sync(enabled=False, dry_run=False)
    assert not (
        home / ".config/systemd/user/backup.service.d/backup-py-notify.conf"
    ).exists()
    user_systemd.reload_systemd.assert_called_once_with()


def _refuse_unlink_du_desktop(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Fait échouer le retrait de l'autostart, après celui du drop-in."""
    desktop = home / ".config/autostart/backup-py-backup-notify.desktop"
    real_unlink = Path.unlink

    def unlink_refuse(self: Path, *, missing_ok: bool = False) -> None:
        if self == desktop:
            raise PermissionError
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink_refuse)


def test_sync_retrait_reload_en_echec_ne_masque_pas_l_erreur_d_origine(
    user_installer: NotifiedJobInstaller,
    user_systemd: MagicMock,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : le drop-in est retiré, l'autostart refuse, et le reload échoue (F29)
    user_installer.sync(enabled=True, dry_run=False)
    user_systemd.reload_systemd.return_value = False
    _refuse_unlink_du_desktop(monkeypatch, home)

    # Act / Assert : l'erreur d'origine remonte, pas celle du reload
    with pytest.raises(RuntimeError, match="Retrait refusé"):
        user_installer.sync(enabled=False, dry_run=False)

    # Assert : l'échec du reload est journalisé, sans être perdu
    assert "daemon-reload" in logger.log_error.call_args.args[0]


def test_sync_retrait_reload_en_echec_seul_leve_runtimeerror(
    user_installer: NotifiedJobInstaller, user_systemd: MagicMock
) -> None:
    # Arrange : aucune erreur en cours, seul le reload échoue
    user_installer.sync(enabled=True, dry_run=False)
    user_systemd.reload_systemd.return_value = False

    # Act / Assert : l'échec du reload n'est pas avalé
    with pytest.raises(RuntimeError, match="daemon-reload"):
        user_installer.sync(enabled=False, dry_run=False)


def test_sync_retrait_journalise_les_actions_au_fil_de_l_eau(
    user_installer: NotifiedJobInstaller,
    logger: MagicMock,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : une étape échoue après le retrait du drop-in
    user_installer.sync(enabled=True, dry_run=False)
    logger.log_info.reset_mock()
    _refuse_unlink_du_desktop(monkeypatch, home)

    # Act
    with pytest.raises(RuntimeError, match="Retrait refusé"):
        user_installer.sync(enabled=False, dry_run=False)

    # Assert : ce qui a été retiré avant l'échec est déjà dans le journal
    dropin = home / ".config/systemd/user/backup.service.d/backup-py-notify.conf"
    logged = [c.args[0] for c in logger.log_info.call_args_list]
    assert f"[backup] Retiré {dropin}" in logged


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("dry_run", [True, False])
def test_sync_scope_user_refuse_une_boucle_de_liens(
    user_installer: NotifiedJobInstaller,
    home: Path,
    *,
    enabled: bool,
    dry_run: bool,
) -> None:
    # Arrange : deux liens qui se pointent l'un l'autre sous le home (F24)
    (home / ".config").mkdir()
    (home / ".config/systemd").symlink_to(home / ".config/boucle")
    (home / ".config/boucle").symlink_to(home / ".config/systemd")

    # Act / Assert : même message en dry-run et en réel, quelle que soit la
    # version de Python (`resolve` lève `RuntimeError` en 3.11, `OSError` ensuite)
    with pytest.raises(RuntimeError, match="Lien symbolique irrésoluble") as info:
        user_installer.sync(enabled=enabled, dry_run=dry_run)
    assert str(home / ".config/systemd") in str(info.value)


def test_sync_scope_user_installation_refuse_un_lien_orphelin(
    user_installer: NotifiedJobInstaller, home: Path
) -> None:
    # Arrange : le dossier d'état est un lien dont la cible a disparu
    state = home / ".local/state/backup-py"
    state.parent.mkdir(parents=True)
    state.symlink_to(home / "dotfiles-supprime")

    # Act / Assert : on n'installe pas à travers un lien cassé (F28)
    with pytest.raises(RuntimeError, match="Lien symbolique irrésoluble"):
        user_installer.sync(enabled=True, dry_run=False)


@pytest.mark.parametrize("dry_run", [True, False])
def test_sync_scope_user_retrait_tolere_un_lien_orphelin(
    user_installer: NotifiedJobInstaller, home: Path, *, dry_run: bool
) -> None:
    # Arrange : installé, puis le dossier d'état devient un lien orphelin (stow
    # défait) ; rien n'est lisible dessous, rien n'y est à retirer
    user_installer.sync(enabled=True, dry_run=False)
    state = home / ".local/state/backup-py"
    state.rename(home / "ailleurs")
    state.symlink_to(home / "dotfiles-supprime")
    dropin = home / ".config/systemd/user/backup.service.d/backup-py-notify.conf"

    # Act : le retrait du reste ne doit pas être bloqué (régression de F24)
    actions = user_installer.sync(enabled=False, dry_run=dry_run)

    # Assert : drop-in retiré (ou annoncé), le lien orphelin est laissé tel quel
    assert any(str(dropin) in a for a in actions)
    assert dropin.exists() is dry_run
    assert state.is_symlink()


def test_sync_scope_user_retrait_refuse_toujours_une_boucle(
    user_installer: NotifiedJobInstaller, home: Path
) -> None:
    # Arrange : une boucle n'est pas une cible absente
    user_installer.sync(enabled=True, dry_run=False)
    (home / ".local/state/backup-py").rename(home / "ailleurs")
    (home / ".local/state/backup-py").symlink_to(home / ".local/state/boucle")
    (home / ".local/state/boucle").symlink_to(home / ".local/state/backup-py")

    # Act / Assert
    with pytest.raises(RuntimeError, match="Lien symbolique irrésoluble"):
        user_installer.sync(enabled=False, dry_run=False)


@pytest.mark.parametrize(
    "dangereux",
    [
        "/home/a b",
        "/home/a%h",
        "/home/a$HOME",
        "/home/a\nExecStart=/bin/evil",
        '/home/a"b',
        "/home/a\\b",
        "/home/a;b",
        "home/relatif",
        "/home/../etc",
    ],
    ids=[
        "espace",
        "pourcent",
        "dollar",
        "saut-de-ligne",
        "guillemet",
        "antislash",
        "point-virgule",
        "relatif",
        "remontee",
    ],
)
def test_init_refuse_un_home_aux_caracteres_dangereux(
    user_systemd: MagicMock, logger: MagicMock, dangereux: str
) -> None:
    # Act / Assert : jamais injecté dans une unité systemd
    with pytest.raises(ValueError, match="home"):
        NotifiedJobInstaller(_user_job(), user_systemd, logger, home=Path(dangereux))


def test_init_scope_systeme_ignore_le_home(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Act / Assert : `home` n'entre dans aucune unité système, il n'est pas contrôlé
    NotifiedJobInstaller(
        _dnf_job(), systemd, logger, root_dir=tmp_path, home=Path("/home/a b")
    )


# ----------------------------------------------------------------------
# Exports
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "nom",
    [
        "NotifiedJob",
        "NotifiedJobInstaller",
        "Outcome",
        "NoProbe",
        "FingerprintProbe",
        "Dnf5Probe",
    ],
)
def test_symboles_publics_exportes_par_jobnotify_et_linuxtools(nom: str) -> None:
    # Arrange
    import linuxtools
    import linuxtools.jobnotify as brique

    # Act / Assert : même objet, déclaré dans les deux `__all__`
    assert getattr(linuxtools, nom) is getattr(brique, nom)
    assert nom in linuxtools.__all__
    assert nom in brique.__all__


def test_sync_refuse_un_descripteur_que_le_runtime_refuserait(
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : un descripteur que le schéma du runtime refuse (corps à 3 éléments)
    job = _dnf_job()
    valide = json.loads(job.to_descriptor())
    valide["start_texts"] = ["a", "b", "c"]
    monkeypatch.setattr(
        NotifiedJob, "to_descriptor", lambda _self: json.dumps(valide) + "\n"
    )
    installer = NotifiedJobInstaller(job, systemd, logger, root_dir=tmp_path)

    # Act / Assert : refus (même en dry-run) AVANT toute écriture ou appel systemd
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="descripteur"):
            installer.sync(enabled=True, dry_run=dry_run)
    assert list(tmp_path.rglob("*")) == []
    assert systemd.method_calls == []


def test_sync_retrait_n_exige_pas_un_descripteur_valide(
    systemd: MagicMock,
    logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange : le descripteur ne sert pas au retrait
    job = _dnf_job()
    monkeypatch.setattr(NotifiedJob, "to_descriptor", lambda _self: "{}\n")
    installer = NotifiedJobInstaller(job, systemd, logger, root_dir=tmp_path)

    # Act / Assert
    assert installer.sync(enabled=False, dry_run=False) == []


# ---------------------------------------------------------------------------
# F22 : dossier des unités tiré de `UnitPath`, post-condition après reload
# ---------------------------------------------------------------------------


def test_sync_scope_user_ecrit_les_unites_dans_le_dossier_de_unitpath(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : `UnitPath` du gestionnaire (F22) : `.control` et un dossier hors du
    # home précèdent le premier dossier persistant sous le home
    wire_user_manager(
        user_systemd,
        home,
        [
            f"{home}/.config/systemd/user.control",
            "/run/user/1000/systemd/generator.early",
            "/etc/systemd/user",
            f"{home}/unites/systemd/user",
            f"{home}/.config/systemd/user",
        ],
    )
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : le drop-in est dans le premier dossier persistant ; l'autostart,
    # lu par la session, reste sous XDG_CONFIG_HOME (repli ~/.config)
    assert (
        home / "unites/systemd/user/backup.service.d/backup-py-notify.conf"
    ).is_file()
    assert (home / ".config/autostart/backup-py-backup-notify.desktop").is_file()
    assert not (home / ".config/systemd").exists()


@pytest.mark.parametrize(
    "unit_path",
    [
        [],
        ["/etc/systemd/user", "/usr/lib/systemd/user"],
        ["{home}/.config/systemd/user.control", "{home}/g/generator.late"],
        ["relatif/user", "{home}/../dehors", "{home}/a%h/user"],
    ],
    ids=["vide", "hors-du-home", "control-et-generator", "relatif-remontee-pourcent"],
)
def test_sync_scope_user_unitpath_ignore_les_entrees_inutilisables(
    user_systemd: MagicMock, logger: MagicMock, home: Path, unit_path: list[str]
) -> None:
    # Arrange : aucune entrée persistante, sûre et sous le home
    entries = [e.format(home=home) for e in unit_path]
    # le repli est `~/.config/systemd/user` : il figure en dernier dans UnitPath
    # (entrée sûre, mais choisie par le repli seul si les précédentes sont refusées)
    wire_user_manager(user_systemd, home, [*entries, f"{home}/.config/systemd/user"])
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (home / ".config/systemd/user/backup.service.d").is_dir()


def test_init_scope_user_unitpath_illisible_repli_sous_le_home(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : `show -p UnitPath` échoue (bus injoignable)
    user_systemd.show_property.side_effect = RuntimeError("bus injoignable")

    # Act
    NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Assert : repli et avertissement qui nomme la cause
    message = logger.log_warning.call_args.args[0]
    assert "bus injoignable" in message
    assert "UnitPath" in message


def test_sync_scope_user_unite_hors_du_chemin_de_recherche_leve_runtimeerror(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : le gestionnaire ne cherche pas dans `~/.config/systemd/user`
    # (aucune entrée sous le home : repli) -> le drop-in n'est jamais chargé
    wire_user_manager(user_systemd, home, ["/etc/systemd/user"])
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act / Assert : pas de succès silencieux, le message nomme le drop-in
    with pytest.raises(RuntimeError, match=r"systemd/user.*hors de UnitPath"):
        installer.sync(enabled=True, dry_run=False)


def test_sync_scope_user_dropin_non_charge_leve_runtimeerror(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : dossier dans `UnitPath`, mais le gestionnaire ne rend pas le drop-in
    real = user_systemd.show_property.side_effect

    def show_property(name: str, unit: str | None = None) -> str:
        return "" if name == "DropInPaths" else str(real(name, unit))

    user_systemd.show_property.side_effect = show_property
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act / Assert
    with pytest.raises(RuntimeError, match=r"drop-in.*backup-py-notify\.conf"):
        installer.sync(enabled=True, dry_run=False)


def test_sync_scope_user_compagnon_non_charge_leve_runtimeerror(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : drop-in chargé, mais le gestionnaire ne trouve pas le compagnon
    real = user_systemd.show_property.side_effect

    def show_property(name: str, unit: str | None = None) -> str:
        return "" if name == "FragmentPath" else str(real(name, unit))

    user_systemd.show_property.side_effect = show_property
    installer = NotifiedJobInstaller(
        _user_job(lock=True), user_systemd, logger, home=home
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match=r"compagnon.*guard"):
        installer.sync(enabled=True, dry_run=False)


def test_sync_scope_user_sans_verrou_ne_verifie_pas_le_compagnon(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Act
    NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home).sync(
        enabled=True, dry_run=False
    )

    # Assert : drop-in vérifié (watched), aucun FragmentPath demandé
    asked = [c.args[0] for c in user_systemd.show_property.call_args_list]
    assert "DropInPaths" in asked
    assert "FragmentPath" not in asked


def test_sync_scope_user_dry_run_ne_verifie_rien(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)
    installer.sync(enabled=True, dry_run=False)
    user_systemd.show_property.reset_mock()
    user_systemd.show_property.side_effect = RuntimeError("ne doit pas être lu")

    # Act : dry-run d'une installation puis d'un retrait
    installer.sync(enabled=True, dry_run=True)
    installer.sync(enabled=False, dry_run=True)

    # Assert
    user_systemd.show_property.assert_not_called()


def test_sync_scope_user_conforme_reverifie_la_postcondition(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : premier sync réel, puis le gestionnaire perd le drop-in
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)
    installer.sync(enabled=True, dry_run=False)
    real = user_systemd.show_property.side_effect

    def show_property(name: str, unit: str | None = None) -> str:
        return "" if name == "DropInPaths" else str(real(name, unit))

    user_systemd.show_property.side_effect = show_property
    user_systemd.reload_systemd.reset_mock()

    # Act / Assert : déjà conforme (aucun reload), mais la vérification a lieu (F27)
    with pytest.raises(RuntimeError, match=r"drop-in.*backup-py-notify\.conf"):
        installer.sync(enabled=True, dry_run=False)
    user_systemd.reload_systemd.assert_not_called()


def test_sync_scope_user_retrait_ne_verifie_rien(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)
    installer.sync(enabled=True, dry_run=False)
    user_systemd.show_property.reset_mock()

    # Act
    installer.sync(enabled=False, dry_run=False)

    # Assert : rien à charger après un retrait
    user_systemd.show_property.assert_not_called()


def test_sync_scope_user_unitpath_compare_les_chemins_resolus(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : `UnitPath` illisible à l'init (repli), puis rendu via un lien
    unit_dir = home / ".config/systemd/user"
    unit_dir.mkdir(parents=True)
    link = home / "lien-unites"
    link.symlink_to(unit_dir)
    real = user_systemd.show_property.side_effect
    calls = {"unit_path": 0}

    def show_property(name: str, unit: str | None = None) -> str:
        if name == "UnitPath":
            calls["unit_path"] += 1
            if calls["unit_path"] == 1:
                raise RuntimeError("bus injoignable")
            return str(link)
        return str(real(name, unit))

    user_systemd.show_property.side_effect = show_property
    installer = NotifiedJobInstaller(_user_job(), user_systemd, logger, home=home)

    # Act : ne lève pas, le lien et le dossier sont le même dossier résolu
    installer.sync(enabled=True, dry_run=False)

    # Assert
    assert (unit_dir / "backup.service.d/backup-py-notify.conf").is_file()


@pytest.mark.parametrize(
    ("vendor_units", "masked", "etat"),
    [
        ((), (), "not-found"),
        (("backup.service",), ("backup.service",), "masked"),
    ],
)
def test_sync_scope_user_unite_surveillee_non_chargee_avertit_sans_erreur(
    home: Path,
    logger: MagicMock,
    vendor_units: Collection[str],
    masked: Collection[str],
    etat: str,
) -> None:
    # Arrange : systemd réel rend LoadState=not-found/masked et DropInPaths vide
    manager = user_manager(home, vendor_units=vendor_units, masked=masked)
    installer = NotifiedJobInstaller(_user_job(), manager, logger, home=home)

    # Act : pas d'erreur (faux positif F27)
    actions = installer.sync(enabled=True, dry_run=False)

    # Assert : écrit, avertissement qui nomme l'unité et l'état, drop-in non lu
    assert actions
    warning = logger.log_warning.call_args.args[0]
    assert "backup.service" in warning
    assert etat in warning
    asked = [c.args[0] for c in manager.show_property.call_args_list]
    assert "DropInPaths" not in asked


def test_sync_scope_user_compagnon_non_charge_par_loadstate_avertit(
    user_systemd: MagicMock, logger: MagicMock, home: Path
) -> None:
    # Arrange : le compagnon n'est pas `loaded` (masqué après écriture)
    real = user_systemd.show_property.side_effect

    def show_property(name: str, unit: str | None = None) -> str:
        if name == "LoadState" and unit == "backup-py-backup-guard.service":
            return "masked"
        return str(real(name, unit))

    user_systemd.show_property.side_effect = show_property
    installer = NotifiedJobInstaller(
        _user_job(lock=True), user_systemd, logger, home=home
    )

    # Act
    installer.sync(enabled=True, dry_run=False)

    # Assert : avertissement, FragmentPath non lu
    assert "masked" in logger.log_warning.call_args.args[0]
    asked = [c.args[0] for c in user_systemd.show_property.call_args_list]
    assert "FragmentPath" not in asked


def test_sync_scope_systeme_ne_lit_aucune_propriete(
    systemd: MagicMock, logger: MagicMock, tmp_path: Path
) -> None:
    # Act
    NotifiedJobInstaller(_dnf_job(), systemd, logger, root_dir=tmp_path).sync(
        enabled=True, dry_run=False
    )

    # Assert : `UnitPath` ne concerne que le scope user
    systemd.show_property.assert_not_called()
