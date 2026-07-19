"""Tests pour le module deploy.transport."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.models import DeployTarget
from linuxtools.deploy.transport import RsyncTransport, Transport


def _make_local_mock(return_code: int = 0) -> MagicMock:
    """Crée un mock de CommandExecutor local pour RsyncTransport."""
    mock = MagicMock(spec=CommandExecutor)
    mock.run.return_value = CommandResult(
        command=(),
        return_code=return_code,
        stdout="",
        stderr="" if return_code == 0 else "rsync error",
        success=return_code == 0,
        duration=0.1,
    )
    return mock


class TestTransportAbc:
    """Tests pour l'interface abstraite Transport."""

    def test_ne_peut_pas_etre_instanciee(self):
        """Transport est une ABC, non instanciable directement."""
        with pytest.raises(TypeError):
            Transport()  # type: ignore[abstract]


class TestRsyncTransportTransfer:
    """Tests pour RsyncTransport.transfer()."""

    def test_leve_erreur_si_source_absente(self, tmp_path):
        """FileNotFoundError si source_dir n'existe pas."""
        transport = RsyncTransport(local_executor=_make_local_mock())
        with pytest.raises(FileNotFoundError):
            transport.transfer(
                tmp_path / "absent",
                Path("/opt/app/src"),
                DeployTarget(),
            )

    def test_commande_locale_utilise_chemins_bruts(self, tmp_path):
        """Cible locale : destination = chemin brut, pas de -e ssh."""
        local = _make_local_mock()
        transport = RsyncTransport(local_executor=local)
        transport.transfer(
            tmp_path, Path("/opt/app/src"), DeployTarget()
        )

        command = local.run.call_args.args[0]
        assert command[0] == "rsync"
        assert command[-2] == f"{tmp_path}/"
        assert command[-1] == "/opt/app/src"
        assert "-e" not in command

    def test_commande_distante_prefixe_destination(self, tmp_path):
        """Cible distante : destination préfixée par user@host:."""
        local = _make_local_mock()
        transport = RsyncTransport(local_executor=local)
        transport.transfer(
            tmp_path,
            Path("/opt/app/src"),
            DeployTarget(host="srv01", user="deploy"),
        )

        command = local.run.call_args.args[0]
        assert command[-1] == "deploy@srv01:/opt/app/src"

    def test_commande_distante_avec_ssh_options_ajoute_dash_e(
        self, tmp_path
    ):
        """Des ssh_options ajoutent -e 'ssh ...' à la commande rsync."""
        local = _make_local_mock()
        transport = RsyncTransport(local_executor=local)
        transport.transfer(
            tmp_path,
            Path("/opt/app/src"),
            DeployTarget(host="srv01", ssh_options=("-p", "2222")),
        )

        command = local.run.call_args.args[0]
        assert "-e" in command
        idx = command.index("-e")
        assert command[idx + 1] == "ssh -p 2222"

    def test_options_par_defaut_incluses(self, tmp_path):
        """Les options par défaut (-a --delete) sont présentes."""
        local = _make_local_mock()
        transport = RsyncTransport(local_executor=local)
        transport.transfer(tmp_path, Path("/dst"), DeployTarget())

        command = local.run.call_args.args[0]
        assert "-a" in command
        assert "--delete" in command

    def test_extra_options_personnalisees(self, tmp_path):
        """extra_options remplace les options par défaut."""
        local = _make_local_mock()
        transport = RsyncTransport(
            local_executor=local, extra_options=("-avz",)
        )
        transport.transfer(tmp_path, Path("/dst"), DeployTarget())

        command = local.run.call_args.args[0]
        assert "-avz" in command
        assert "--delete" not in command

    def test_execute_via_local_executor_avec_timeout(self, tmp_path):
        """rsync est exécuté via l'exécuteur local avec un timeout."""
        local = _make_local_mock()
        transport = RsyncTransport(local_executor=local, timeout=120)
        transport.transfer(tmp_path, Path("/dst"), DeployTarget())

        assert local.run.call_args.kwargs["timeout"] == 120

    def test_retourne_le_resultat_de_l_executeur_local(self, tmp_path):
        """transfer() retourne tel quel le CommandResult de rsync."""
        local = _make_local_mock(return_code=1)
        transport = RsyncTransport(local_executor=local)
        result = transport.transfer(
            tmp_path, Path("/dst"), DeployTarget()
        )

        assert result.success is False
        assert result.stderr == "rsync error"

    def test_logue_le_succes_si_logger_fourni(self, tmp_path):
        """Le logger reçoit un message de succès quand rsync réussit."""
        local = _make_local_mock(return_code=0)
        logger = MagicMock()
        transport = RsyncTransport(local_executor=local, logger=logger)

        transport.transfer(tmp_path, Path("/dst"), DeployTarget())

        assert logger.log_info.call_count == 2
