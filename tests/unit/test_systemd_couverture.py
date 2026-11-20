"""Tests de comportement complémentaires pour le module systemd.

Aucune action systemd réelle : exécuteurs simulés, unités écrites sous tmp_path.
"""

import os
import stat
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from linuxtools.logging.base import Logger
from linuxtools.systemd import (
    AutomountConfig,
    LinuxMountUnitManager,
    MountConfig,
    ServiceConfig,
    TimerConfig,
)
from linuxtools.systemd.base import UnitManager
from linuxtools.systemd.config_loaders import BashScriptConfigLoader
from linuxtools.systemd.executor import SystemdExecutor
from linuxtools.systemd.timer import LinuxTimerUnitManager
from linuxtools.systemd.unit_porter import SystemdUnitExporter, SystemdUnitRestorer
from linuxtools.systemd.user_service import LinuxUserServiceUnitManager
from linuxtools.systemd.user_timer import LinuxUserTimerUnitManager
from tests.unit.couverture_helpers import cmd_result, descripteurs_ouverts


@pytest.fixture
def logger() -> MagicMock:
    """Logger simulé."""
    return MagicMock(spec=Logger)


@pytest.fixture
def xdg_casse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """XDG_CONFIG_HOME pointe vers un fichier : créer le dossier des unités échoue."""
    fichier = tmp_path / "pas-un-dossier"
    fichier.write_text("x", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fichier))
    return fichier


# --- base_config ---


def test_montage_sans_source_est_refuse() -> None:
    """Une unité mount sans 'what' est refusée."""
    with pytest.raises(ValueError, match="'what' et 'where' sont requis"):
        MountConfig(description="d", what="", where="/mnt/x", type="nfs")


def test_automount_sans_chemin_est_refuse() -> None:
    """Une unité automount sans 'where' est refusée."""
    with pytest.raises(ValueError, match="'where' est requis"):
        AutomountConfig(description="d", where="")


# --- script_loader ---


def test_chargement_sans_notification_exige_une_commande(tmp_path: Path) -> None:
    """Sans exec_command ni exec_start, le chargement lève KeyError."""
    fichier = tmp_path / "app.toml"
    fichier.write_text('[script]\nautre = "x"\n', encoding="utf-8")

    with pytest.raises(KeyError, match="Ni 'exec_command' ni 'exec_start'"):
        BashScriptConfigLoader(str(fichier)).load_without_notification("script")


# --- executor ---


def _executeur_systemd(logger: MagicMock) -> tuple[SystemdExecutor, MagicMock]:
    """Exécuteur systemd branché sur un exécuteur de commandes simulé."""
    commandes = MagicMock()
    return SystemdExecutor(logger, commandes), commandes


def test_desactivation_sans_arret_immediat(logger: MagicMock) -> None:
    """Avec now=False, la commande n'a pas --now."""
    executeur, commandes = _executeur_systemd(logger)
    commandes.run.return_value = cmd_result()

    assert executeur.disable_unit("backup.service", now=False) is True

    commandes.run.assert_called_once_with(["systemctl", "disable", "backup.service"])


def test_liste_des_fichiers_d_unite_en_repli_texte(logger: MagicMock) -> None:
    """Sans JSON, le repli texte ignore lignes vides et lignes incomplètes."""
    executeur, commandes = _executeur_systemd(logger)
    commandes.run.side_effect = [
        cmd_result(success=False, stderr="unknown option '--output=json'"),
        cmd_result(stdout="a.service enabled enabled\n\nseul\nb.timer disabled\n"),
    ]

    fichiers = executeur.list_unit_files()

    assert fichiers == [
        {"unit_file": "a.service", "state": "enabled", "preset": "enabled"},
        {"unit_file": "b.timer", "state": "disabled", "preset": ""},
    ]


# --- mount ---


@pytest.fixture
def unites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Dossier d'unités système factice pour LinuxMountUnitManager."""
    dossier = tmp_path / "units"
    dossier.mkdir()
    monkeypatch.setattr(LinuxMountUnitManager, "SYSTEMD_UNIT_PATH", str(dossier))
    return dossier


