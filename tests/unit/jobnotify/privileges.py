"""Exécute un test en utilisateur ordinaire, même quand la CI tourne en root.

Le hook `login` du scope user refuse root, et le runtime exige que les fichiers
d'état appartiennent à l'euid courant. Sous root (CI), on abaisse donc l'euid du
processus à `UNPRIVILEGED_UID` et on donne le dossier de test à cet utilisateur.
"""

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

UNPRIVILEGED_UID = 1000


def unprivileged_tmp() -> Iterator[Path]:
    """Dossier jetable ; sous root, l'euid est abaissé le temps du test."""
    root = Path(tempfile.mkdtemp(prefix="jobnotify-"))
    was_root = os.geteuid() == 0
    try:
        if was_root:
            os.chown(root, UNPRIVILEGED_UID, UNPRIVILEGED_UID)
            os.seteuid(UNPRIVILEGED_UID)
        yield root
    finally:
        if was_root:
            os.seteuid(0)
        shutil.rmtree(root, ignore_errors=True)
