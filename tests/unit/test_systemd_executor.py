"""Tests pour le module systemd.executor."""

import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandResult
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.systemd.executor import (
    SystemdExecutor,
    UserSystemdExecutor,
)


def _result(
    return_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    command: tuple[str, ...] = ("systemctl",),
) -> CommandResult:
    """Construit un CommandResult prêt à retourner par un mock."""
    return CommandResult(
        command=command,
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        success=return_code == 0,
        duration=0.0,
    )


class TestSystemdExecutorValidation:
    """Tests pour la validation des noms d'unités dans SystemdExecutor."""

    def _make_executor(self) -> SystemdExecutor:
        """Crée un executor avec un logger mock."""
        logger = MagicMock()
        return SystemdExecutor(logger)

    def test_enable_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans enable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.enable_unit("bad;name.service")

    def test_disable_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans disable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.disable_unit("../etc.service")

    def test_start_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans start_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.start_unit("$(cmd).service")

    def test_stop_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans stop_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.stop_unit("bad name.service")

    def test_restart_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans restart_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.restart_unit(";evil.service")

    def test_get_status_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans get_status."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.get_status("../passwd.service")

    def test_is_enabled_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans is_enabled."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.is_enabled("bad;cmd.timer")

    def test_mask_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans mask_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.mask_unit("bad;name.service")

    def test_unmask_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans unmask_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.unmask_unit("../etc.service")

    def test_is_masked_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet d'un nom invalide dans is_masked."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="invalide"):
            executor.is_masked("bad;cmd.service")

    def test_nom_valide_accepte(self) -> None:
        """Vérifie que les noms valides passent la validation."""
        executor = self._make_executor()
        try:
            executor.get_status("backup.service")
        except ValueError:
            pytest.fail("Nom valide rejeté par la validation")

    def test_rejet_extension_inconnue(self) -> None:
        """Rejette une extension non autorisée dans enable_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="non autorisée"):
            executor.enable_unit("backup.path")

    def test_rejet_sans_extension(self) -> None:
        """Rejette un nom sans extension dans start_unit."""
        executor = self._make_executor()
        with pytest.raises(ValueError, match="sans extension"):
            executor.start_unit("backup")


class TestUserSystemdExecutorValidation:
    """Tests pour la validation dans UserSystemdExecutor."""

    def test_enable_unit_rejette_nom_invalide(self) -> None:
        """Vérifie le rejet dans l'executor utilisateur."""
        logger = MagicMock()
        executor = UserSystemdExecutor(logger)
        with pytest.raises(ValueError, match="invalide"):
            executor.enable_unit("bad;name.service")


