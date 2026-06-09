"""Exécuteur de commandes Linux via subprocess.

Ce module fournit LinuxCommandExecutor, une implémentation concrète
de CommandExecutor qui utilise subprocess pour exécuter des commandes
sur un système Linux.

Les commandes exécutées par root sont distinguées visuellement des
commandes utilisateur :
    - Dans les logs fichier : préfixe textuel [ROOT] ou [user]
    - En console (optionnel) : codes ANSI couleur + gras via
      AnsiCommandFormatter

Example :
    Exécution simple avec logs fichier uniquement :

        from linux_python_utils.commands import LinuxCommandExecutor

        executor = LinuxCommandExecutor(logger=logger)
        result = executor.run(["ls", "-la"])
        print(result.stdout)
        print(result.executed_as_root)  # True si lancé en root

    Exécution avec affichage console coloré en plus des logs :

        from linux_python_utils import FileLogger
        from linux_python_utils.commands import (
            LinuxCommandExecutor,
            AnsiCommandFormatter,
        )

        logger = FileLogger("/var/log/app.log")
        executor = LinuxCommandExecutor(
            logger=logger,
            console_formatter=AnsiCommandFormatter(),
        )
        result = executor.run_streaming(
            ["rsync", "-av", "/src", "/dst"]
        )
"""

import os
import shlex
import subprocess  # nosec B404
import time

from linux_python_utils.commands.base import (
    CommandExecutor,
    CommandResult,
)
from linux_python_utils.commands.formatter import (
    CommandFormatter,
    PlainCommandFormatter,
)
from linux_python_utils.logging.base import Logger


