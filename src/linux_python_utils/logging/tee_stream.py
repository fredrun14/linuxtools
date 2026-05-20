"""Flux dupliqué vers le terminal et vers un fichier log (pattern tee Unix)."""

# stdlib
from typing import IO, Any


class TeeStream:
    """Duplique chaque écriture vers le flux original et vers un fichier log.

    Inspiré de la commande Unix ``tee`` (raccord en T) : tout ce qui est
    écrit sur le flux est envoyé simultanément au terminal (flux original)
    et au fichier log, afin de conserver une trace complète de l'exécution
    sans sacrifier l'affichage en temps réel.

    Usage typique — capturer stdout et stderr dans un fichier log tout en
    conservant l'affichage console ::

        log_fh = open(log_file, "a", encoding="utf-8")
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = TeeStream(sys.stdout, log_fh)
        sys.stderr = TeeStream(sys.stderr, log_fh)
        try:
            ...  # code de l'application
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            log_fh.close()

    Attributes:
        _original: Flux d'origine conservé pour l'affichage terminal.
        _log_fh: Handle du fichier log ouvert en mode append.

    Example:
        >>> import io, sys
        >>> buf = io.StringIO()
        >>> tee = TeeStream(sys.stdout, buf)
        >>> _ = tee.write("hello")
        >>> buf.getvalue()
        'hello'
    """

    def __init__(self, original: IO[str], log_fh: IO[str]) -> None:
        """Initialise le flux dupliqué.

        Args:
            original: Flux d'origine (sys.stdout ou sys.stderr).
            log_fh: Handle du fichier log ouvert en mode append.
        """
        self._original = original
        self._log_fh = log_fh

    def write(self, data: str) -> int:
        """Écrit dans le flux original et dans le fichier log.

        Args:
            data: Données à écrire.

        Returns:
            Nombre de caractères écrits.
        """
        self._original.write(data)
        self._log_fh.write(data)
        return len(data)

    def flush(self) -> None:
        """Vide les tampons des deux flux."""
        self._original.flush()
        self._log_fh.flush()

    def __getattr__(self, name: str) -> Any:
        """Délègue les attributs inconnus au flux original.

        Args:
            name: Nom de l'attribut demandé (ex: encoding, fileno, isatty).

        Returns:
            Attribut correspondant du flux original.
        """
        return getattr(self._original, name)
