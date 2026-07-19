"""Exécuteur de commandes distant via ssh.

Ce module fournit SshCommandExecutor, un CommandExecutor qui
enveloppe chaque commande dans un appel ssh vers un hôte distant.
Permet à Deployer, VenvInstaller et InstallVerifier de rester
agnostiques local/distant : ils reçoivent un CommandExecutor
quelconque et ne savent jamais s'il cible l'hôte local ou un hôte
distant.
"""

from __future__ import annotations

import shlex

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.deploy.models import DeployTarget
from linuxtools.logging.base import Logger


class SshCommandExecutor(CommandExecutor):
    """Exécute des commandes sur un hôte distant via ssh.

    Enveloppe chaque commande dans `ssh [opts] user@host -- <cmd>`
    et délègue l'exécution locale de ce ssh à un
    LinuxCommandExecutor.

    Attributes:
        _target: Hôte distant (doit être is_remote=True).
        _local: Exécuteur local qui lance le binaire ssh.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        target: DeployTarget,
        local_executor: CommandExecutor | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise l'exécuteur distant.

        Args:
            target: Cible distante (host renseigné).
            local_executor: Exécuteur local pour lancer ssh. Si
                None, un LinuxCommandExecutor est créé.
            logger: Logger optionnel, propagé au LinuxCommandExecutor
                par défaut.

        Raises:
            ValueError: Si target n'est pas distante (host absent).
        """
        if not target.is_remote:
            raise ValueError(
                "SshCommandExecutor requiert une cible distante"
                " (DeployTarget.host doit être renseigné)"
            )
        self._target = target
        self._local = local_executor or LinuxCommandExecutor(
            logger=logger
        )
        self._logger = logger

    def _wrap(
        self,
        command: list[str],
        cwd: str | None,
        env: dict[str, str] | None,
    ) -> list[str]:
        """Construit la commande ssh complète pour l'hôte distant.

        Le cwd et env sont injectés dans la commande *distante*
        (préfixe shell), jamais passés au LinuxCommandExecutor local
        qui lance ssh — sinon ils s'appliqueraient au binaire ssh
        lui-même et non à la commande distante.

        Args:
            command: Commande à exécuter côté distant.
            cwd: Répertoire de travail distant, ou None.
            env: Variables d'environnement distantes, ou None.

        Returns:
            Commande ssh complète, prête pour un CommandExecutor
            local.
        """
        prefix = ""
        if cwd:
            prefix += f"cd {shlex.quote(cwd)} && "
        if env:
            exports = "".join(
                f"export {key}={shlex.quote(value)}; "
                for key, value in env.items()
            )
            prefix += exports

        remote = shlex.join(command)
        remote_command = f"{prefix}{remote}"

        return [
            "ssh",
            *self._target.ssh_options,
            self._target.ssh_destination,
            "--",
            remote_command,
        ]

    def run(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        """Exécute une commande sur l'hôte distant et attend le résultat.

        Args:
            command: Commande à exécuter côté distant.
            env: Variables d'environnement distantes.
            cwd: Répertoire de travail distant.
            timeout: Timeout en secondes pour l'appel ssh local.

        Returns:
            CommandResult de l'appel ssh (le code retour reflète
            celui de la commande distante).
        """
        return self._local.run(
            self._wrap(command, cwd, env), timeout=timeout
        )

    def run_streaming(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        merge_stderr: bool = False,
    ) -> CommandResult:
        """Exécute une commande distante avec sortie en temps réel.

        Args:
            command: Commande à exécuter côté distant.
            env: Variables d'environnement distantes.
            cwd: Répertoire de travail distant.
            timeout: Timeout en secondes pour l'appel ssh local.
            merge_stderr: Propagé tel quel au LinuxCommandExecutor
                local.

        Returns:
            CommandResult de l'appel ssh en streaming.
        """
        return self._local.run_streaming(
            self._wrap(command, cwd, env),
            timeout=timeout,
            merge_stderr=merge_stderr,
        )
