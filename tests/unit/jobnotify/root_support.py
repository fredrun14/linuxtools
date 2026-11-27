"""Fait jouer à un test un utilisateur ordinaire quand la CI tourne en root.

Le hook `login` refuse root et le runtime exige que les fichiers d'état
appartiennent à l'euid courant. Les tests du scope user fixent donc `OWNER_UID`
(non nul) ; sous root, les fichiers créés appartiennent pourtant à root. Plutôt
que de changer l'euid du processus (effet de bord sur toute la session), on
montre au runtime, et à lui seul, les fichiers de root comme ceux de `OWNER_UID`.
"""

import os
import types
from collections.abc import Callable
from typing import Any

import pytest

from linuxtools.jobnotify import runtime

UNPRIVILEGED_UID = 1000


class _RuntimeOs(types.SimpleNamespace):
    """`os` vu par le runtime : `fstat` attribue à `owner_uid` les fichiers de root."""

    def __init__(self, owner_uid: int) -> None:
        super().__init__()
        self._owner_uid = owner_uid

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)

    def fstat(self, fd: int) -> os.stat_result:
        info = os.fstat(fd)
        if info.st_uid != 0:
            return info
        fields = list(info)
        fields[4] = self._owner_uid  # st_uid
        return os.stat_result(fields)


def as_unprivileged_user(
    monkeypatch: pytest.MonkeyPatch, owner_uid: int = UNPRIVILEGED_UID
) -> None:
    """Sous root uniquement, substitue `owner_uid` à root pour le runtime."""
    if os.geteuid() == 0:
        monkeypatch.setattr(runtime, "os", _RuntimeOs(owner_uid))


def autouse_unprivileged(
    *, autouse: bool = True
) -> Callable[[pytest.MonkeyPatch], None]:
    """Fabrique la fixture d'un module de test du scope user."""

    @pytest.fixture(autouse=autouse)
    def _fixture(monkeypatch: pytest.MonkeyPatch) -> None:
        as_unprivileged_user(monkeypatch)

    return _fixture