class LinuxCommandExecutor(CommandExecutor):
    """Exécuteur de commandes Linux via subprocess.

    Supporte l'exécution avec capture de sortie et le streaming
    en temps réel vers un logger. Le mode dry_run permet de
    simuler l'exécution sans lancer de processus.

    Les messages de log utilisent PlainCommandFormatter avec les
    préfixes [ROOT] ou [user] selon les privilèges détectés à
    l'initialisation via os.getuid().

    Un console_formatter optionnel (ex: AnsiCommandFormatter)
    permet d'afficher en parallèle des messages colorés sur stdout,
    indépendamment du logger fichier.

    Attributes:
        _logger: Logger optionnel pour les logs fichier.
        _default_env: Variables d'environnement par défaut.
        _default_timeout: Timeout par défaut en secondes.
        _dry_run: Mode simulation.
        _is_root: True si le processus courant est root (uid 0).
        _plain: Formateur texte brut pour les logs fichier.
        _console_formatter: Formateur optionnel pour la console.
    """

    def __init__(
        self,
        logger: Logger | None = None,
        default_env: dict[str, str] | None = None,
        default_timeout: int | None = None,
        dry_run: bool = False,
        console_formatter: CommandFormatter | None = None,
    ) -> None:
        """Initialise l'exécuteur de commandes.

        Détecte automatiquement si le processus courant s'exécute
        en root via os.getuid() == 0.

        Args:
            logger: Logger optionnel pour les sorties fichier.
            default_env: Variables d'environnement par défaut
                (fusionnées avec os.environ).
            default_timeout: Timeout par défaut en secondes.
            dry_run: Si True, simule sans exécuter.
            console_formatter: Formateur optionnel pour la console
                (ex: AnsiCommandFormatter()). Indépendant du logger :
                utiliser FileLogger sans console_output=True pour
                éviter la duplication de sortie console.
        """
        self._logger = logger
        self._default_env = default_env
        self._default_timeout = default_timeout
        self._dry_run = dry_run
        self._is_root: bool = os.getuid() == 0
        self._plain = PlainCommandFormatter()
        self._console_formatter = console_formatter

    def _build_env(
        self,
        env: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        """Construit l'environnement d'exécution.

        Fusionne os.environ, default_env et env spécifique.
        Retourne None si aucun environnement personnalisé
        (subprocess utilisera os.environ par défaut).

        Args:
            env: Variables d'environnement spécifiques.

        Returns:
            Dictionnaire d'environnement ou None.
        """
        if self._default_env is None and env is None:
            return None
        merged = os.environ.copy()
        if self._default_env:
            merged.update(self._default_env)
        if env:
            merged.update(env)
        return merged

    def _resolve_timeout(
        self,
        timeout: int | None = None,
    ) -> int | None:
        """Détermine le timeout effectif.

        Le timeout spécifique à l'appel est prioritaire
        sur le timeout par défaut.

        Args:
            timeout: Timeout spécifique à cet appel.

        Returns:
            Timeout en secondes ou None (pas de limite).
        """
        if timeout is not None:
            return timeout
        return self._default_timeout

    def _log(self, message: str) -> None:
        """Envoie un message au logger fichier si disponible."""
        if self._logger:
            self._logger.log_info(message)

    def _log_error(self, message: str) -> None:
        """Envoie un message d'erreur au logger si disponible."""
        if self._logger:
            self._logger.log_error(message)

    def _print(self, message: str) -> None:
        """Envoie un message déjà formaté vers stdout."""
        print(message)

    def _emit(self, method: str, command: list[str]) -> None:
        """Logue et affiche un événement de commande (start/dry-run).

        Args:
            method: Nom de la méthode du formatter à invoquer.
            command: Commande concernée.
        """
        plain = getattr(self._plain, method)(command, self._is_root)
        self._log(plain)
        if self._console_formatter:
            self._print(
                getattr(self._console_formatter, method)(
                    command, self._is_root
                )
            )

    def _log_timeout(
        self, command: list[str], timeout: int | None
    ) -> None:
        """Logue une expiration de timeout."""
        self._log_error(
            f"Timeout après {timeout}s : {shlex.join(command)}"
        )

    def _log_returncode(
        self, command: list[str], code: int
    ) -> None:
        """Logue un code de retour non nul."""
        self._log_error(
            f"Code retour {code} : {shlex.join(command)}"
        )

    def _log_oserror(self, e: OSError) -> None:
        """Logue une erreur système OS."""
        self._log_error(f"Erreur système : {e}")

    def _result(
        self,
        command: list[str],
        return_code: int,
        stdout: str,
        stderr: str,
        duration: float,
    ) -> CommandResult:
        """Construit un CommandResult avec les champs communs.

        Args:
            command: Commande exécutée.
            return_code: Code de retour du processus.
            stdout: Sortie standard capturée.
            stderr: Sortie d'erreur capturée.
            duration: Durée d'exécution en secondes.

        Returns:
            CommandResult complet avec executed_as_root.
        """
        return CommandResult(
            command=tuple(command),
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
            success=return_code == 0,
            duration=duration,
            executed_as_root=self._is_root,
        )

    def _make_dry_run_result(
        self,
        command: list[str],
    ) -> CommandResult:
        """Crée un CommandResult pour le mode dry_run.

        Args:
            command: Commande simulée.

        Returns:
            CommandResult avec code retour 0.
        """
        self._emit("format_dry_run", command)
        return self._result(command, 0, "", "", 0.0)

    def run(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        """Exécute une commande et retourne le résultat.

        Utilise subprocess.Popen pour capturer stdout et stderr.
        Préfixe les messages de log avec [ROOT] ou [user] selon
        les privilèges détectés à l'initialisation.

        Sur TimeoutExpired, tue le processus (SIGKILL) et draine
        les pipes avant de retourner un résultat d'erreur.

        Args:
            command: Commande sous forme de liste.
            env: Variables d'environnement supplémentaires.
            cwd: Répertoire de travail.
            timeout: Timeout en secondes (prioritaire).

        Returns:
            CommandResult avec les sorties capturées et
            executed_as_root indiquant le contexte d'exécution.

        Note:
            Logue une erreur si le code retour est non-nul et qu'un
            logger est configuré.
        """
        if self._dry_run:
            return self._make_dry_run_result(command)

        effective_env = self._build_env(env)
        effective_timeout = self._resolve_timeout(timeout)
        self._emit("format_start", command)

        start = time.monotonic()
        try:
            with subprocess.Popen(  # nosec B603
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=effective_env,
                cwd=cwd,
            ) as _proc:
                try:
                    _stdout, _stderr = _proc.communicate(
                        timeout=effective_timeout
                    )
                except subprocess.TimeoutExpired:
                    _proc.kill()
                    _stdout, _stderr = _proc.communicate()
                    duration = time.monotonic() - start
                    self._log_timeout(command, effective_timeout)
                    return self._result(
                        command, -1, _stdout, _stderr, duration
                    )
                except KeyboardInterrupt:
                    _proc.terminate()
                    try:
                        _proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _proc.kill()
                    raise
            duration = time.monotonic() - start
            if _proc.returncode != 0:
                self._log_returncode(command, _proc.returncode)
            return self._result(
                command, _proc.returncode, _stdout, _stderr, duration
            )
        except OSError as e:
            duration = time.monotonic() - start
            self._log_oserror(e)
            return self._result(command, -1, "", str(e), duration)

    def run_streaming(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        merge_stderr: bool = False,
    ) -> CommandResult:
        """Exécute avec sortie en temps réel vers le logger.

        Utilise subprocess.Popen pour lire stdout ligne par
        ligne et l'envoyer au logger en temps réel.

        Args:
            command: Commande sous forme de liste.
            env: Variables d'environnement supplémentaires.
            cwd: Répertoire de travail.
            timeout: Timeout en secondes (prioritaire).
            merge_stderr: Si True, fusionne stderr dans stdout via
                subprocess.STDOUT — élimine le risque de deadlock
                causé par un pipe stderr plein (> 64 Ko), au prix
                de la séparation stdout/stderr dans le résultat
                (result.stderr sera toujours "").

        Returns:
            CommandResult avec les sorties capturées et
            executed_as_root indiquant le contexte d'exécution.

        Note:
            Logue une erreur si le code retour est non-nul et qu'un
            logger est configuré.
        """
        if self._dry_run:
            return self._make_dry_run_result(command)

        effective_env = self._build_env(env)
        effective_timeout = self._resolve_timeout(timeout)
        self._emit("format_start_streaming", command)
        stderr_target = (
            subprocess.STDOUT if merge_stderr else subprocess.PIPE
        )

        start = time.monotonic()
        stdout_lines: list[str] = []
        try:
            with subprocess.Popen(  # nosec B603
                command,
                stdout=subprocess.PIPE,
                stderr=stderr_target,
                text=True,
                env=effective_env,
                cwd=cwd,
            ) as proc:
                assert proc.stdout is not None  # nosec
                for line in proc.stdout:
                    stripped = line.rstrip("\n")
                    stdout_lines.append(stripped)
                    self._log(
                        self._plain.format_line(
                            stripped, self._is_root
                        )
                    )
                    if self._console_formatter:
                        self._print(
                            self._console_formatter.format_line(
                                stripped, self._is_root
                            )
                        )

                proc.wait(timeout=effective_timeout)
                stderr = (
                    "" if merge_stderr or proc.stderr is None
                    else proc.stderr.read()
                )

                duration = time.monotonic() - start
                if proc.returncode != 0:
                    self._log_returncode(command, proc.returncode)
                return self._result(
                    command,
                    proc.returncode,
                    "\n".join(stdout_lines),
                    stderr,
                    duration,
                )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            duration = time.monotonic() - start
            stderr = (
                "" if merge_stderr or proc.stderr is None
                else proc.stderr.read()
            )
            self._log_timeout(command, effective_timeout)
            return self._result(
                command,
                -1,
                "\n".join(stdout_lines),
                stderr,
                duration,
            )
        except OSError as e:
            duration = time.monotonic() - start
            self._log_oserror(e)
            return self._result(
                command,
                -1,
                "\n".join(stdout_lines),
                str(e),
                duration,
            )