def test_montage_sur_un_point_existant_ne_le_recree_pas(
    tmp_path: Path, unites: Path, logger: MagicMock
) -> None:
    """Un point de montage déjà présent n'est pas annoncé comme créé."""
    point = tmp_path / "mnt"
    point.mkdir()
    executeur = MagicMock(spec=SystemdExecutor)
    executeur.reload_systemd.return_value = True
    gestionnaire = LinuxMountUnitManager(logger, executeur)

    ok = gestionnaire.install_mount_unit(
        MountConfig(description="d", what="srv:/x", where=str(point), type="nfs")
    )

    assert ok is True
    messages = [c.args[0] for c in logger.log_info.call_args_list]
    assert not any(m.startswith("Point de montage créé") for m in messages)
    assert any(f.suffix == ".mount" for f in unites.iterdir())


def test_installation_automount_echoue_si_l_ecriture_de_l_automount_echoue(
    tmp_path: Path, unites: Path, logger: MagicMock
) -> None:
    """Si le .automount ne peut pas être écrit (nom occupé par un dossier), échec."""
    point = tmp_path / "mnt"
    config = MountConfig(description="d", what="srv:/x", where=str(point), type="nfs")
    (
        unites
        / f"{AutomountConfig(description='d', where=str(point)).unit_name}.automount"
    ).mkdir()
    executeur = MagicMock(spec=SystemdExecutor)
    gestionnaire = LinuxMountUnitManager(logger, executeur)

    ok = gestionnaire.install_mount_unit(config, with_automount=True)

    assert ok is False
    executeur.reload_systemd.assert_not_called()


# --- unit_porter ---


def test_parse_ini_ignore_les_lignes_hors_section_et_sans_egal(
    tmp_path: Path,
) -> None:
    """Les clés avant toute section et les lignes sans '=' sont ignorées."""
    fichier = tmp_path / "x.service"
    fichier.write_text("orpheline=1\n[Unit]\nsans egal\nA=1\n", encoding="utf-8")

    assert SystemdUnitExporter.parse_ini(fichier) == {"Unit": {"A": ["1"]}}


def _toml_avec_prerequis(dossier: Path, requires_exec: str) -> Path:
    """Écrit un TOML d'unité exigeant ``requires_exec``."""
    dossier.mkdir(parents=True)
    chemin = dossier / "outil-service.toml"
    chemin.write_text(
        "[meta]\n"
        'unit_type = "service"\n'
        "enabled = false\n"
        f'requires_exec = "{requires_exec}"\n'
        '\n[Unit]\nDescription = "T"\n'
        '\n[Service]\nExecStart = "/usr/bin/foo"\n',
        encoding="utf-8",
    )
    return chemin


@pytest.mark.parametrize(("present", "attendu"), [(True, True), (False, False)])
def test_prerequis_nomme_est_cherche_dans_le_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    logger: MagicMock,
    *,
    present: bool,
    attendu: bool,
) -> None:
    """Un prérequis sans chemin absolu est résolu via PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if present:
        outil = bin_dir / "mon-outil-xyz"
        outil.write_text("#!/bin/sh\n", encoding="utf-8")
        outil.chmod(stat.S_IRWXU)
    monkeypatch.setenv("PATH", str(bin_dir))
    toml = _toml_avec_prerequis(tmp_path / "src", "mon-outil-xyz")
    restaurateur = SystemdUnitRestorer(logger=logger, executor=MagicMock())

    ok, nom = restaurateur.restore(toml, tmp_path / "dest")

    assert ok is attendu
    assert nom == ("outil.service" if attendu else "")
    if not attendu:
        messages = [c.args[0] for c in logger.log_error.call_args_list]
        assert any("prérequis manquant : mon-outil-xyz" in m for m in messages)


# --- base.py : unités utilisateur et timers ---


def test_creation_impossible_du_dossier_d_unites_utilisateur(
    xdg_casse: Path, logger: MagicMock
) -> None:
    """Si le dossier des unités ne peut être créé, l'installation échoue, loggée."""
    gestionnaire = LinuxUserServiceUnitManager(logger, MagicMock())
    config = ServiceConfig(description="T", exec_start="/usr/bin/t")

    ok = gestionnaire.install_service_unit_with_name("outil", config)

    assert ok is False
    logger.log_error.assert_called_once()
    message = logger.log_error.call_args.args[0]
    assert message.startswith("Erreur lors de la création du répertoire")
    assert str(xdg_casse) in message


