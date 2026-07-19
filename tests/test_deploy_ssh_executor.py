"""Tests pour le module deploy.ssh_executor."""

from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.models import DeployTarget
from linuxtools.deploy.ssh_executor import SshCommandExecutor


def _make_local_mock(
    return_code: int = 0, stdout: str = "", stderr: str = ""
) -> MagicMock:
    """Crée un mock de CommandExecutor local pour SshCommandExecutor."""
    mock = MagicMock(spec=CommandExecutor)
    result = CommandResult(
        command=(),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        success=return_code == 0,
        duration=0.01,
    )
    mock.run.return_value = result
    mock.run_streaming.return_value = result
    return mock


class TestSshCommandExecutorInit:
    """Tests pour l'initialisation de SshCommandExecutor."""

    def test_refuse_une_cible_locale(self):
        """Lève ValueError si la cible n'a pas de host."""
        with pytest.raises(ValueError, match="distante"):
            SshCommandExecutor(DeployTarget())

    def test_accepte_une_cible_distante(self):
        """S'initialise sans erreur avec une cible distante."""
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=_make_local_mock()
        )
        assert executor is not None

    def test_cree_un_linux_command_executor_par_defaut(self):
        """Un LinuxCommandExecutor local est créé si non fourni."""
        executor = SshCommandExecutor(DeployTarget(host="srv01"))
        assert executor._local is not None


class TestSshCommandExecutorRun:
    """Tests pour SshCommandExecutor.run()."""

    def test_enveloppe_la_commande_avec_ssh(self):
        """La commande est préfixée par ssh <destination> -- <cmd>."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01", user="deploy"),
            local_executor=local,
        )
        executor.run(["echo", "hello"])

        called_cmd = local.run.call_args.args[0]
        assert called_cmd[0] == "ssh"
        assert called_cmd[-3] == "deploy@srv01"
        assert called_cmd[-2] == "--"
        assert called_cmd[-1] == "echo hello"

    def test_inclut_les_options_ssh(self):
        """Les ssh_options sont insérées avant la destination."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01", ssh_options=("-p", "2222")),
            local_executor=local,
        )
        executor.run(["ls"])

        called_cmd = local.run.call_args.args[0]
        assert called_cmd == [
            "ssh", "-p", "2222", "srv01", "--", "ls",
        ]

    def test_cwd_injecte_dans_la_commande_distante(self):
        """cwd devient un préfixe `cd <cwd> &&` côté distant."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run(["ls"], cwd="/opt/app")

        called_cmd = local.run.call_args.args[0]
        assert called_cmd[-1] == "cd /opt/app && ls"

    def test_cwd_avec_espace_est_shell_quote(self):
        """Un cwd contenant un espace est protégé par shlex.quote."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run(["ls"], cwd="/opt/mon app")

        called_cmd = local.run.call_args.args[0]
        assert "'/opt/mon app'" in called_cmd[-1]

    def test_env_injecte_dans_la_commande_distante(self):
        """env devient des `export K=V;` préfixés côté distant."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run(["ls"], env={"MY_VAR": "42"})

        called_cmd = local.run.call_args.args[0]
        assert "export MY_VAR=42; ls" in called_cmd[-1]

    def test_env_avec_injection_shell_est_neutralisee(self):
        """Une valeur env malicieuse est neutralisée par shlex.quote."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run(["ls"], env={"VAR": "$(rm -rf /)"})

        called_cmd = local.run.call_args.args[0]
        # La valeur dangereuse doit être shell-quotée, pas interprétée
        assert "'$(rm -rf /)'" in called_cmd[-1]

    def test_ne_passe_pas_cwd_env_au_local_executor(self):
        """cwd/env ne sont jamais transmis à l'exécuteur local ssh.

        Piège classique documenté dans le plan : cwd/env doivent
        s'appliquer côté distant (dans la commande), pas au binaire
        ssh lui-même en local.
        """
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run(
            ["ls"], cwd="/opt/app", env={"MY_VAR": "42"}, timeout=30
        )

        call_kwargs = local.run.call_args.kwargs
        assert "cwd" not in call_kwargs
        assert "env" not in call_kwargs
        assert call_kwargs["timeout"] == 30

    def test_retourne_le_resultat_du_local_executor(self):
        """run() retourne tel quel le CommandResult du local executor."""
        local = _make_local_mock(return_code=1, stderr="échec ssh")
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        result = executor.run(["ls"])

        assert result.success is False
        assert result.stderr == "échec ssh"


class TestSshCommandExecutorRunStreaming:
    """Tests pour SshCommandExecutor.run_streaming()."""

    def test_delegue_a_run_streaming_local(self):
        """run_streaming() délègue au run_streaming du local executor."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run_streaming(["ls"], merge_stderr=True)

        local.run_streaming.assert_called_once()
        call_kwargs = local.run_streaming.call_args.kwargs
        assert call_kwargs["merge_stderr"] is True
        assert "cwd" not in call_kwargs
        assert "env" not in call_kwargs

    def test_enveloppe_la_commande_avec_ssh(self):
        """La commande streaming est aussi enveloppée par ssh."""
        local = _make_local_mock()
        executor = SshCommandExecutor(
            DeployTarget(host="srv01"), local_executor=local
        )
        executor.run_streaming(["tail", "-f", "/var/log/app.log"])

        called_cmd = local.run_streaming.call_args.args[0]
        assert called_cmd[0] == "ssh"
        assert called_cmd[-1] == "tail -f /var/log/app.log"
