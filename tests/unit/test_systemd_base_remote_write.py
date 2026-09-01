"""Tests pour `_write_unit_content_remote` (systemd/base.py).

Écriture distante d'un fichier d'unité systemd via
`install -m 644 -T /dev/stdin <dest>` (une seule commande, cf.
correctif de sécurité « fenêtre de permissions / suivi de symlink »).
Cette fonction n'avait aucun test avant ce plan.

Complété par le routage vers cette fonction (et sa jumelle de
suppression `_remove_unit_content_remote`) depuis les managers système
et utilisateur : sans ces tests, un aiguillage `if self._remote_write:`
inversé retomberait silencieusement sur le chemin local.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandResult
from linuxtools.systemd.base import (
    UnitManager,
    UserUnitManager,
    _remove_unit_content_remote,
    _write_unit_content_remote,
)
from linuxtools.systemd.executor import SystemdExecutor


def _result(success: bool = True, stderr: str = "") -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout="",
        stderr=stderr,
        success=success,
        duration=0.01,
    )


class TestWriteUnitContentRemote:
    """Tests de `_write_unit_content_remote` (executor.run_raw)."""

    def test_ecriture_distante_emet_install_avec_mode_et_no_target_directory(
        self,
    ) -> None:
        """Un seul appel `install -m 644 -T /dev/stdin <dest>` : `-T`
        empêche `install` de suivre un symlink ou de créer un fichier
        fantôme si la destination est un répertoire (A01)."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        result = _write_unit_content_remote(
            unit_path, "[Unit]\n", executor, logger
        )

        # Assert
        assert result is True
        executor.run_raw.assert_called_once_with(
            ["install", "-m", "644", "-T", "/dev/stdin", unit_path],
            stdin="[Unit]\n",
        )

    def test_ecriture_distante_passe_le_contenu_par_stdin(self) -> None:
        """Le contenu de l'unité transite par stdin, jamais par argv
        (A09 : pas d'exposition du contenu via `ps`)."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()
        contenu = "[Service]\nExecStart=/usr/bin/mon-binaire\n"

        # Act
        _write_unit_content_remote(unit_path, contenu, executor, logger)

        # Assert
        install_call = executor.run_raw.call_args
        assert contenu not in install_call.args[0]
        assert install_call.args[0][-1] == unit_path
        assert install_call.kwargs["stdin"] == contenu

    def test_ecriture_distante_echec_retourne_false_et_logue(self) -> None:
        """Échec d'`install` -> False, une seule erreur loguée, pas de
        second mode d'échec (plus de `chmod` séparé)."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(
            False, stderr="permission denied"
        )
        logger = MagicMock()

        # Act
        result = _write_unit_content_remote(
            unit_path, "[Unit]\n", executor, logger
        )

        # Assert
        assert result is False
        executor.run_raw.assert_called_once()
        logger.log_error.assert_called_once()
        logger.log_info.assert_not_called()
        assert "permission denied" in logger.log_error.call_args.args[0]

    def test_ecriture_distante_succes_logue_le_chemin(self) -> None:
        """Succès -> True, un seul log d'information mentionnant le
        chemin de destination."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        result = _write_unit_content_remote(
            unit_path, "[Unit]\n", executor, logger
        )

        # Assert
        assert result is True
        logger.log_info.assert_called_once()
        assert unit_path in logger.log_info.call_args.args[0]
        logger.log_error.assert_not_called()


class TestRemoveUnitContentRemote:
    """Tests de `_remove_unit_content_remote` (executor.run_raw)."""

    def test_suppression_distante_emet_rm_force(self) -> None:
        """La commande émise est exactement `rm -f <dest>` : le `-f`
        rend l'absence de fichier non fatale, jamais un échec."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        result = _remove_unit_content_remote(unit_path, executor, logger)

        # Assert
        assert result is True
        executor.run_raw.assert_called_once_with(
            ["rm", "-f", unit_path]
        )

    def test_suppression_distante_succes_logue_le_chemin(self) -> None:
        """Succès -> True, un seul log d'information mentionnant le
        chemin supprimé."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        result = _remove_unit_content_remote(unit_path, executor, logger)

        # Assert
        assert result is True
        logger.log_info.assert_called_once()
        assert unit_path in logger.log_info.call_args.args[0]
        logger.log_error.assert_not_called()

    def test_suppression_distante_echec_retourne_false_et_logue(
        self,
    ) -> None:
        """Échec de `rm -f` -> False, une seule erreur loguée avec le
        stderr de la commande."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(
            False, stderr="permission denied"
        )
        logger = MagicMock()

        # Act
        result = _remove_unit_content_remote(unit_path, executor, logger)

        # Assert
        assert result is False
        logger.log_error.assert_called_once()
        assert "permission denied" in logger.log_error.call_args.args[0]
        logger.log_info.assert_not_called()

    def test_suppression_distante_n_utilise_pas_stdin(self) -> None:
        """Cas limite : la suppression ne transmet aucun contenu, à la
        différence de l'écriture."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        _remove_unit_content_remote(unit_path, executor, logger)

        # Assert
        call = executor.run_raw.call_args
        assert "stdin" not in call.kwargs or call.kwargs["stdin"] is None


class TestRemoteWriteRouting:
    """Tests de l'aiguillage `if self._remote_write:` (4 méthodes,
    2 sens chacune) — cf. `_write_unit_file` / `_remove_unit_file` des
    managers système (`UnitManager`) et utilisateur (`UserUnitManager`).
    """

    def test_ecriture_systeme_distante_passe_par_l_executor(self) -> None:
        """`remote_write=True` : l'écriture système emprunte la voie
        distante (`install ...`), pas l'écriture locale."""
        # Arrange
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()
        manager = UnitManager(logger, executor, remote_write=True)

        # Act
        result = manager._write_unit_file(
            "mon-outil.service", "[Unit]\n"
        )

        # Assert
        assert result is True
        executor.run_raw.assert_called_once()
        command = executor.run_raw.call_args.args[0]
        assert command == [
            "install", "-m", "644", "-T", "/dev/stdin",
            "/etc/systemd/system/mon-outil.service",
        ]
        assert executor.run_raw.call_args.kwargs["stdin"] == "[Unit]\n"

    def test_ecriture_systeme_locale_n_appelle_pas_l_executor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`remote_write=False` (défaut) : l'écriture système reste
        locale, l'executor n'est jamais sollicité."""
        # Arrange
        monkeypatch.setattr(UnitManager, "SYSTEMD_UNIT_PATH", str(tmp_path))
        executor = MagicMock(spec=SystemdExecutor)
        logger = MagicMock()
        manager = UnitManager(logger, executor, remote_write=False)

        # Act
        result = manager._write_unit_file(
            "mon-outil.service", "[Unit]\n"
        )

        # Assert
        assert result is True
        executor.run_raw.assert_not_called()
        fichier_ecrit = tmp_path / "mon-outil.service"
        assert fichier_ecrit.read_text() == "[Unit]\n"

    def test_suppression_systeme_distante_passe_par_l_executor(
        self,
    ) -> None:
        """`remote_write=True` : la suppression système emprunte la
        voie distante (`rm -f ...`)."""
        # Arrange
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()
        manager = UnitManager(logger, executor, remote_write=True)

        # Act
        result = manager._remove_unit_file("mon-outil.service")

        # Assert
        assert result is True
        executor.run_raw.assert_called_once()
        assert executor.run_raw.call_args.args[0] == [
            "rm", "-f", "/etc/systemd/system/mon-outil.service",
        ]

    def test_suppression_systeme_locale_n_appelle_pas_l_executor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`remote_write=False` (défaut) : la suppression système
        reste locale, l'executor n'est jamais sollicité."""
        # Arrange
        monkeypatch.setattr(UnitManager, "SYSTEMD_UNIT_PATH", str(tmp_path))
        executor = MagicMock(spec=SystemdExecutor)
        logger = MagicMock()
        manager = UnitManager(logger, executor, remote_write=False)
        fichier_present = tmp_path / "mon-outil.service"
        fichier_present.write_text("[Unit]\n")

        # Act
        result = manager._remove_unit_file("mon-outil.service")

        # Assert
        assert result is True
        executor.run_raw.assert_not_called()
        assert not fichier_present.exists()

    def test_ecriture_utilisateur_distante_passe_par_l_executor(
        self,
    ) -> None:
        """`remote_write=True` : l'écriture utilisateur emprunte la
        voie distante (`install ...`)."""
        # Arrange
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()
        manager = UserUnitManager(logger, executor, remote_write=True)

        # Act
        result = manager._write_unit_file(
            "mon-outil.service", "[Unit]\n"
        )

        # Assert
        assert result is True
        executor.run_raw.assert_called_once()
        command = executor.run_raw.call_args.args[0]
        attendu = os.path.join(manager.unit_path, "mon-outil.service")
        assert command == [
            "install", "-m", "644", "-T", "/dev/stdin", attendu,
        ]
        assert executor.run_raw.call_args.kwargs["stdin"] == "[Unit]\n"

    def test_ecriture_utilisateur_locale_n_appelle_pas_l_executor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`remote_write=False` (défaut) : l'écriture utilisateur
        reste locale, l'executor n'est jamais sollicité."""
        # Arrange
        monkeypatch.setattr(
            UserUnitManager, "SYSTEMD_USER_UNIT_PATH", str(tmp_path)
        )
        executor = MagicMock(spec=SystemdExecutor)
        logger = MagicMock()
        manager = UserUnitManager(logger, executor, remote_write=False)

        # Act
        result = manager._write_unit_file(
            "mon-outil.service", "[Unit]\n"
        )

        # Assert
        assert result is True
        executor.run_raw.assert_not_called()
        fichier_ecrit = tmp_path / "mon-outil.service"
        assert fichier_ecrit.read_text() == "[Unit]\n"

    def test_suppression_utilisateur_distante_passe_par_l_executor(
        self,
    ) -> None:
        """`remote_write=True` : la suppression utilisateur emprunte
        la voie distante (`rm -f ...`)."""
        # Arrange
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()
        manager = UserUnitManager(logger, executor, remote_write=True)

        # Act
        result = manager._remove_unit_file("mon-outil.service")

        # Assert
        assert result is True
        executor.run_raw.assert_called_once()
        attendu = os.path.join(manager.unit_path, "mon-outil.service")
        assert executor.run_raw.call_args.args[0] == [
            "rm", "-f", attendu,
        ]

    def test_suppression_utilisateur_locale_n_appelle_pas_l_executor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`remote_write=False` (défaut) : la suppression utilisateur
        reste locale, l'executor n'est jamais sollicité."""
        # Arrange
        monkeypatch.setattr(
            UserUnitManager, "SYSTEMD_USER_UNIT_PATH", str(tmp_path)
        )
        executor = MagicMock(spec=SystemdExecutor)
        logger = MagicMock()
        manager = UserUnitManager(logger, executor, remote_write=False)
        fichier_present = tmp_path / "mon-outil.service"
        fichier_present.write_text("[Unit]\n")

        # Act
        result = manager._remove_unit_file("mon-outil.service")

        # Assert
        assert result is True
        executor.run_raw.assert_not_called()
        assert not fichier_present.exists()