def test_installation_de_timer_echoue_si_l_ecriture_echoue(
    xdg_casse: Path, logger: MagicMock
) -> None:
    """Un timer dont l'unité ne peut pas être écrite n'est ni rechargé ni activé."""
    executeur = MagicMock()
    gestionnaire = LinuxUserTimerUnitManager(logger, executeur)

    ok = gestionnaire.install_timer_unit(
        TimerConfig(description="T", unit="backup.service", on_calendar="daily")
    )

    assert ok is False
    executeur.reload_systemd.assert_not_called()


def test_suppression_de_timer_echoue_si_le_fichier_ne_peut_etre_supprime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logger: MagicMock
) -> None:
    """Si l'unité .timer n'est pas supprimable, la suppression échoue."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    unites = tmp_path / "systemd" / "user"
    (unites / "backup.timer").mkdir(parents=True)  # un dossier : unlink échoue
    executeur = MagicMock()
    gestionnaire = LinuxUserTimerUnitManager(logger, executeur)

    assert gestionnaire.remove_timer_unit("backup") is False

    executeur.reload_systemd.assert_not_called()


def test_liste_des_timers_en_repli_texte_ignore_les_lignes_inutilisables(
    logger: MagicMock,
) -> None:
    """Le repli texte saute lignes vides, indentées et à un seul champ."""
    executeur = MagicMock()
    executeur._run_systemctl.side_effect = [
        cmd_result(success=False, stderr="invalid option"),
        cmd_result(
            stdout=(
                "NEXT LEFT LAST PASSED UNIT ACTIVATES\n"
                "\n"
                "  ligne indentée a b\n"
                "seul\n"
                "Mon 1h Sun 2h a.timer a.service\n"
            )
        ),
    ]

    timers = LinuxTimerUnitManager(logger, executeur).list_timers()

    assert timers == [{"unit": "a.timer", "activates": "a.service"}]


def test_is_active_delegue_a_l_executeur(logger: MagicMock) -> None:
    """is_active interroge l'exécuteur avec le nom d'unité tel quel."""
    executeur = MagicMock()
    executeur.is_active.return_value = True

    assert UnitManager(logger, executeur).is_active("a.service") is True

    executeur.is_active.assert_called_once_with("a.service")


def test_ecriture_d_unite_en_echec_apres_ouverture_est_signalee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logger: MagicMock
) -> None:
    """Si fchmod échoue après l'ouverture, False, erreur loggée, fd fermé."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    vrai_close = os.close
    fermes: list[int] = []
    recus: list[int] = []

    def _fchmod_en_echec(fd: int, mode: int) -> None:
        recus.append(fd)
        raise OSError(5, "simulé")  # ne ferme volontairement pas le fd

    def _close_espion(fd: int) -> None:
        fermes.append(fd)
        vrai_close(fd)

    monkeypatch.setattr("linuxtools.systemd.base.os.fchmod", _fchmod_en_echec)
    monkeypatch.setattr(os, "close", _close_espion)
    gestionnaire = LinuxUserServiceUnitManager(logger, MagicMock())
    config = ServiceConfig(description="T", exec_start="/usr/bin/t")

    ok = gestionnaire.install_service_unit_with_name("outil", config)

    assert ok is False
    message = logger.log_error.call_args.args[0]
    assert message.startswith("Erreur lors de l'écriture de")
    assert "simulé" in message
    assert len(recus) == 1
    assert fermes.count(recus[0]) == 1


def test_ecriture_d_unite_echec_tardif_de_fdopen_propage_l_erreur_d_origine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logger: MagicMock
) -> None:
    """Échec réel de fdopen après prise du fd : erreur d'origine, aucun fd ne fuit."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    vrai_fdopen = os.fdopen

    def _fdopen_encodage_invalide(fd: int, mode: str, **_: object) -> Any:
        # io.open prend le fd puis échoue sur l'encodage, et ferme le fd lui-même
        return vrai_fdopen(fd, mode, encoding="encodage-inexistant")

    monkeypatch.setattr("linuxtools.systemd.base.os.fdopen", _fdopen_encodage_invalide)
    gestionnaire = LinuxUserServiceUnitManager(logger, MagicMock())
    config = ServiceConfig(description="T", exec_start="/usr/bin/t")
    avant = descripteurs_ouverts()

    with pytest.raises(LookupError, match="encodage-inexistant"):
        gestionnaire.install_service_unit_with_name("outil", config)

    assert descripteurs_ouverts() == avant
    logger.log_error.assert_not_called()
