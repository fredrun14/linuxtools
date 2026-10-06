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

        from linuxtools.commands import LinuxCommandExecutor

        executor = LinuxCommandExecutor(logger=logger)
        result = executor.run(["ls", "-la"])
        print(result.stdout)
        print(result.executed_as_root)  # True si lancé en root

    Exécution avec affichage console coloré en plus des logs :

        from linuxtools import FileLogger
        from linuxtools.commands import (
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
import signal
import subprocess  # nosec B404
import threading
import time
from collections.abc import Iterable

from linuxtools.commands.base import (
    CommandExecutor,
    CommandResult,
)
from linuxtools.commands.formatter import (
    CommandFormatter,
    PlainCommandFormatter,
)
from linuxtools.logging.base import Logger


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

    def _log_timeout(self, command: list[str], timeout: int | None) -> None:
        """Logue une expiration de timeout."""
        self._log_error(f"Timeout après {timeout}s : {shlex.join(command)}")

    def _log_returncode(self, command: list[str], code: int) -> None:
        """Logue un code de retour non nul."""
        self._log_error(f"Code retour {code} : {shlex.join(command)}")

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
        probe: bool = False,
        stdin: str | None = None,
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
            probe: Si True, la commande est une sonde en lecture seule
                et s'exécute même en mode dry-run. Réservé aux
                commandes sans effet de bord (``rpm -q``,
                ``repolist``, ``flatpak info``) : le mode dry-run
                s'appuie sur leur résultat pour décider quoi faire.
            stdin: Contenu texte à envoyer sur l'entrée standard du
                process lancé, ou None pour ne rien envoyer.

        Returns:
            CommandResult avec les sorties capturées et
            executed_as_root indiquant le contexte d'exécution.

        Note:
            Logue une erreur si le code retour est non-nul et qu'un
            logger est configuré.
        """
        # Une sonde en lecture doit s'exécuter même en dry-run : le
        # mode simulation s'appuie sur son résultat pour décider quoi
        # faire.
        if self._dry_run and not probe:
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
                stdin=(subprocess.PIPE if stdin is not None else None),
                text=True,
                env=effective_env,
                cwd=cwd,
            ) as _proc:
                try:
                    _stdout, _stderr = _proc.communicate(
                        input=stdin, timeout=effective_timeout
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

    @staticmethod
    def _drain(stream: Iterable[str], sink: list[str]) -> None:
        """Accumule dans `sink` toutes les lignes de `stream` jusqu'à EOF.

        Destinée à un fil de drainage de stderr : ne logue rien.

        Args:
            stream: Flux texte itérable (ex. proc.stderr).
            sink: Liste qui reçoit les lignes lues.
        """
        sink.extend(stream)

    @staticmethod
    def _kill_group(proc: subprocess.Popen[str]) -> None:
        """Tue (SIGKILL) tout le groupe de processus de ``proc``.

        Suppose ``proc`` lancé avec ``process_group=0`` (pgid == pid).
        Se rabat sur ``proc.kill()`` si le groupe est introuvable ou
        inaccessible.

        Args:
            proc: Processus dont le groupe doit être tué.
        """
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()

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
            timeout: Timeout en secondes (prioritaire). Appliqué
                pendant la lecture : à l'échéance, tout le groupe de
                processus est tué (SIGKILL), petits-fils compris (code
                retour -1, sorties partielles conservées).
            merge_stderr: Si True, fusionne stderr dans stdout via
                subprocess.STDOUT (result.stderr sera toujours ""). Plus
                nécessaire contre le deadlock (stderr est vidé en continu
                par un fil dédié), reste utile pour obtenir un flux unique.

        Returns:
            CommandResult avec les sorties capturées et
            executed_as_root indiquant le contexte d'exécution.

        Note:
            Logue une erreur si le code retour est non-nul et qu'un
            logger est configuré. Le processus est lancé dans son propre
            groupe : sur KeyboardInterrupt, le groupe est tué puis
            l'exception est relancée.
        """
        if self._dry_run:
            return self._make_dry_run_result(command)

        effective_env = self._build_env(env)
        effective_timeout = self._resolve_timeout(timeout)
        self._emit("format_start_streaming", command)
        stderr_target = subprocess.STDOUT if merge_stderr else subprocess.PIPE

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
                # Groupe de processus dédié : le délai (ou Ctrl-C) peut
                # ainsi tuer tout l'arbre, pas seulement le shell.
                process_group=0,
            ) as proc:
                assert proc.stdout is not None  # nosec

                # Fil de drainage : vide stderr en continu pour éviter
                # le blocage du processus sur un pipe plein (> 64 Ko).
                # Il n'accumule que, sans logger (pas de concurrence).
                stderr_lines: list[str] = []
                stderr_thread: threading.Thread | None = None
                if not merge_stderr and proc.stderr is not None:
                    stderr_thread = threading.Thread(
                        target=self._drain,
                        args=(proc.stderr, stderr_lines),
                        daemon=True,
                    )
                    stderr_thread.start()

                # Chien de garde : tue le groupe à l'échéance, ce qui
                # ferme stdout et termine la boucle de lecture ci-dessous.
                timed_out = threading.Event()
                watchdog: threading.Timer | None = None
                if effective_timeout is not None:

                    def _expire() -> None:
                        timed_out.set()
                        self._kill_group(proc)

                    watchdog = threading.Timer(effective_timeout, _expire)
                    watchdog.daemon = True
                    watchdog.start()

                try:
                    for line in proc.stdout:
                        stripped = line.rstrip("\n")
                        stdout_lines.append(stripped)
                        self._log(
                            self._plain.format_line(stripped, self._is_root)
                        )
                        if self._console_formatter:
                            self._print(
                                self._console_formatter.format_line(
                                    stripped, self._is_root
                                )
                            )
                    # stdout est fermé : le processus est terminé ou tué.
                    proc.wait()
                except KeyboardInterrupt:
                    # Le processus n'est plus dans le groupe du terminal
                    # (process_group=0) : Ctrl-C ne l'atteint plus, on tue
                    # donc le groupe nous-mêmes avant de relancer.
                    self._kill_group(proc)
                    proc.wait()
                    raise
                finally:
                    if watchdog is not None:
                        watchdog.cancel()

                if stderr_thread is not None:
                    # Join borné : un petit-fils gardant stderr ouvert ne
                    # doit pas bloquer ; on utilise ce qui est drainé.
                    stderr_thread.join(timeout=5)
                stderr = "".join(stderr_lines)

                duration = time.monotonic() - start
                if timed_out.is_set():
                    self._log_timeout(command, effective_timeout)
                    return self._result(
                        command,
                        -1,
                        "\n".join(stdout_lines),
                        stderr,
                        duration,
                    )
                if proc.returncode != 0:
                    self._log_returncode(command, proc.returncode)
                return self._result(
                    command,
                    proc.returncode,
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