class TestSystemdExecutorMocked:
    """Tests pour SystemdExecutor avec un CommandExecutor injecté mocké."""

    def _make_executor(
        self,
    ) -> tuple[SystemdExecutor, MagicMock, MagicMock]:
        """Crée un executor avec logger et CommandExecutor mockés."""
        logger = MagicMock()
        command_executor = MagicMock()
        return (
            SystemdExecutor(logger, command_executor),
            logger,
            command_executor,
        )

    def test_reload_systemd_succes(self) -> None:
        """reload_systemd() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.reload_systemd()
        assert result is True
        logger.log_info.assert_called_once()

    def test_reload_systemd_echec(self) -> None:
        """reload_systemd() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.reload_systemd()
        assert result is False
        logger.log_error.assert_called_once()

    def test_enable_unit_succes_avec_now(self) -> None:
        """enable_unit() avec now=True retourne True."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.enable_unit("backup.service", now=True)
        assert result is True
        logger.log_info.assert_called_once()
        args = command_executor.run.call_args[0][0]
        assert "--now" in args

    def test_enable_unit_accepte_nom_echappe_systemd(self) -> None:
        """enable_unit() accepte un nom produit par systemd-escape."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        nom = r"media-nas\x2dbackup.mount"
        assert executor.enable_unit(nom) is True
        args = command_executor.run.call_args[0][0]
        assert nom in args

    def test_enable_unit_succes_sans_now(self) -> None:
        """enable_unit() avec now=False ne passe pas --now."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.enable_unit("backup.service", now=False)
        assert result is True
        args = command_executor.run.call_args[0][0]
        assert "--now" not in args

    def test_enable_unit_echec(self) -> None:
        """enable_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.enable_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_disable_unit_succes(self) -> None:
        """disable_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.disable_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_disable_unit_echec(self) -> None:
        """disable_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.disable_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_disable_unit_ignore_errors(self) -> None:
        """disable_unit() avec ignore_errors retourne True."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.disable_unit("backup.service", ignore_errors=True)
        assert result is True
        logger.log_warning.assert_called_once()

    def test_start_unit_succes(self) -> None:
        """start_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.start_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_start_unit_echec(self) -> None:
        """start_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.start_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_stop_unit_succes(self) -> None:
        """stop_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.stop_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_stop_unit_echec(self) -> None:
        """stop_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.stop_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_restart_unit_succes(self) -> None:
        """restart_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.restart_unit("backup.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_restart_unit_echec(self) -> None:
        """restart_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.restart_unit("backup.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_get_status_retourne_statut(self) -> None:
        """get_status() retourne le statut de l unite."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="active\n")
        status = executor.get_status("backup.service")
        assert status == "active"

    def test_get_status_retourne_chaine_vide_si_commande_echoue(
        self,
    ) -> None:
        """get_status() retourne "" (jamais None) si la commande echoue.

        CommandExecutor.probe() ne leve jamais : une erreur systeme est
        deja convertie en CommandResult avec un stdout vide.
        """
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(
            return_code=-1, stdout="", stderr="systemctl non trouve"
        )
        result = executor.get_status("backup.service")
        assert result == ""

    def test_is_active_retourne_true(self) -> None:
        """is_active() retourne True si statut == active."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="active\n")
        assert executor.is_active("backup.service") is True

    def test_is_active_retourne_false(self) -> None:
        """is_active() retourne False si statut != active."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="inactive\n")
        assert executor.is_active("backup.service") is False

    def test_is_enabled_retourne_true(self) -> None:
        """is_enabled() retourne True si statut == enabled."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="enabled\n")
        assert executor.is_enabled("backup.service") is True

    def test_is_enabled_retourne_false(self) -> None:
        """is_enabled() retourne False si statut != enabled."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="disabled\n")
        assert executor.is_enabled("backup.service") is False

    def test_is_enabled_erreur(self) -> None:
        """is_enabled() retourne False en cas d erreur."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(
            return_code=-1, stdout="", stderr="erreur"
        )
        result = executor.is_enabled("backup.service")
        assert result is False

    def test_is_masked_retourne_true(self) -> None:
        """is_masked() retourne True si stdout == masked."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="masked\n")
        assert executor.is_masked("packagekit.service") is True

    def test_is_masked_retourne_false(self) -> None:
        """is_masked() retourne False si stdout != masked."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="enabled\n")
        assert executor.is_masked("packagekit.service") is False

    def test_is_masked_erreur(self) -> None:
        """is_masked() retourne False en cas d erreur."""
        executor, _, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(
            return_code=-1, stdout="", stderr="erreur"
        )
        assert executor.is_masked("packagekit.service") is False

    def test_mask_unit_succes(self) -> None:
        """mask_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.mask_unit("packagekit.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_mask_unit_echec(self) -> None:
        """mask_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.mask_unit("packagekit.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_unmask_unit_succes(self) -> None:
        """unmask_unit() retourne True en cas de succes."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.unmask_unit("packagekit.service")
        assert result is True
        logger.log_info.assert_called_once()

    def test_unmask_unit_echec(self) -> None:
        """unmask_unit() retourne False en cas d erreur."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.unmask_unit("packagekit.service")
        assert result is False
        logger.log_error.assert_called_once()


class TestSystemdExecutorRunRaw:
    """Tests pour SystemdExecutor.run_raw() avec un executor mocké.

    Distinct de TestSystemdExecutorMocked : ces tests ciblent
    spécifiquement le passe-plat run_raw() (utilisé par UnitManager
    pour écrire/supprimer un fichier d'unité distant), pas
    _run_systemctl().
    """

    def _make_executor(
        self,
    ) -> tuple[SystemdExecutor, MagicMock]:
        """Crée un executor avec un CommandExecutor mocké."""
        logger = MagicMock()
        command_executor = MagicMock()
        return SystemdExecutor(logger, command_executor), command_executor

    def test_run_raw_transmet_command_et_stdin_a_l_executor(self) -> None:
        """command et stdin atteignent self._executor.run() tels quels.

        L'attendu est un littéral écrit indépendamment de `command` (pas
        la même variable) : si run_raw() mutait la liste en place avant
        de la transmettre, les deux côtés de l'assertion ne muteraient
        pas ensemble et le test détecterait la mutation.
        """
        executor, command_executor = self._make_executor()
        command = [
            "install",
            "-m",
            "644",
            "-T",
            "/dev/stdin",
            "/tmp/x.service",
        ]
        executor.run_raw(command, stdin="contenu")
        command_executor.run.assert_called_once_with(
            ["install", "-m", "644", "-T", "/dev/stdin", "/tmp/x.service"],
            stdin="contenu",
        )

    def test_run_raw_sans_stdin_transmet_none_par_defaut(self) -> None:
        """Sans argument stdin, stdin=None est transmis explicitement.

        Littéral indépendant pour la même raison que le test précédent.
        """
        executor, command_executor = self._make_executor()
        command = ["rm", "-f", "/tmp/x.service"]
        executor.run_raw(command)
        command_executor.run.assert_called_once_with(
            ["rm", "-f", "/tmp/x.service"], stdin=None
        )

    def test_run_raw_retourne_command_result_sans_transformation(
        self,
    ) -> None:
        """run_raw() retourne l'objet CommandResult de l'executor tel quel.

        Vérifié par identité d'objet (is), pas par égalité de champs :
        prouve l'absence de reconstruction/copie du CommandResult.
        """
        executor, command_executor = self._make_executor()
        objet_result_attendu = _result(
            return_code=1,
            stdout="out",
            stderr="err",
            command=("rm", "-f", "/tmp/x.service"),
        )
        command_executor.run.return_value = objet_result_attendu
        resultat = executor.run_raw(["rm", "-f", "/tmp/x.service"])
        assert resultat is objet_result_attendu


class TestSystemdExecutorSansExecutorInjecte:
    """Non-régression : SystemdExecutor(logger) reste utilisable seul."""

    def test_sans_executor_utilise_linuxcommandexecutor_local(
        self,
    ) -> None:
        """Sans executor injecté, un LinuxCommandExecutor local est créé."""
        from linuxtools.commands.runner import LinuxCommandExecutor

        logger = MagicMock()
        executor = SystemdExecutor(logger)
        assert isinstance(executor._executor, LinuxCommandExecutor)


class TestSystemdExecutorListUnits:
    """Tests pour SystemdExecutor.list_units()."""

    def _make_executor(
        self,
    ) -> tuple[SystemdExecutor, MagicMock]:
        """Crée un executor avec un CommandExecutor mocké.

        Le logger n'est pas retourné : aucun test de cette classe ne
        s'appuie dessus (ils ne vérifient que le CommandExecutor et
        le résultat de list_units()).
        """
        logger = MagicMock()
        command_executor = MagicMock()
        return SystemdExecutor(logger, command_executor), command_executor

    def test_list_units_json_valide(self) -> None:
        """list_units() parse une réponse JSON à plusieurs unités."""
        executor, command_executor = self._make_executor()
        json_stdout = json.dumps(
            [
                {
                    "unit": "backup.service",
                    "load": "loaded",
                    "active": "active",
                    "sub": "running",
                    "description": "Backup service",
                },
                {
                    "unit": "sshd.service",
                    "load": "loaded",
                    "active": "inactive",
                    "sub": "dead",
                    "description": "OpenSSH server",
                },
            ]
        )
        command_executor.probe.return_value = _result(stdout=json_stdout)
        units = executor.list_units()
        assert units == [
            {
                "unit": "backup.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "Backup service",
            },
            {
                "unit": "sshd.service",
                "load": "loaded",
                "active": "inactive",
                "sub": "dead",
                "description": "OpenSSH server",
            },
        ]

    def test_list_units_json_vide(self) -> None:
        """list_units() retourne [] si le JSON est une liste vide."""
        executor, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="[]")
        units = executor.list_units()
        assert units == []

    def test_list_units_fallback_texte(self) -> None:
        """list_units() bascule sur le fallback texte si JSON non géré.

        Vérifie que la 2ᵉ commande (--no-legend --plain) est bien
        appelée et parsée correctement, y compris une description
        contenant des espaces.
        """
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(
                stdout=(
                    "backup.service loaded active running "
                    "Service de sauvegarde quotidienne\n"
                )
            ),
        ]
        units = executor.list_units()
        assert units == [
            {
                "unit": "backup.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "Service de sauvegarde quotidienne",
            }
        ]
        second_call_args = command_executor.probe.call_args_list[1][0][0]
        assert "--no-legend" in second_call_args
        assert "--plain" in second_call_args
        assert "--output=json" not in second_call_args

    def test_list_units_fallback_texte_json_invalide(self) -> None:
        """list_units() bascule sur le fallback si le JSON est invalide.

        Cas distinct de return_code != 0 : ici return_code == 0 mais
        stdout n'est pas du JSON valide (couvre json.JSONDecodeError).
        """
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=0, stdout="pas du json"),
            _result(stdout="backup.service loaded active running Backup\n"),
        ]
        units = executor.list_units()
        assert units == [
            {
                "unit": "backup.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "Backup",
            }
        ]

    def test_list_units_erreur_subprocess(self) -> None:
        """list_units() lève RuntimeError si systemctl échoue (JSON)."""
        executor, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(
            return_code=1, stderr="erreur inconnue"
        )
        with pytest.raises(RuntimeError, match="erreur inconnue"):
            executor.list_units()

    def test_list_units_erreur_subprocess_fallback(self) -> None:
        """list_units() lève RuntimeError si le fallback texte échoue."""
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(return_code=1, stderr="erreur fallback"),
        ]
        with pytest.raises(RuntimeError, match="erreur fallback"):
            executor.list_units()

    def test_list_units_fallback_ligne_sans_description(self) -> None:
        """Une ligne texte sans description donne description vide."""
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(stdout="backup.service loaded active running\n"),
        ]
        units = executor.list_units()
        assert units == [
            {
                "unit": "backup.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "",
            }
        ]

    def test_list_units_fallback_ligne_malformee(self) -> None:
        """Les lignes vides ou à moins de 4 tokens sont ignorées.

        Couvre le fallback texte (``_list_units_text_fallback()``) :
        une ligne vide est ignorée, tout comme une ligne dont le
        split produit moins de 4 tokens (ex: nom d'unité seul, ou nom
        d'unité + load sans active/sub) — sans lever d'exception. Une
        ligne valide au milieu confirme que le parsing continue
        normalement après les lignes malformées.
        """
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(
                stdout=(
                    "foo.service\n"
                    "\n"
                    "bar.service loaded\n"
                    "backup.service loaded active running Backup\n"
                )
            ),
        ]
        units = executor.list_units()
        assert units == [
            {
                "unit": "backup.service",
                "load": "loaded",
                "active": "active",
                "sub": "running",
                "description": "Backup",
            }
        ]

    def test_list_units_user_executor_ajoute_flag_user(self) -> None:
        """UserSystemdExecutor hérite list_units() avec --user."""
        logger = MagicMock()
        command_executor = MagicMock()
        executor = UserSystemdExecutor(logger, command_executor)
        command_executor.probe.return_value = _result(stdout="[]")
        executor.list_units()
        command_executor.probe.assert_called_once_with(
            [
                "systemctl",
                "--user",
                "list-units",
                "--no-pager",
                "--output=json",
            ]
        )


class TestSystemdExecutorListUnitFiles:
    """Tests pour SystemdExecutor.list_unit_files()."""

    def _make_executor(
        self,
    ) -> tuple[SystemdExecutor, MagicMock]:
        """Crée un executor avec un CommandExecutor mocké.

        Le logger n'est pas retourné : aucun test de cette classe ne
        s'appuie dessus (ils ne vérifient que le CommandExecutor et
        le résultat de list_unit_files()).
        """
        logger = MagicMock()
        command_executor = MagicMock()
        return SystemdExecutor(logger, command_executor), command_executor

    def test_list_unit_files_json_valide(self) -> None:
        """list_unit_files() parse une réponse JSON à plusieurs entrées."""
        executor, command_executor = self._make_executor()
        json_stdout = json.dumps(
            [
                {
                    "unit_file": "backup.service",
                    "state": "enabled",
                    "preset": "disabled",
                },
                {
                    "unit_file": "sshd.service",
                    "state": "enabled",
                    "preset": "enabled",
                },
            ]
        )
        command_executor.probe.return_value = _result(stdout=json_stdout)
        files = executor.list_unit_files()
        assert files == [
            {
                "unit_file": "backup.service",
                "state": "enabled",
                "preset": "disabled",
            },
            {
                "unit_file": "sshd.service",
                "state": "enabled",
                "preset": "enabled",
            },
        ]

    def test_list_unit_files_json_vide(self) -> None:
        """list_unit_files() retourne [] si le JSON est une liste vide."""
        executor, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="[]")
        files = executor.list_unit_files()
        assert files == []

    def test_list_unit_files_filtre_type_et_state(self) -> None:
        """Les filtres --type/--state sont bien passés à la commande."""
        executor, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="[]")
        executor.list_unit_files(unit_type="service", state="enabled")
        args = command_executor.probe.call_args[0][0]
        assert "--type=service" in args
        assert "--state=enabled" in args

    def test_list_unit_files_sans_filtre(self) -> None:
        """Sans paramètre, aucun --type/--state dans la commande."""
        executor, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(stdout="[]")
        executor.list_unit_files()
        args = command_executor.probe.call_args[0][0]
        assert not any(arg.startswith("--type=") for arg in args)
        assert not any(arg.startswith("--state=") for arg in args)

    def test_list_unit_files_fallback_texte(self) -> None:
        """list_unit_files() bascule sur le fallback texte si JSON non géré.

        Vérifie que la 2ᵉ commande (--no-legend, filtres propagés) est
        bien appelée et parsée correctement (3 colonnes avec preset).
        """
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(stdout="abrt-journal-core.service enabled enabled\n"),
        ]
        files = executor.list_unit_files(unit_type="service", state="enabled")
        assert files == [
            {
                "unit_file": "abrt-journal-core.service",
                "state": "enabled",
                "preset": "enabled",
            }
        ]
        second_call_args = command_executor.probe.call_args_list[1][0][0]
        assert "--no-legend" in second_call_args
        assert "--type=service" in second_call_args
        assert "--state=enabled" in second_call_args
        assert "--output=json" not in second_call_args

    def test_list_unit_files_fallback_texte_sans_preset(self) -> None:
        """Une ligne texte à 2 tokens donne un preset vide."""
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(stdout="foo.service enabled\n"),
        ]
        files = executor.list_unit_files()
        assert files == [
            {
                "unit_file": "foo.service",
                "state": "enabled",
                "preset": "",
            }
        ]

    def test_list_unit_files_fallback_texte_json_invalide(self) -> None:
        """list_unit_files() bascule sur le fallback si le JSON est invalide.

        Cas distinct de return_code != 0 : ici return_code == 0 mais
        stdout n'est pas du JSON valide (couvre json.JSONDecodeError).
        """
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=0, stdout="pas du json"),
            _result(stdout="foo.service enabled enabled\n"),
        ]
        files = executor.list_unit_files()
        assert files == [
            {
                "unit_file": "foo.service",
                "state": "enabled",
                "preset": "enabled",
            }
        ]

    def test_list_unit_files_erreur_subprocess(self) -> None:
        """list_unit_files() lève RuntimeError si systemctl échoue (JSON)."""
        executor, command_executor = self._make_executor()
        command_executor.probe.return_value = _result(
            return_code=1, stderr="erreur inconnue"
        )
        with pytest.raises(RuntimeError, match="erreur inconnue"):
            executor.list_unit_files()

    def test_list_unit_files_erreur_subprocess_fallback(self) -> None:
        """list_unit_files() lève RuntimeError si le fallback échoue."""
        executor, command_executor = self._make_executor()
        command_executor.probe.side_effect = [
            _result(return_code=1, stderr="Unknown option --output."),
            _result(return_code=1, stderr="erreur fallback"),
        ]
        with pytest.raises(RuntimeError, match="erreur fallback"):
            executor.list_unit_files()

    def test_list_unit_files_user_executor_ajoute_flag_user(self) -> None:
        """UserSystemdExecutor hérite list_unit_files() avec --user."""
        logger = MagicMock()
        command_executor = MagicMock()
        executor = UserSystemdExecutor(logger, command_executor)
        command_executor.probe.return_value = _result(stdout="[]")
        executor.list_unit_files()
        command_executor.probe.assert_called_once_with(
            [
                "systemctl",
                "--user",
                "list-unit-files",
                "--no-pager",
                "--output=json",
            ]
        )


class TestUserSystemdExecutorMocked:
    """Tests pour UserSystemdExecutor avec un CommandExecutor mocké."""

    def _make_executor(
        self,
    ) -> tuple[UserSystemdExecutor, MagicMock, MagicMock]:
        """Crée un executor utilisateur avec logger et CommandExecutor mockés."""
        logger = MagicMock()
        command_executor = MagicMock()
        return (
            UserSystemdExecutor(logger, command_executor),
            logger,
            command_executor,
        )

    def test_run_systemctl_utilise_user_flag(self) -> None:
        """_run_systemctl() utilise --user dans la commande."""
        executor, _, command_executor = self._make_executor()
        command_executor.run.return_value = _result(stdout="active\n")
        executor._run_systemctl(["status", "backup.service"])
        args = command_executor.run.call_args[0][0]
        assert "--user" in args
        assert "systemctl" in args[0]

    def test_reload_systemd_user_succes(self) -> None:
        """reload_systemd() pour user retourne True."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result()
        result = executor.reload_systemd()
        assert result is True
        logger.log_info.assert_called_once()

    def test_reload_systemd_user_echec(self) -> None:
        """reload_systemd() pour user retourne False."""
        executor, logger, command_executor = self._make_executor()
        command_executor.run.return_value = _result(return_code=1, stderr="erreur")
        result = executor.reload_systemd()
        assert result is False
        logger.log_error.assert_called_once()


class TestShowProperty:
    """Tests pour show_property() (propriété du gestionnaire ou d'une unité)."""

    def test_user_lit_une_propriete_du_gestionnaire(self) -> None:
        """Sans unité : `systemctl --user show -p NAME --value`, sans saut final."""
        command_executor = MagicMock()
        command_executor.probe.return_value = _result(stdout="/a/user /b/user\n")
        executor = UserSystemdExecutor(MagicMock(), command_executor)

        value = executor.show_property("UnitPath")

        assert value == "/a/user /b/user"
        command_executor.probe.assert_called_once_with(
            ["systemctl", "--user", "show", "-p", "UnitPath", "--value"]
        )

    def test_systeme_lit_une_propriete_d_unite(self) -> None:
        """Avec unité : elle termine la commande ; une valeur vide est rendue."""
        command_executor = MagicMock()
        command_executor.probe.return_value = _result(stdout="\n")
        executor = SystemdExecutor(MagicMock(), command_executor)

        value = executor.show_property("DropInPaths", "demo.service")

        assert value == ""
        command_executor.probe.assert_called_once_with(
            ["systemctl", "show", "-p", "DropInPaths", "--value", "demo.service"]
        )

    def test_echec_leve_runtimeerror(self) -> None:
        """Un échec de systemctl n'est pas confondu avec une propriété vide."""
        command_executor = MagicMock()
        command_executor.probe.return_value = _result(
            return_code=1, stderr="Failed to connect to bus"
        )
        executor = UserSystemdExecutor(MagicMock(), command_executor)

        with pytest.raises(RuntimeError, match="UnitPath"):
            executor.show_property("UnitPath")

    @pytest.mark.parametrize("name", ["", "Unit Path", "-p", "A=b", "A;id"])
    def test_nom_de_propriete_invalide_leve_valueerror(self, name: str) -> None:
        """Le nom de propriété est une option de systemctl : liste blanche."""
        command_executor = MagicMock()
        executor = UserSystemdExecutor(MagicMock(), command_executor)

        with pytest.raises(ValueError, match="propriété"):
            executor.show_property(name)

        command_executor.probe.assert_not_called()


class TestShowEnvironment:
    """Tests pour show_environment() (environnement du gestionnaire systemd)."""

    def test_user_lit_l_environnement_du_gestionnaire_user(self) -> None:
        """show_environment() interroge `systemctl --user` et parse KEY=VALUE."""
        command_executor = MagicMock()
        command_executor.probe.return_value = _result(
            stdout="LANG=fr_FR.UTF-8\nXDG_STATE_HOME=/home/u/etat\nVIDE=\n"
        )
        executor = UserSystemdExecutor(MagicMock(), command_executor)

        env = executor.show_environment()

        assert env == {
            "LANG": "fr_FR.UTF-8",
            "XDG_STATE_HOME": "/home/u/etat",
            "VIDE": "",
        }
        command_executor.probe.assert_called_once_with(
            ["systemctl", "--user", "show-environment"]
        )

    def test_systeme_interroge_le_gestionnaire_systeme(self) -> None:
        """Sans --user : `systemctl show-environment`, valeur avec `=` conservée."""
        command_executor = MagicMock()
        command_executor.probe.return_value = _result(stdout="A=b=c\nsans-egal\n\n")
        executor = SystemdExecutor(MagicMock(), command_executor)

        env = executor.show_environment()

        assert env == {"A": "b=c"}
        command_executor.probe.assert_called_once_with(
            ["systemctl", "show-environment"]
        )

    def test_echec_leve_runtimeerror(self) -> None:
        """Un échec de systemctl n'est pas confondu avec un environnement vide."""
        command_executor = MagicMock()
        command_executor.probe.return_value = _result(
            return_code=1, stderr="Failed to connect to bus"
        )
        executor = UserSystemdExecutor(MagicMock(), command_executor)

        with pytest.raises(RuntimeError, match="show-environment"):
            executor.show_environment()


def _faux_systemctl(dossier: Path, etat: str = "inactive") -> None:
    """Dépose un `systemctl` qui se comporte comme le vrai pour une unité.

    `show -p ActiveState --value` rend `etat` avec le code 0. Le faux
    `is-active` ignore `etat` : il rend toujours `inactive` (code 3), car
    `get_status` ne l'appelle plus (F38).
    """
    script = dossier / "systemctl"
    script.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  [ "$a" = is-active ] && { echo inactive; exit 3; }\n'
        "done\n"
        f"echo {etat}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def test_get_status_unite_inactive_ne_journalise_pas_d_erreur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange : exécuteur réel, `systemctl` simulé (unité inactive : code 3
    # avec `is-active`), PATH limité au dossier de test
    _faux_systemctl(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    logger = MagicMock()
    executor = SystemdExecutor(logger, LinuxCommandExecutor(logger=logger))

    # Act
    statut = executor.get_status("backup.service")

    # Assert : la valeur rendue est inchangée, et rien n'est journalisé en ERROR
    # (un statut inactif n'est pas une erreur, F38)
    assert statut == "inactive"
    logger.log_error.assert_not_called()


@pytest.mark.parametrize(
    ("classe", "prefixe"),
    [
        (SystemdExecutor, ["systemctl"]),
        (UserSystemdExecutor, ["systemctl", "--user"]),
    ],
)
def test_get_status_lit_activestate_sans_is_active(
    classe: type[SystemdExecutor], prefixe: list[str]
) -> None:
    # Arrange
    command_executor = MagicMock()
    command_executor.probe.return_value = _result(stdout="failed\n")

    # Act
    statut = classe(MagicMock(), command_executor).get_status("backup.service")

    # Assert : valeur inchangée, commande sans code de retour d'état (F38)
    assert statut == "failed"
    command_executor.probe.assert_called_once_with(
        [*prefixe, "show", "-p", "ActiveState", "--value", "backup.service"]
    )
    # Lecture seule : sonde (exécutée même en dry-run), jamais run
    command_executor.run.assert_not_called()


def test_get_status_dry_run_lit_l_etat_reel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange : exécuteur réel en dry-run, `systemctl` simulé qui rend `active`
    _faux_systemctl(tmp_path, etat="active")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    logger = MagicMock()
    executor = SystemdExecutor(
        logger, LinuxCommandExecutor(logger=logger, dry_run=True)
    )

    # Act
    statut = executor.get_status("backup.service")

    # Assert : l'état réel est lu malgré le dry-run (sinon "")
    assert statut == "active"


@pytest.mark.parametrize(
    ("classe", "prefixe"),
    [
        (SystemdExecutor, ["systemctl"]),
        (UserSystemdExecutor, ["systemctl", "--user"]),
    ],
)
def test_run_systemctl_sans_probe_utilise_run(
    classe: type[SystemdExecutor], prefixe: list[str]
) -> None:
    # Arrange
    command_executor = MagicMock()
    command_executor.run.return_value = _result()

    # Act
    classe(MagicMock(), command_executor)._run_systemctl(["daemon-reload"])

    # Assert : sans `probe`, comportement historique (run, pas de sonde)
    command_executor.run.assert_called_once_with([*prefixe, "daemon-reload"])
    command_executor.probe.assert_not_called()


_CLASSES = [
    (SystemdExecutor, ["systemctl"]),
    (UserSystemdExecutor, ["systemctl", "--user"]),
]
_ECHEC_JSON = _result(return_code=1, stderr="unknown option '--output=json'")

# (appel, réponses de la sonde, commandes attendues sans le préfixe systemctl)
_LECTURES: dict[
    str,
    tuple[Callable[[SystemdExecutor], object], list[CommandResult], list[list[str]]],
] = {
    "show_environment": (
        lambda e: e.show_environment(),
        [_result(stdout="A=b\n")],
        [["show-environment"]],
    ),
    "show_property": (
        lambda e: e.show_property("UnitPath", "backup.service"),
        [_result(stdout="x\n")],
        [["show", "-p", "UnitPath", "--value", "backup.service"]],
    ),
    "is_enabled": (
        lambda e: e.is_enabled("backup.service"),
        [_result(stdout="enabled\n")],
        [["is-enabled", "backup.service"]],
    ),
    "is_masked": (
        lambda e: e.is_masked("backup.service"),
        [_result(stdout="masked\n")],
        [["is-enabled", "backup.service"]],
    ),
    "list_units": (
        lambda e: e.list_units(),
        [_result(stdout="[]")],
        [["list-units", "--no-pager", "--output=json"]],
    ),
    "list_units_repli_texte": (
        lambda e: e.list_units(),
        [_ECHEC_JSON, _result(stdout="")],
        [
            ["list-units", "--no-pager", "--output=json"],
            ["list-units", "--no-pager", "--no-legend", "--plain"],
        ],
    ),
    "list_unit_files": (
        lambda e: e.list_unit_files(),
        [_result(stdout="[]")],
        [["list-unit-files", "--no-pager", "--output=json"]],
    ),
    "list_unit_files_repli_texte": (
        lambda e: e.list_unit_files(),
        [_ECHEC_JSON, _result(stdout="")],
        [
            ["list-unit-files", "--no-pager", "--output=json"],
            ["list-unit-files", "--no-pager", "--no-legend"],
        ],
    ),
}


@pytest.mark.parametrize(("classe", "prefixe"), _CLASSES, ids=["system", "user"])
@pytest.mark.parametrize("nom", list(_LECTURES))
def test_lecture_seule_passe_par_probe(
    classe: type[SystemdExecutor], prefixe: list[str], nom: str
) -> None:
    # Arrange
    appel, reponses, commandes = _LECTURES[nom]
    command_executor = MagicMock()
    command_executor.probe.side_effect = reponses

    # Act
    appel(classe(MagicMock(), command_executor))

    # Assert : sonde (exécutée même en dry-run) avec la commande attendue
    assert [c.args[0] for c in command_executor.probe.call_args_list] == [
        [*prefixe, *commande] for commande in commandes
    ]
    command_executor.run.assert_not_called()


@pytest.mark.parametrize(("classe", "prefixe"), _CLASSES, ids=["system", "user"])
@pytest.mark.parametrize(
    ("appel", "commande"),
    [
        (lambda e: e.reload_systemd(), ["daemon-reload"]),
        (lambda e: e.enable_unit("a.service", now=False), ["enable", "a.service"]),
        (lambda e: e.disable_unit("a.service", now=False), ["disable", "a.service"]),
        (lambda e: e.start_unit("a.service"), ["start", "a.service"]),
        (lambda e: e.stop_unit("a.service"), ["stop", "a.service"]),
        (lambda e: e.restart_unit("a.service"), ["restart", "a.service"]),
        (lambda e: e.mask_unit("a.service"), ["mask", "a.service"]),
        (lambda e: e.unmask_unit("a.service"), ["unmask", "a.service"]),
    ],
    ids=[
        "reload_systemd",
        "enable_unit",
        "disable_unit",
        "start_unit",
        "stop_unit",
        "restart_unit",
        "mask_unit",
        "unmask_unit",
    ],
)
def test_mutation_reste_sur_run(
    classe: type[SystemdExecutor],
    prefixe: list[str],
    appel: Callable[[SystemdExecutor], object],
    commande: list[str],
) -> None:
    # Arrange
    command_executor = MagicMock()
    command_executor.run.return_value = _result()

    # Act
    appel(classe(MagicMock(), command_executor))

    # Assert : une mutation est simulée en dry-run, donc jamais une sonde
    command_executor.run.assert_called_once_with([*prefixe, *commande])
    command_executor.probe.assert_not_called()
